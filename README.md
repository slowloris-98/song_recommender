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

## Swapping the LLM provider

Change two env vars in `backend/.env` (and install that provider's integration package):

| Provider  | `LLM_PROVIDER` | `LLM_MODEL`           | Package              | Key env var         |
|-----------|----------------|-----------------------|----------------------|---------------------|
| OpenAI    | `openai`       | `gpt-4o`              | `langchain-openai`   | `OPENAI_API_KEY`    |
| Anthropic | `anthropic`    | `claude-opus-4-8`     | `langchain-anthropic`| `ANTHROPIC_API_KEY` |
| Ollama    | `ollama`       | `llama3.1`            | `langchain-ollama`   | (local)             |

No agent code changes — the provider factory in `backend/app/llm.py` is the only swap point.

## Project layout

| Path          | What it is                                                             |
|---------------|-----------------------------------------------------------------------|
| `mcp_server/` | FastMCP server wrapping Spotify (Client Credentials, read-only tools). |
| `backend/`    | FastAPI + LangGraph ReAct agent, SSE chat, per-session memory.         |
| `frontend/`   | React/Vite streaming chat UI.                                          |

## Roadmap (Phase 2)

Per-user OAuth (Authorization Code + PKCE) to **create playlists in the user's account**. The
seams are already in place: every MCP tool accepts an optional `user_token`. See PLAN.md.
