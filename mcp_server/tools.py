"""MCP tool definitions wrapping the Spotify Web API.

Only NON-deprecated endpoints are exposed (verified against the Spotify OpenAPI schema).
There is no recommendations endpoint and no artist-top-tracks endpoint available to a new
app, so `search` is the backbone of recommendation composition.

Every tool accepts an optional `user_token`. It is unused in Phase 1 (Client Credentials),
but exists from day one so Phase-2 per-user OAuth (playlist writes) is purely additive.
"""

from mcp.server.fastmcp import FastMCP

from spotify import normalize
from spotify.client import SpotifyClient

_spotify: SpotifyClient | None = None


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
        return normalize.artist(
            await _spotify.get(f"/artists/{artist_id}", user_token=user_token)
        )

    @mcp.tool()
    async def get_artist_albums(
        artist_id: str, limit: int = 20, user_token: str | None = None
    ) -> list[dict]:
        """Get an artist's albums and singles. Use to dig into a seed artist's catalogue,
        then call `get_album_tracks` to pull specific songs from an album."""
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
        return normalize.track(
            await _spotify.get(f"/tracks/{track_id}", user_token=user_token)
        )
