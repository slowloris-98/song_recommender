"""Connects to the FastMCP Spotify server and loads its tools as LangChain tools.

`MultiServerMCPClient.get_tools()` returns native LangChain `StructuredTool`s, so the
agent can call them directly. Transport is streamable-http to match the MCP server.
"""

from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import settings


def build_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "spotify": {
                "url": settings.mcp_url,
                "transport": "streamable_http",
            }
        }
    )
