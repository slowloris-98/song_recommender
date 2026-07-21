# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Three independently-deployed services:

```
React (Vite) --SSE--> FastAPI + LangGraph agent --MCP (streamable-http)--> FastMCP --> Spotify Web API
  frontend/ :5173         backend/ :8000                                    mcp_server/ :8001/mcp
```

**The MCP server owns all Spotify access.** The backend holds no Spotify credentials and does no
OAuth; it only discovers tools over MCP. Do not add Spotify HTTP calls to `backend/`.

**Startup order matters.** `backend/app/main.py` does everything expensive in the lifespan: connect
MCP -> `get_tools()` -> build LLM -> build agent. It retries the MCP connection 6x/15s and then
**hard-fails** if unreachable. Start `mcp_server` first.

**Tools are never declared in Python on the backend.** MCP tools arrive as LangChain
`StructuredTool`s from `get_tools()` and are concatenated with the one local tool
(`local_tools.mood_to_genres`) at `backend/app/main.py:64`. The agent can't distinguish them.
Adding a Spotify capability means adding a tool in `mcp_server/tools.py` — nothing on the backend
changes.

### The Spotify constraint that shapes everything

Spotify deprecated the "easy" discovery endpoints in Nov 2024. A new app **cannot** use:
`/recommendations`, `/artists/{id}/top-tracks`, `/artists/{id}/related-artists`, audio-features,
audio-analysis, all `/browse/*`, and batch `/tracks|/artists|/albums`. Artist objects come back with
`genres` and `popularity` empty.

Available and used: `/search`, `/artists/{id}`, `/artists/{id}/albums`, `/albums/{id}/tracks`,
`/tracks/{id}`. That's the whole allow-list (`PLAN.md:29-38`).

**Source of truth for the Spotify Web API** — whenever you need to confirm which endpoints,
parameters (e.g. `market`), or fields are still exposed, consult the canonical OpenAPI schema
rather than relying on memory (much of it was deprecated in Nov 2024):
https://developer.spotify.com/reference/web-api/open-api-schema.yaml

Consequences to respect:
- `search` is the backbone of recommendation. Genre discovery is `genre:"x"` search, not an API.
- **Genre is an artist attribute; there is no track-level genre.** Genres can't be read from the API
  either — `backend/app/genres.py` holds a hand-vetted `VETTED_VOCAB` (genre / mood / region /
  scene terms, with a flat `VETTED_GENRES` derived from it), regenerated empirically by
  `scripts/validate_genres.py`. Note: emotion/weather words don't work as `genre:` filters — they
  are mapped to real genres via `MOOD_GENRES` / the `mood_to_genres` tool instead.
- `/search` rejects `limit > 10`. Anything wanting more must paginate (see `_pages` below).
- Do not add `get_artist_top_tracks` or a batch `get_tracks` — they 404.

### Prompt surface (edit with care)

Two files are runtime behavior, not docs:

- `backend/app/prompts.py` — the agent's routing policy. Encodes the "songs BY X" vs "songs LIKE X"
  split (getting this wrong is called out as the worst failure mode), the batching rule, and hard
  grounding rules: recommend only tracks a tool returned this conversation, never from model
  knowledge, drop any track lacking a real `url`.
- `mcp_server/tools.py` tool docstrings — these steer which tool the agent picks and which dead ends
  it avoids. Rewording them changes agent behavior.

### Shared idioms in `mcp_server/tools.py`

Fan-out is the norm; a naive one-call-at-a-time drive would be ~44 sequential requests.

- `_pages(wanted)` -> `(limit, offset)` pairs of <=10, working around the `/search` limit cap.
- `_gather(coros)` -> semaphore-bounded `asyncio.gather(..., return_exceptions=True)`. Exceptions are
  **returned, not raised**, so one bad page can't sink a fan-out.
- `_items(result, key)` -> the counterpart: safely unwraps a result that may be an exception sentinel
  or contain Spotify's null padding. Always pair with `_gather`.
- `_round_robin(tracks)` -> interleaves by lead artist so artist diversity is deterministic rather
  than left to prompt instructions.

Jobs are built eagerly into a `jobs` list with a parallel `origin` list to preserve the
input->result mapping, then recombined via `zip(origin, await _gather(jobs))`.

`_spotify` is a **module global** set by `set_client()` from `server.py`. Any test or alternate
embedding must call `tools.set_client(...)` first.

Every tool takes `user_token: str | None = None`. It is unused in Phase 1 and nothing populates it —
it's a Phase-2 OAuth seam, kept so playlist writes are purely additive.

## Running locally

Three terminals. Note the venvs on disk are `venv/`, not the `.venv/` the README shows.

```bash
# 1. MCP server — MUST be first; cwd must be mcp_server/ (flat imports, no package __init__)
cd mcp_server && python server.py                      # http://localhost:8001/mcp

# 2. Backend
cd backend && uvicorn app.main:app --reload --port 8000

# 3. Frontend
cd frontend && npm run dev                             # http://localhost:5173
```

Windows venv interpreters: `backend/venv/Scripts/python.exe`, `mcp_server/venv/Scripts/python.exe`.

Docker: `docker compose up --build` (create `backend/.env` and `mcp_server/.env` first). Note
compose has no volume mounts, so source edits need a rebuild.

Smoke-test the SSE stream directly:
```bash
curl -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"smoke-1","message":"Recommend songs like Tame Impala"}'
```

## Testing

**There is no unit test suite** — no pytest, no pyproject/setup.cfg, no frontend test script. There
is also **no linter or formatter configured** (no ruff, eslint, or prettier config anywhere). Don't
reference `pytest` or `npm run lint` in verification steps; they don't exist.

What exists is one end-to-end eval harness requiring both servers live plus real Spotify + LLM keys:

```bash
python tests/run_tool_eval.py
python tests/run_tool_eval.py --base-url http://localhost:8000 --prompts tests/test_prompts.jsonl
```

It POSTs each prompt in `tests/test_prompts.jsonl`, tallies `tool_start` events against
`expected_tools`, and prints a diff. **It exits 0 even on tool mismatches** — it's a report, not a
gate. Only transport failures exit 1.

Syntax check available in the permission allowlist:
`python -m py_compile mcp_server/server.py backend/app/main.py`

## The `/chat` contract

`POST /chat` with `{session_id, message}` returns a `StreamingResponse` of hand-formatted SSE
(`backend/app/routes/chat.py:32`). There is no response schema — `schemas.py` defines only
`ChatRequest`.

Five events: `token{text}`, `tool_start{name,input}`, `tool_end{name}`, `done{}`, `error{message}`.
`tool_end` **deliberately omits tool output** — results go to the turn log, never to the client.

The frontend hand-rolls the SSE parser over `fetch` + `ReadableStream` (`frontend/src/api.js`)
because `EventSource` can't POST. It handles only `token`, `tool_start`, and `error`; `busy` clears
when the stream closes, not on `done`.

`session_id` is generated client-side into localStorage and used directly as the LangGraph
`thread_id`. It is **not** an authenticated principal. Memory is an in-process `MemorySaver`, so it
resets on restart and isn't shared across workers.

## Logging

Both log files live at **repo root `logs/`**, deliberately outside `backend/` — `uvicorn --reload`
watches `backend/`, and watchfiles' own log lines would otherwise trigger a self-sustaining reload
loop (see the comment at `backend/app/main.py:24-26`).

- `logs/backend.log`, `mcp_server/logs/mcp.log` — rotating, 1 MB x 3.
- `logs/turns.jsonl` — one JSON record per turn, **never rotated** because it doubles as the eval
  dataset. Contains full user messages and model output; gate with `TURN_LOG_ENABLED=false`.
  Turn-log failures are swallowed by design: a broken log must never break a turn.

## Conventions

- Swapping LLM provider is config-only: `LLM_PROVIDER` / `LLM_MODEL` feed `init_chat_model` in
  `backend/app/llm.py`. Only `langchain-openai` is installed, so other providers need their
  integration package added first.
- LangChain v1 API — use `create_agent`, not the deprecated `create_react_agent`.
- `normalize.py` deliberately **drops album art**. Images were ~48% of a normalized track payload
  (~6.5k tokens/turn) and rendered nowhere. If a structured `tracks` event is added later, re-source
  art in the backend for the UI only — never route it through LLM context. Same warning at
  `frontend/src/components/TrackCard.jsx:8-11` (that component is currently dead code, staged for
  exactly that future event).
- Tuning knobs live in `mcp_server/config.py`: `artists_per_genre=10`, `tracks_per_artist=10`,
  `discovery_concurrency=8` (measured safe: 26 concurrent calls in 1.6s, no 429s),
  `max_genres_per_call=4`.
- Production is `render.yaml`, and it diverges from docker-compose: the frontend deploys as a
  **static site**, so `frontend/Dockerfile` (a Vite dev-server image) is local-only.
- `VITE_API_BASE_URL` is baked into the bundle at build time — changing it on Render requires
  "Clear build cache & deploy".
