"""FastMCP server exposing Spotify tools over streamable-http.

Run from this directory:  python server.py
The MCP endpoint is served at  http://<MCP_HOST>:<MCP_PORT>/mcp
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import tools
from config import settings
from spotify.client import SpotifyClient

# Send root logs (tool calls + framework INFO logs) to both the terminal and a rotating
# file under mcp_server/logs/. Creating the dir here means a bare `python server.py`
# captures everything without any extra setup.
_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"

_file_handler = RotatingFileHandler(
    _LOG_DIR / "mcp.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))

# No-op if the runtime already configured root logging, so it won't fight an existing
# setup or change its format.
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
    handlers=[logging.StreamHandler(), _file_handler],
)


def build_server() -> FastMCP:
    mcp = FastMCP("spotify", host=settings.mcp_host, port=settings.mcp_port)
    tools.set_client(
        SpotifyClient(settings.spotify_client_id, settings.spotify_client_secret)
    )
    tools.register_tools(mcp)
    return mcp


mcp = build_server()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
