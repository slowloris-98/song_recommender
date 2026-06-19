"""Tool-call evaluation harness for the song-recommender agent.

Sends each prompt in a prompts file to the running backend's `/chat` SSE endpoint and tallies
the `tool_start` events the agent emits, so you can see how many — and which — Spotify tool
calls different user prompts trigger.

It does NOT instrument the agent: the backend already streams a `tool_start` event carrying the
tool `name` and `input` for every invocation (see backend/app/routes/chat.py). We just listen.

Prerequisites (all must be running — see README.md):
  - MCP server   : mcp_server/, port 8001, with valid Spotify credentials
  - Backend      : uvicorn app.main:app --port 8000, with a valid LLM key

Usage (from repo root, with the backend venv active so httpx + httpx_sse are importable):
    python tests/run_tool_eval.py
    python tests/run_tool_eval.py --base-url http://localhost:8000 --prompts tests/test_prompts.jsonl

Each prompt runs with a fresh session_id (uuid4) so the agent's per-thread memory does not leak
context from one prompt into the next.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from httpx_sse import connect_sse

DEFAULT_BASE_URL = os.environ.get("EVAL_BASE_URL", "http://localhost:8000")
DEFAULT_PROMPTS = Path(__file__).with_name("test_prompts.jsonl")
# LLM + live Spotify calls are slow; give each prompt plenty of room to finish streaming.
READ_TIMEOUT_SECONDS = 120.0


@dataclass
class PromptCase:
    id: str
    prompt: str
    category: str = ""
    expected_tools: list[str] = field(default_factory=list)


@dataclass
class PromptResult:
    case: PromptCase
    calls: list[tuple[str, str]]  # (tool_name, json-serialized input)
    error: str | None = None

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    @property
    def tool_counts(self) -> Counter:
        return Counter(name for name, _ in self.calls)

    @property
    def unique_tools(self) -> int:
        """Distinct tool names invoked at least once — the 'unique tool calls' headline."""
        return len(self.tool_counts)

    @property
    def distinct_arg_calls(self) -> int:
        """Distinct (tool name + arguments) combinations."""
        return len(set(self.calls))


def load_prompts(path: Path) -> list[PromptCase]:
    cases: list[PromptCase] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            cases.append(
                PromptCase(
                    id=obj.get("id", f"prompt-{lineno}"),
                    prompt=obj["prompt"],
                    category=obj.get("category", ""),
                    expected_tools=list(obj.get("expected_tools", [])),
                )
            )
    if not cases:
        raise SystemExit(f"No prompts found in {path}")
    return cases


def run_case(client: httpx.Client, base_url: str, case: PromptCase) -> PromptResult:
    """POST one prompt to /chat and collect tool_start events until done/error."""
    payload = {"session_id": f"eval-{uuid.uuid4()}", "message": case.prompt}
    calls: list[tuple[str, str]] = []
    try:
        with connect_sse(
            client, "POST", f"{base_url}/chat", json=payload
        ) as event_source:
            for sse in event_source.iter_sse():
                if sse.event == "tool_start":
                    data = json.loads(sse.data) if sse.data else {}
                    name = data.get("name", "<unknown>")
                    args = json.dumps(data.get("input"), sort_keys=True, default=str)
                    calls.append((name, args))
                elif sse.event == "error":
                    data = json.loads(sse.data) if sse.data else {}
                    return PromptResult(case, calls, error=data.get("message", "error"))
                elif sse.event == "done":
                    break
    except httpx.HTTPError as exc:
        return PromptResult(case, calls, error=f"transport: {exc}")
    return PromptResult(case, calls)


def _expected_match(result: PromptResult) -> str:
    """Compare the multiset of expected vs actual tool names. Annotation only."""
    if not result.case.expected_tools:
        return "ok" if result.total_calls == 0 else "extra"
    return "ok" if Counter(result.case.expected_tools) == result.tool_counts else "diff"


def print_report(results: list[PromptResult]) -> None:
    header = f"{'id':<26} {'category':<8} {'total':>5} {'unique':>6} {'expect':>6}  tools-used"
    print(header)
    print("-" * len(header))
    for r in results:
        if r.error:
            print(f"{r.case.id:<26} {r.case.category:<8} {'ERR':>5} {'-':>6} {'-':>6}  {r.error}")
            continue
        breakdown = ", ".join(f"{n}x{c}" for n, c in sorted(r.tool_counts.items())) or "(none)"
        print(
            f"{r.case.id:<26} {r.case.category:<8} {r.total_calls:>5} "
            f"{r.unique_tools:>6} {_expected_match(r):>6}  {breakdown}"
        )

    ok = [r for r in results if not r.error]
    errored = [r for r in results if r.error]
    print("-" * len(header))
    print(
        f"Summary: {len(ok)} prompts ran, {len(errored)} errored. "
        f"Total tool calls across all prompts: {sum(r.total_calls for r in ok)}. "
        f"Aggregate distinct tools: {len(Counter(n for r in ok for n, _ in r.calls))}."
    )
    if errored:
        print(
            "Note: errors usually mean the backend/MCP server isn't running or a key is "
            "missing — see the prerequisites in this file's docstring."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="backend base URL")
    parser.add_argument(
        "--prompts", type=Path, default=DEFAULT_PROMPTS, help="path to a .jsonl prompts file"
    )
    args = parser.parse_args(argv)

    cases = load_prompts(args.prompts)
    base_url = args.base_url.rstrip("/")
    print(f"Running {len(cases)} prompt(s) against {base_url}/chat ...\n")

    # connect + read timeouts; no overall pool wait since prompts run one at a time.
    timeout = httpx.Timeout(connect=10.0, read=READ_TIMEOUT_SECONDS, write=10.0, pool=10.0)
    results: list[PromptResult] = []
    with httpx.Client(timeout=timeout) as client:
        for case in cases:
            print(f"  -> {case.id} ...", flush=True)
            results.append(run_case(client, base_url, case))

    print()
    print_report(results)

    # Exit non-zero only on transport/connection failures, not expected-vs-actual mismatches.
    return 1 if any(r.error and r.error.startswith("transport") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
