# Song Recommender — Architecture & Build Plan

> Living project plan. Tick items in the **Progress checklist** as work lands.

## Context

A song-recommendation system: a user converses in a React webapp about artists/albums/tracks they like;
a FastAPI backend runs an LLM agent that decides which Spotify operations to call; an MCP server (FastMCP)
exposes Spotify API endpoints as tools.

Confirmed decisions:
- **Spotify scope:** read-only recommendations first (app-level auth), architected so per-user OAuth
  playlist creation layers on later without a rewrite.
- **Interaction:** multi-turn streaming chat (SSE) with per-session conversation memory.
- **LLM:** OpenAI by default, behind a provider abstraction so more providers are config-only.

**Status (2026-07-14):** Phase 1 is built and verified end-to-end (read-only recommendations work in the
browser) and **deployed to Render** (free tier) — see **Deployment** below. Post-scaffolding hardening
landed earlier — see **Phase 1 hardening**. Phase 2 (OAuth + playlist writes) remains deferred.

---

## Architecture review — gaps designed around

1. **Spotify auth is two worlds.** Read-only = Client Credentials (one app token the MCP server manages).
   Playlist writes = Authorization Code + PKCE (user login, token store/refresh, user token threaded
   backend → MCP). MCP tools take an optional `user_token` arg from day one so OAuth is additive.

2. **The deprecation net is wide — `/search` is the backbone.** Verified against the Spotify OpenAPI schema.
   For a new app, deprecated endpoints are effectively unavailable:
   - **Do NOT use:** `GET /recommendations` (absent), `GET /artists/{id}/top-tracks`,
     `GET /artists/{id}/related-artists`, batch `GET /tracks|/artists|/albums`, audio-features/analysis,
     all browse endpoints (`/browse/featured-playlists`, `/browse/categories`).
   - **Available:** `GET /search`, `GET /artists/{id}`, `GET /artists/{id}/albums`,
     `GET /albums/{id}/tracks`, `GET /tracks/{id}` (single).
   - Recommendations are composed with `/search` as the engine: search seed artist → `get_artist` genres →
     `search` tracks by `genre:"…" year:…` → optionally albums → album tracks → dedupe.
   - `GET /browse/new-releases` and `audio-features` weren't visible in the fetched schema excerpt — verify
     at build time before relying on them.

3. **MCP transport = streamable-http** (separate service, matches the diagram). Backend connects via
   `langchain-mcp-adapters` `MultiServerMCPClient`.

4. **Streaming + session memory.** SSE from FastAPI; conversation keyed by frontend-generated `session_id`.

5. **Trim tool results** to compact shapes (`id, name, artists, album, url, preview_url`) — raw Spotify
   payloads bloat tokens.

6. **Rate limits / 429.** MCP Spotify client honors `Retry-After`; caches app token (+ hot lookups).

7. **Provider abstraction** via `init_chat_model(model, model_provider=...)` driven by env.

8. **Cross-cutting:** CORS, `pydantic-settings` + `.env` per service, secrets handling.

---

## Folder structure

```
song_recommender/
├── backend/                      # FastAPI + LangGraph agent (OpenAI default)
│   ├── app/
│   │   ├── main.py               # FastAPI app, CORS, logging, lifespan: build MCP client + agent once
│   │   ├── config.py             # pydantic-settings: LLM_PROVIDER, LLM_MODEL, MCP_URL, keys
│   │   ├── llm.py                # provider factory -> init_chat_model(...)
│   │   ├── mcp_client.py         # MultiServerMCPClient -> MCP tools as LangChain tools
│   │   ├── agent.py              # create_agent(llm, tools, checkpointer=MemorySaver())
│   │   ├── prompts.py            # RECOMMENDATION_AGENT_SYSTEM_PROMPT (search-composition strategy)
│   │   ├── routes/chat.py        # POST /chat -> SSE stream; thread_id = session_id
│   │   └── schemas.py
│   ├── logs/                     # rotating backend.log (gitignored)
│   ├── requirements.txt
│   └── .env.example
├── mcp_server/                   # FastMCP server wrapping Spotify
│   ├── server.py                 # FastMCP("spotify"), logging, run(transport="streamable-http")
│   ├── spotify/
│   │   ├── client.py             # httpx; Client Credentials token + refresh; 429/Retry-After
│   │   ├── auth.py               # token cache; (Phase 2) user-token passthrough hook
│   │   └── normalize.py          # trim Spotify payloads -> compact dicts (incl. album-art images)
│   ├── tools.py                  # @mcp.tool primitives + _log_call() tool-call logging
│   ├── logs/                     # rotating mcp.log (gitignored)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                     # React (Vite)
│   ├── src/
│   │   ├── App.jsx               # chat UI; renders markdown + inline album art
│   │   ├── api.js                # POST /chat, consume SSE
│   │   ├── styles.css            # chat styling incl. album-art thumbnails
│   │   ├── hooks/useChat.js      # session_id mgmt + streaming state
│   │   └── components/           # TrackCard (ready for structured track output)
│   ├── package.json
│   └── .env.example
├── tests/
│   ├── run_tool_eval.py          # tool-call eval harness: replays prompts, tallies tool_start events
│   └── test_prompts.jsonl        # 12 categorized prompts (none/single/multi/deep)
├── docker-compose.yml
└── README.md
```

---

## Phase 1 (read-only recommendations)

**mcp_server:** Client Credentials token cache/refresh + 429 handling; normalize helpers; tools `search`,
`get_artist`, `get_artist_albums`, `get_album_tracks`, `get_track` (all with optional `user_token`);
FastMCP streamable-http. Prescriptive tool docstrings so the agent composes correctly. Do NOT add
`get_artist_top_tracks` or batch `get_tracks`.

**backend:** `config.py`, `llm.py` (provider factory — single swap point), `mcp_client.py`,
`agent.py` (`create_agent` + MemorySaver), `prompts.py` (search-based composition system prompt),
`routes/chat.py` (SSE `/chat`, `thread_id = session_id`), `main.py` (CORS + lifespan).

**frontend:** `useChat.js` (session_id + SSE), chat UI + `TrackCard`.

**Reuse:** `langchain-mcp-adapters`, `langchain`/`langgraph` `create_agent` + `MemorySaver`,
`init_chat_model`, `langchain-openai`, FastMCP `@mcp.tool` + `streamable-http`.

## Phase 1 hardening (post-scaffolding)

Work that landed after the initial scaffolding, while keeping Phase 1 read-only scope:
- **`create_agent` migration:** replaced the deprecated `create_react_agent` (langgraph) with
  `create_agent` (langchain 1.0).
- **Prompt extraction:** moved the system prompt inline-in-`agent.py` out to `prompts.py`
  (`RECOMMENDATION_AGENT_SYSTEM_PROMPT`) so it's versioned and editable in one place.
- **Logging / observability:** backend and MCP server both log to console + a rotating file
  (`backend/logs/backend.log`, `mcp_server/logs/mcp.log`; 1 MB × 3 backups). `tools.py` logs every
  tool call via `_log_call()` (args logged, `user_token` redacted).
- **Album art:** `normalize.py` now carries `images`; the frontend renders inline album-art thumbnails
  in assistant messages (`styles.css`).
- **Tool-eval harness:** `tests/run_tool_eval.py` replays `tests/test_prompts.jsonl` against the running
  backend's `/chat` SSE stream and tallies `tool_start` events per prompt — used to sanity-check that the
  agent composes the right number/kind of tool calls (categories: none / single / multi / deep). Needs
  `httpx` + `httpx_sse` and a running backend + MCP server.

## Phase 2 (deferred seams)

OAuth (`/auth/login`, `/auth/callback`, PKCE) + token store + "Login with Spotify" (scopes
`user-read-private`, `playlist-modify-public`, `playlist-modify-private`). Write tools using current paths:
`get_current_user` (`GET /me`), `create_playlist` (`POST /me/playlists`),
`add_tracks_to_playlist` (`POST /playlists/{id}/items`). Thread `user_token` through.

---

## Verification

1. MCP standalone: `search(query='genre:"indie" year:2020-2024', type='track')` + `get_artist` return
   normalized data — proves Client Credentials + normalization + search strategy.
2. Backend: `curl -N` SSE `/chat`; confirm multi-step tool calls + streamed list; follow-up with same
   `session_id` confirms memory. For a repeatable check, run `python tests/run_tool_eval.py` (backend +
   MCP must be up) to tally tool calls per prompt across the `test_prompts.jsonl` cases.
3. Frontend: chat end-to-end; streaming render + inline album art.
4. Provider swap: change `LLM_PROVIDER`/`LLM_MODEL`; agent runs unchanged.

---

## Progress checklist

**Step 0 — Tracking**
- [x] Copy plan into repo as `PLAN.md`
- [x] Save a `project`-type memory entry

**Phase 1 — scaffolding**
- [x] Repo skeleton: `backend/`, `mcp_server/`, `frontend/`, root `README.md`, `docker-compose.yml`
- [x] `.env.example` for each service

**Phase 1 — mcp_server**
- [x] `spotify/client.py`: Client Credentials token cache + refresh + 429/Retry-After
- [x] `spotify/normalize.py`: compact track/artist/album shapes
- [x] `tools.py`: `search`, `get_artist`, `get_artist_albums`, `get_album_tracks`, `get_track`
- [x] `server.py`: FastMCP streamable-http
- [ ] Verify build-time availability of `new-releases` before adding that tool

**Phase 1 — backend**
- [x] `config.py`, `llm.py` (provider factory), `mcp_client.py`
- [x] `agent.py`: agent + MemorySaver + composition system prompt
- [x] `routes/chat.py`: SSE `/chat` with `thread_id = session_id`
- [x] `main.py`: CORS + lifespan wiring

**Phase 1 — frontend**
- [x] `useChat.js`: session_id + SSE streaming
- [x] Chat UI + `TrackCard` component (ready for structured track output)
- [x] Inline album-art rendering in assistant messages

**Phase 1 — hardening**
- [x] Migrate `create_react_agent` → `create_agent` (deprecation fix)
- [x] Extract system prompt to `prompts.py`
- [x] Rotating-file logging for backend + MCP server; `_log_call()` tool-call logging
- [x] Tool-eval harness `tests/run_tool_eval.py` + `tests/test_prompts.jsonl`

**Phase 1 — verification**
- [x] Static: Python byte-compiles (3.12), file tree matches plan
- [x] Runtime: MCP standalone search/get_artist (with Spotify creds)
- [x] Runtime: Backend SSE + session memory (OpenAI key + MCP running)
- [x] Runtime: Frontend end-to-end (chat + album art render in browser)
- [ ] Runtime: Provider swap smoke test (non-OpenAI provider)

**Deployment (Render, free tier)**
- [x] `render.yaml` Blueprint: frontend static site + backend & MCP Docker web services
- [x] `$PORT` binding (MCP `server.py`, backend Dockerfile CMD) + resilient MCP-load retry in lifespan
- [x] Live end-to-end on Render — see README **Deploy to Render** for URLs and the hostname-suffix gotcha
- [ ] (optional) Swap `MemorySaver` → `PostgresSaver` so memory survives free-tier spin-down

**Phase 2 — deferred**
- [ ] OAuth + token store + "Login with Spotify"
- [ ] Write tools: `get_current_user`, `create_playlist`, `add_tracks_to_playlist`
- [ ] Thread `user_token` through chat → agent → MCP tools
