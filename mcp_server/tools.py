"""MCP tool definitions wrapping the Spotify Web API.

Only NON-deprecated endpoints are exposed (verified against the Spotify OpenAPI schema).
There is no recommendations endpoint and no artist-top-tracks endpoint available to a new
app, so `search` is the backbone of recommendation composition.

Every tool accepts an optional `user_token`. It is unused in Phase 1 (Client Credentials),
but exists from day one so Phase-2 per-user OAuth (playlist writes) is purely additive.
"""

import logging

from mcp.server.fastmcp import FastMCP

from spotify import normalize
from spotify.client import SpotifyClient

_spotify: SpotifyClient | None = None

logger = logging.getLogger("spotify.tools")


def _log_call(tool: str, **kwargs: object) -> None:
    """Emit one INFO line naming the tool being called (and its non-secret args).

    Shows up in the MCP server terminal so you can watch which tools the agent invokes.
    `user_token` is intentionally never logged.
    """
    args = ", ".join(f"{k}={v!r}" for k, v in kwargs.items() if v is not None)
    logger.info("-> tool call: %s(%s)", tool, args)


def set_client(client: SpotifyClient) -> None:
    global _spotify
    _spotify = client


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search(
        query: str,
        type: str = "track",
        limit: int = 10,
        user_token: str | None = None,
    ) -> list[dict]:
        """Search Spotify for tracks, artists, or albums. This is the PRIMARY discovery tool.

        Use Spotify search filters inside `query` to find candidates:
          - artist:"Tame Impala"
          - genre:"indie pop"
          - year:2020   or   year:2018-2024
          - track:"the less i know the better"

        `type` is one of "track", "artist", or "album". This replaces the deprecated
        recommendations and artist-top-tracks endpoints: compose recommendations by
        searching with genre/year/artist filters. Returns a list of normalized items.
        """
        _log_call("search", query=query, type=type, limit=limit)
        data = await _spotify.get(
            "/search",
            params={"q": query, "type": type, "limit": limit},
            user_token=user_token,
        )
        items = (data.get(f"{type}s") or {}).get("items", [])
        normalizer = {
            "track": normalize.track,
            "artist": normalize.artist,
            "album": normalize.album,
        }.get(type, normalize.track)
        return [normalizer(i) for i in items if i]

    @mcp.tool()
    async def get_artist(artist_id: str, user_token: str | None = None) -> dict:
        """Get a single artist by Spotify ID, including `genres` and `popularity`.

        Use the artist's genres as seeds for genre-based `search` to find similar music
        (e.g. search type=track with genre:"<one of the artist's genres>").
        """
        _log_call("get_artist", artist_id=artist_id)
        return normalize.artist(
            await _spotify.get(f"/artists/{artist_id}", user_token=user_token)
        )

    @mcp.tool()
    async def get_artist_albums(
        artist_id: str, limit: int = 20, user_token: str | None = None
    ) -> list[dict]:
        """Get an artist's albums and singles. Use to dig into a seed artist's catalogue,
        then call `get_album_tracks` to pull specific songs from an album."""
        _log_call("get_artist_albums", artist_id=artist_id, limit=limit)
        data = await _spotify.get(
            f"/artists/{artist_id}/albums",
            params={"limit": limit, "include_groups": "album,single"},
            user_token=user_token,
        )
        return [normalize.album(a) for a in data.get("items", []) if a]

    @mcp.tool()
    async def get_album_tracks(
        album_id: str, limit: int = 50, user_token: str | None = None
    ) -> list[dict]:
        """Get the tracks on an album. These simplified tracks lack album art; use
        `get_track` or `search` if you need full per-track detail (art, preview URL)."""
        _log_call("get_album_tracks", album_id=album_id, limit=limit)
        data = await _spotify.get(
            f"/albums/{album_id}/tracks",
            params={"limit": limit},
            user_token=user_token,
        )
        return [normalize.track(t) for t in data.get("items", []) if t]

    @mcp.tool()
    async def get_track(track_id: str, user_token: str | None = None) -> dict:
        """Get full detail for a SINGLE track by Spotify ID (album art, preview URL,
        duration). Note: batch track lookup is deprecated — fetch one track at a time."""
        _log_call("get_track", track_id=track_id)
        return normalize.track(
            await _spotify.get(f"/tracks/{track_id}", user_token=user_token)
        )
