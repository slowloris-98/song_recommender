# 🎧 Song Recommender

A conversational song-recommendation system. The user chats about artists, albums, tracks, or
moods they like; an LLM agent composes Spotify API calls to recommend songs.

```
React (Vite)  ──SSE──▶  FastAPI + LangGraph agent  ──MCP (streamable-http)──▶  FastMCP ──▶ Spotify Web API
  frontend/                      backend/                                       mcp_server/
```

See **[PLAN.md](PLAN.md)** for the full architecture review, design decisions, and the live
progress checklist.

## Why the agent composes calls (important)

Spotify deprecated most of the "easy" discovery endpoints (Nov 2024) — `/recommendations`,
artist top-tracks, related-artists, audio-features, browse playlists, and batch lookups are all
unavailable to a new app. So **`search`** (with `genre:` / `year:` / `artist:` filters) is the
backbone, and the agent makes **multiple tool calls** to assemble recommendations.

The recommendation strategy is encoded in the agent's system prompt
([backend/app/prompts.py](backend/app/prompts.py)): search a seed artist → read its `genres`
via `get_artist` → search tracks by those genres + a year range → optionally dig into albums
with `get_artist_albums` / `get_album_tracks` → dedupe and return ~10 concrete tracks.

## Architecture at a glance

Three independent services. The MCP server owns *all* Spotify access, so the backend never
touches Spotify directly and stays portable.

1. **`mcp_server/`** — a [FastMCP](https://github.com/modelcontextprotocol) server that wraps the
   Spotify Web API and exposes a handful of read-only tools over `streamable-http` at `/mcp`.
   Handles Spotify auth (Client Credentials), token caching, 429 rate-limit backoff, and trims
   bulky Spotify payloads into compact dicts.
2. **`backend/`** — a FastAPI app that builds a LangGraph ReAct agent once at startup. On each
   request it streams the agent's run as Server-Sent Events. The agent's tools are the MCP
   server's tools, loaded via `langchain-mcp-adapters`. The LLM provider is swappable by config.
3. **`frontend/`** — a React/Vite chat UI that POSTs to `/chat`, renders the streamed tokens as
   Markdown (including inline album art), and persists a `session_id` for multi-turn memory.

### Request flow

```
User types in the React UI
  └─▶ POST /chat { session_id, message }                         (frontend/src/api.js)
        └─▶ Backend resolves agent from app.state, streams astream_events
              ├─ on_chat_model_stream  ─▶ SSE "token"
              ├─ on_tool_start          ─▶ SSE "tool_start"  ─┐
              ├─ on_tool_end            ─▶ SSE "tool_end"      │  tool call goes:
              └─ done / error           ─▶ SSE "done"/"error"  │  agent ─▶ MCP client
                                                               └─▶ MCP server ─▶ Spotify
```

Conversation memory is held by an in-memory `MemorySaver` checkpointer keyed by
`thread_id = session_id`. It lives for the lifetime of the backend process; swap it for a
persistent checkpointer (e.g. `SqliteSaver`/`PostgresSaver`) for production.

## Prerequisites

- Python 3.12+, Node 20+
- A Spotify app (free): https://developer.spotify.com/dashboard → copy the **Client ID** and **Client Secret**
- An LLM provider key (default OpenAI: `OPENAI_API_KEY`)

## Run locally (three terminals)

### 1. MCP server
```bash
cd mcp_server
python -m venv .venv && . .venv/Scripts/activate   # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env        # then fill in SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET
python server.py            # serves MCP at http://localhost:8001/mcp
```

### 2. Backend
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev                 # http://localhost:5173
```

Open http://localhost:5173 and chat.

## Run with Docker
```bash
# create the two backend/.env and mcp_server/.env files first (from the examples)
docker compose up --build
```

`docker-compose.yml` wires the three services together and overrides `MCP_URL` so the backend
reaches the MCP server by its compose service name (`http://mcp_server:8001/mcp`).

## Configuration

Each service reads a `.env` file (copy from its `.env.example`). Config is loaded via
`pydantic-settings`.

### `backend/.env`

| Variable        | Default                      | What it does                                                        |
|-----------------|------------------------------|---------------------------------------------------------------------|
| `LLM_PROVIDER`  | `openai`                     | Provider passed to `init_chat_model` (see swap table below).        |
| `LLM_MODEL`     | `gpt-4o`                     | Model id for that provider.                                         |
| `OPENAI_API_KEY`| —                            | Standard key var for whichever provider you chose.                  |
| `MCP_URL`       | `http://localhost:8001/mcp`  | Where the backend finds the MCP server.                            |
| `CORS_ORIGINS`  | `http://localhost:5173`      | Comma-separated allowed origins (the Vite dev server).             |

### `mcp_server/.env`

| Variable                | Default   | What it does                                  |
|-------------------------|-----------|-----------------------------------------------|
| `SPOTIFY_CLIENT_ID`     | —         | From your Spotify app dashboard.              |
| `SPOTIFY_CLIENT_SECRET` | —         | From your Spotify app dashboard.              |
| `MCP_HOST`              | `0.0.0.0` | Bind host for the FastMCP server.             |
| `MCP_PORT`              | `8001`    | Bind port; the MCP endpoint is `/mcp`.        |

### `frontend/.env`

| Variable             | Default                  | What it does                          |
|----------------------|--------------------------|---------------------------------------|
| `VITE_API_BASE_URL`  | `http://localhost:8000`  | Backend base URL the UI calls.        |

## Swapping the LLM provider

Change two env vars in `backend/.env` (and install that provider's integration package):

| Provider  | `LLM_PROVIDER` | `LLM_MODEL`           | Package              | Key env var         |
|-----------|----------------|-----------------------|----------------------|---------------------|
| OpenAI    | `openai`       | `gpt-4o`              | `langchain-openai`   | `OPENAI_API_KEY`    |
| Anthropic | `anthropic`    | `claude-opus-4-8`     | `langchain-anthropic`| `ANTHROPIC_API_KEY` |
| Ollama    | `ollama`       | `llama3.1`            | `langchain-ollama`   | (local)             |

No agent code changes — the provider factory in [backend/app/llm.py](backend/app/llm.py) is the
only swap point (it calls `init_chat_model`, which resolves the right LangChain integration from
`LLM_PROVIDER`).

## HTTP API reference

The backend exposes two endpoints.

### `GET /health`
Liveness check. Returns `{"status": "ok"}`.

### `POST /chat`
Runs one agent turn and streams the result as **Server-Sent Events** (`text/event-stream`).

Request body:
```json
{ "session_id": "uuid-string", "message": "Recommend songs like Tame Impala" }
```

`session_id` is the conversation key — reuse it across turns to keep memory; use a fresh one to
start clean. SSE event types emitted (see [backend/app/routes/chat.py](backend/app/routes/chat.py)):

| Event        | `data` payload                  | Meaning                                  |
|--------------|---------------------------------|------------------------------------------|
| `token`      | `{ "text": "..." }`             | An LLM text delta (stream these to UI).  |
| `tool_start` | `{ "name": "...", "input": … }` | The agent invoked a Spotify MCP tool.    |
| `tool_end`   | `{ "name": "..." }`             | That tool finished.                      |
| `done`       | `{}`                            | The turn completed.                      |
| `error`      | `{ "message": "..." }`          | A failure, surfaced instead of dropping. |

## MCP tools reference

Defined in [mcp_server/tools.py](mcp_server/tools.py). Only **non-deprecated** Spotify endpoints
are exposed. Every tool also accepts an optional `user_token` — unused in Phase 1 (Client
Credentials), present so Phase-2 per-user OAuth is purely additive. All tools return normalized
dicts (see [mcp_server/spotify/normalize.py](mcp_server/spotify/normalize.py)).

| Tool                 | Args                                | Returns / use                                                                 |
|----------------------|-------------------------------------|-------------------------------------------------------------------------------|
| `search`             | `query`, `type` (`track`/`artist`/`album`), `limit` | **Primary discovery tool.** Put filters in `query`: `artist:"…"`, `genre:"…"`, `year:2018-2024`, `track:"…"`. |
| `get_artist`         | `artist_id`                         | Single artist incl. `genres` + `popularity` — use genres as search seeds.     |
| `get_artist_albums`  | `artist_id`, `limit`                | Albums + singles, to dig into a seed artist's catalogue.                      |
| `get_album_tracks`   | `album_id`, `limit`                 | An album's tracks (simplified; no per-track art).                            |
| `get_track`          | `track_id`                          | Full detail for one track (album art, preview URL, duration).                |

Spotify access details live in [mcp_server/spotify/](mcp_server/spotify/): `client.py` (async
httpx transport, 429 `Retry-After` backoff, one-shot 401 token refresh), `auth.py` (Client
Credentials token cache with refresh skew), `normalize.py` (payload trimming).

## Testing — tool-call evaluation

[tests/run_tool_eval.py](tests/run_tool_eval.py) is a harness that checks **which** Spotify tools
the agent decides to call for a range of prompts. It POSTs each prompt in
[tests/test_prompts.jsonl](tests/test_prompts.jsonl) to a running backend and tallies the
`tool_start` events (it does not instrument the agent — it just listens to the SSE stream). Each
prompt runs with a fresh `session_id` so memory doesn't leak between cases.

The prompt set spans four categories with `expected_tools` annotations: `none` (off-topic /
capability questions → 0 tools), `single` (one `search`), `multi` (artist lookup + searches), and
`deep` (album exploration). The report prints per-prompt tool counts and an aggregate summary;
it exits non-zero only on transport/connection failures, not on expected-vs-actual mismatches.

Run it with **both servers up** and the backend venv active (for `httpx` + `httpx_sse`):
```bash
python tests/run_tool_eval.py
python tests/run_tool_eval.py --base-url http://localhost:8000 --prompts tests/test_prompts.jsonl
```

## Logging & observability

Both Python services log to the terminal **and** a rotating file (1 MB × 3 backups), configured
at import time so a bare `python server.py` / `uvicorn app.main:app` captures everything:

- Backend → `backend/logs/backend.log`
- MCP server → `mcp_server/logs/mcp.log`

The MCP server logs every tool invocation with its arguments (a `_log_call` helper in
[mcp_server/tools.py](mcp_server/tools.py), with `user_token` omitted), so the MCP log is the
first place to look when debugging what the agent asked Spotify for. The `logs/` directories are
git-ignored.

## Project layout

| Path          | What it is                                                             |
|---------------|-----------------------------------------------------------------------|
| `mcp_server/` | FastMCP server wrapping Spotify (Client Credentials, read-only tools). |
| `backend/`    | FastAPI + LangGraph ReAct agent, SSE chat, per-session memory.         |
| `frontend/`   | React/Vite streaming chat UI.                                          |
| `tests/`      | Tool-call evaluation harness + prompt suite.                          |

Key files within each service:

```
mcp_server/
  server.py            FastMCP init, logging, run(transport="streamable-http")
  tools.py             @mcp.tool definitions (search, get_artist, …) + _log_call
  config.py            Spotify creds, host/port (pydantic-settings)
  spotify/
    client.py          async Spotify API client (token inject, 429/401 handling)
    auth.py            Client Credentials token cache
    normalize.py       trim Spotify payloads → compact dicts

backend/app/
  main.py              FastAPI app, CORS, logging, lifespan (builds agent once)
  config.py            LLM_PROVIDER / LLM_MODEL / MCP_URL / CORS_ORIGINS
  llm.py               provider factory (init_chat_model) — single swap point
  agent.py             create_agent (ReAct) + MemorySaver
  prompts.py           RECOMMENDATION_AGENT_SYSTEM_PROMPT
  mcp_client.py        MultiServerMCPClient → LangChain tools
  schemas.py           ChatRequest
  routes/chat.py       POST /chat → SSE stream

frontend/src/
  App.jsx              chat UI (renders Markdown + inline album art)
  api.js               streamChat(): POST /chat, parse SSE
  hooks/useChat.js     session_id persistence + message state
  components/TrackCard.jsx   (prepared for structured track output)
  styles.css           chat styling
```

## Roadmap (Phase 2)

Per-user OAuth (Authorization Code + PKCE) to **create playlists in the user's account**. The
seams are already in place: every MCP tool accepts an optional `user_token`, and
`SpotifyClient` passes user tokens straight through (never caching them). See PLAN.md.