"""FastAPI app: CORS + lifespan wiring.

On startup we connect to the MCP server, load its Spotify tools, build the LLM and the
agent once, and stash the agent on app.state for the chat route to reuse.
"""

import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent import build_agent
from .config import settings
from .llm import build_llm
from .mcp_client import build_mcp_client
from .routes.chat import router as chat_router

# Send root logs to both the terminal and a rotating file under backend/logs/. Creating
# the dir here means `uvicorn app.main:app` captures everything without any extra setup.
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"

_file_handler = RotatingFileHandler(
    _LOG_DIR / "backend.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))

# No-op if the runtime already configured root logging, so it won't fight an existing
# setup or change its format.
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    handlers=[logging.StreamHandler(), _file_handler],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_client = build_mcp_client()
    tools = await mcp_client.get_tools()
    llm = build_llm()
    app.state.agent = build_agent(llm, tools)
    yield


app = FastAPI(title="Song Recommender Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
