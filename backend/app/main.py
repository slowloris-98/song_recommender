"""FastAPI app: CORS + lifespan wiring.

On startup we connect to the MCP server, load its Spotify tools, build the LLM and the
agent once, and stash the agent on app.state for the chat route to reuse.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent import build_agent
from .config import settings
from .llm import build_llm
from .local_tools import mood_to_genres
from .mcp_client import build_mcp_client
from .routes.chat import router as chat_router

# Send root logs to both the terminal and a rotating file under the project-root logs/.
# It's kept OUTSIDE backend/ on purpose: `uvicorn --reload` watches backend/, so a log file
# in there turns every write into a "change detected" — and since watchfiles' own log lines
# propagate to this handler, that becomes a self-sustaining feedback loop.
_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"

_file_handler = RotatingFileHandler(
    _LOG_DIR / "backend.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))

# No-op if the runtime already configured root logging, so it won't fight an existing
# setup or change its format.
logging.basicConfig(
    level=settings.log_level.upper(),
    format=_LOG_FORMAT,
    handlers=[logging.StreamHandler(), _file_handler],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_client = build_mcp_client()
    # On a free-tier host the MCP server may be spun down and take ~1 min to wake, so retry
    # the initial tool-load instead of crashing the backend boot on the cold-start race.
    tools = None
    for attempt in range(1, 7):  # ~90s total: enough for a cold MCP to wake
        try:
            tools = await mcp_client.get_tools()
            break
        except Exception as exc:  # noqa: BLE001 - retry any startup-time MCP failure
            logger.warning("MCP not ready (attempt %d/6): %s", attempt, exc)
            await asyncio.sleep(15)
    if tools is None:
        raise RuntimeError("MCP server unreachable at startup")
    # `mood_to_genres` runs locally (no Spotify call), so it lives beside the genre list rather
    # than in the MCP server. The agent sees it as just another tool.
    tools = [*tools, mood_to_genres]
    logger.info("agent tools: %s", [t.name for t in tools])
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
