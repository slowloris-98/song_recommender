"""Per-turn recording: one JSONL line per /chat turn.

The agent's `astream_events` stream already carries everything worth keeping — the user's
message, each tool call with its Spotify results, the streamed answer, token usage. The
chat route feeds those events here; this module accumulates them and writes one complete
record when the turn ends.

The file doubles as an eval dataset (tests/run_tool_eval.py can replay it), so records are
written whole and never rotated away — unlike backend.log, which is a rolling log.

Records hold full user messages and full model output. Set TURN_LOG_ENABLED=false to
disable. Nothing in here may break a turn: every write is best-effort.
"""

import json
import logging
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import settings

# Same project-root logs/ as backend.log, and outside backend/ for the same reason:
# `uvicorn --reload` watches backend/, so writing a record there would restart the server
# mid-stream (see the comment in main.py).
_TURN_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "turns.jsonl"

logger = logging.getLogger(__name__)

_handle = None


def _write(record: dict) -> None:
    """Append one record. Opens the file on first use so a disabled log creates nothing."""
    global _handle
    if _handle is None:
        _TURN_LOG_PATH.parent.mkdir(exist_ok=True)
        _handle = _TURN_LOG_PATH.open("a", encoding="utf-8")
    _handle.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
    _handle.flush()  # a crash mid-session shouldn't cost us the turns before it


def _loads(value: object) -> object:
    """json.loads that passes non-JSON (and non-strings) straight through."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def _unwrap_tool_output(output: object) -> object:
    """Reduce a tool result to the actual Spotify payload.

    A tool result reaches us triple-wrapped: a ToolMessage, whose `.content` is a JSON
    string, which decodes to a list of MCP content blocks like
    `{"type": "text", "text": "<the track JSON, escaped again>"}` — one block per item.
    We peel all three so the record holds real track objects you can query, rather than a
    doubly-escaped blob. Any layer that doesn't match is left as-is.
    """
    content = _loads(getattr(output, "content", output))
    if isinstance(content, list) and content and all(
        isinstance(b, dict) and b.get("type") == "text" for b in content
    ):
        return [_loads(b.get("text")) for b in content]
    return content


class TurnRecorder:
    """Accumulates one turn. Call the on_* hooks as events arrive, then flush() once."""

    def __init__(self, session_id: str, message: str) -> None:
        self.turn_id = uuid4().hex[:12]
        self._session_id = session_id
        self._message = message
        self._started_at = datetime.now(timezone.utc)
        self._start = time.monotonic()
        self._tokens: list[str] = []
        self._tool_calls: list[dict] = []
        self._usage: dict | None = None
        self._error: dict | None = None

    def _elapsed_ms(self) -> int:
        return round((time.monotonic() - self._start) * 1000)

    def on_token(self, text: str) -> None:
        self._tokens.append(text)

    def on_tool_start(self, name: str, tool_input: object) -> None:
        self._tool_calls.append(
            {"name": name, "input": tool_input, "_started": time.monotonic()}
        )

    def on_tool_end(self, name: str, output: object) -> dict:
        """Close the most recent still-open call with this name.

        Matching newest-first rather than by position keeps parallel tool calls from
        attributing one call's results to another's.

        Returns a small summary the caller can forward to the client: how long the call
        took and how many items came back. We hand it back rather than letting the caller
        recompute it — unwrapping parses every track, and a second timer would report a
        different duration than the one recorded here.
        """
        output = _unwrap_tool_output(output)
        count = len(output) if isinstance(output, list) else None
        for call in reversed(self._tool_calls):
            if call["name"] == name and "output" not in call:
                call["output"] = output
                call["duration_ms"] = round((time.monotonic() - call.pop("_started")) * 1000)
                return {"ms": call["duration_ms"], "count": count}
        # No open call to match — record it anyway rather than dropping the results.
        self._tool_calls.append({"name": name, "input": None, "output": output})
        return {"ms": None, "count": count}

    def on_usage(self, usage: dict | None) -> None:
        if usage:
            self._usage = usage

    def fail(self, exc: BaseException) -> None:
        self._error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        }

    @property
    def tool_count(self) -> int:
        return len(self._tool_calls)

    def flush(self) -> int:
        """Write the record and return the turn's duration in ms."""
        duration_ms = self._elapsed_ms()
        if not settings.turn_log_enabled:
            return duration_ms
        for call in self._tool_calls:
            call.pop("_started", None)  # a tool still open when the turn died
        record = {
            "turn_id": self.turn_id,
            "session_id": self._session_id,
            "started_at": self._started_at.isoformat(),
            "duration_ms": duration_ms,
            "status": "error" if self._error else "ok",
            "llm": {"provider": settings.llm_provider, "model": settings.llm_model},
            "message": self._message,
            "answer": "".join(self._tokens),
            "tool_calls": self._tool_calls,
            "usage": self._usage,
            "error": self._error,
        }
        try:
            _write(record)
        except Exception:  # noqa: BLE001 - a broken turn log must never break a turn
            logger.exception("failed to write turn record %s", self.turn_id)
        return duration_ms
