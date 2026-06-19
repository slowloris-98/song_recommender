"""FastAPI app: CORS + lifespan wiring.

On startup we connect to the MCP server, load its Spotify tools, build the LLM and the
agent once, and stash the agent on app.state for the chat route to reuse.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent import build_agent
from .config import settings
from .llm import build_llm
from .mcp_client import build_mcp_client
from .routes.chat import router as chat_router


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
