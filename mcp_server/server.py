"""FastMCP server exposing Spotify tools over streamable-http.

Run from this directory:  python server.py
The MCP endpoint is served at  http://<MCP_HOST>:<MCP_PORT>/mcp
"""

from mcp.server.fastmcp import FastMCP

import tools
from config import settings
from spotify.client import SpotifyClient


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
