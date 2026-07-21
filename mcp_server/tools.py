"""MCP tool definitions wrapping the Spotify Web API.

Only NON-deprecated endpoints are exposed (verified against the Spotify OpenAPI schema).
There is no recommendations endpoint and no artist-top-tracks endpoint available to a new
app, so `search` is the backbone of recommendation composition.

The batched discovery tools (`genres_to_artists`, `artists_to_tracks`) each issue many Spotify
calls and run them CONCURRENTLY. That is deliberate: the agent composes them, and a singular
tool would force it into ~44 sequential calls (and therefore ~44 LLM roundtrips) for one mood
request. Batched + concurrent, the same work is 3 tool calls in ~2s.

Two Spotify constraints shape everything here:
  * `limit` is capped at 10 per request (11+ returns 400 Invalid limit), so larger counts are
    fetched by paging with `offset` (range 0-1000).
  * Genre is an ARTIST attribute — no track-level genre exists — so genre lookups use
    type=artist, which yields far more distinct artists than type=track.

Every tool accepts an optional `user_token`. It is unused in Phase 1 (Client Credentials),
but exists from day one so Phase-2 per-user OAuth (playlist writes) is purely additive.
"""

import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from config import settings
from spotify import normalize
from spotify.client import SpotifyClient

_spotify: SpotifyClient | None = None

logger = logging.getLogger("spotify.tools")

# Spotify rejects limit > 10 on /search with "400 Invalid limit".
_MAX_PAGE = 10


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


def _pages(wanted: int) -> list[tuple[int, int]]:
    """Split a desired result count into (limit, offset) pages of at most _MAX_PAGE."""
    pages, offset = [], 0
    while offset < wanted:
        pages.append((min(_MAX_PAGE, wanted - offset), offset))
        offset += _MAX_PAGE
    return pages


async def _gather(coros: list) -> list:
    """Run coroutines concurrently under the configured concurrency cap.

    Exceptions are returned rather than raised so one failed page (a rate limit, an odd
    artist name) cannot sink the whole fan-out.
    """
    sem = asyncio.Semaphore(settings.discovery_concurrency)

    async def _guarded(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*(_guarded(c) for c in coros), return_exceptions=True)


def _items(result: object, key: str) -> list[dict]:
    """Pull `<key>.items` out of a search payload, tolerating errors and null entries.

    Spotify pads some result sets with nulls (deprecated playlist entries do this), and
    `_gather` hands back exceptions, so both are filtered here.
    """
    if isinstance(result, BaseException) or not isinstance(result, dict):
        return []
    return [i for i in (result.get(key) or {}).get("items", []) if i]


def _round_robin(tracks: list[dict]) -> list[dict]:
    """Interleave tracks so consecutive entries come from different artists.

    Spotify orders results by relevance/popularity, which clusters one artist's catalogue
    together; taking the head of that list would return 10 tracks by 2 artists. Interleaving
    makes artist diversity deterministic instead of leaving it to prompt instructions.
    """
    by_artist: dict[str, list[dict]] = {}
    for t in tracks:
        artist = (t.get("artists") or ["?"])[0]
        by_artist.setdefault(artist, []).append(t)

    ordered: list[dict] = []
    while by_artist:
        for artist in list(by_artist):
            ordered.append(by_artist[artist].pop(0))
            if not by_artist[artist]:
                del by_artist[artist]
    return ordered


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

        `type` is one of "track", "artist", or "album". Mainly useful as a RESOLVER — e.g.
        finding which artist recorded a named track. For building recommendations prefer the
        batched tools (`genres_to_artists`, `artists_to_tracks`), which fan out concurrently.

        `limit` is capped at 10 by Spotify. Returns a list of normalized items.
        """
        _log_call("search", query=query, type=type, limit=limit)
        data = await _spotify.get(
            "/search",
            params={"q": query, "type": type, "limit": min(limit, _MAX_PAGE)},
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
    async def genres_to_artists(
        genres: list[str],
        per_genre: int | None = None,
        user_token: str | None = None,
    ) -> list[dict]:
        """Find artists belonging to each of the given genres. Pass ALL genres at once.

        Genre is an artist-level attribute in Spotify, so this is the correct way to explore a
        genre: it returns many DISTINCT artists, whereas searching tracks by genre returns the
        same one or two popular artists repeatedly.

        Every genre is searched concurrently, so passing 4 genres costs one tool call, not four.
        Results are deduplicated by artist id; each artist carries the `genre` that found it, so
        you can pass that straight to `artists_to_tracks`.
        """
        genres = genres[: settings.max_genres_per_call]
        want = per_genre or settings.artists_per_genre
        _log_call("genres_to_artists", genres=genres, per_genre=want)

        artists: list[dict] = []
        seen: set[str] = set()
        per_genre_count: dict[str, int] = {g: 0 for g in genres}

        def _add(raw: dict, genre: str) -> None:
            if raw and raw.get("id") and raw["id"] not in seen:
                seen.add(raw["id"])
                artists.append({**normalize.artist(raw), "genre": genre})
                per_genre_count[genre] += 1

        # Pass 1: ask for artists directly — the semantically correct query.
        jobs, origin = [], []
        for genre in genres:
            for limit, offset in _pages(want):
                jobs.append(
                    _spotify.get(
                        "/search",
                        params={
                            "q": f'genre:"{genre}"',
                            "type": "artist",
                            "limit": limit,
                            "offset": offset,
                        },
                        user_token=user_token,
                    )
                )
                origin.append(genre)
        for genre, result in zip(origin, await _gather(jobs)):
            for raw in _items(result, "artists"):
                _add(raw, genre)

        # Pass 2: top up the genres that came back thin. type=artist is sparse for a lot of
        # tags — "ambient" returns 0 artists and "shoegaze"/"trap"/"post-punk" return 1 — while
        # a track search on the same tag yields 15-24 distinct artists. Harvesting the artists
        # off those tracks keeps every genre usable.
        thin = [g for g in genres if per_genre_count[g] < want]
        if thin:
            jobs, origin = [], []
            for genre in thin:
                for limit, offset in _pages(want):
                    jobs.append(
                        _spotify.get(
                            "/search",
                            params={
                                "q": f'genre:"{genre}"',
                                "type": "track",
                                "limit": limit,
                                "offset": offset,
                            },
                            user_token=user_token,
                        )
                    )
                    origin.append(genre)
            for genre, result in zip(origin, await _gather(jobs)):
                for track in _items(result, "tracks"):
                    if per_genre_count[genre] >= want:
                        break
                    for raw in track.get("artists") or []:
                        _add(raw, genre)

            logger.info("   genres_to_artists: topped up thin genres %s", thin)

        logger.info(
            "   genres_to_artists: %d distinct artists %s",
            len(artists),
            {g: per_genre_count[g] for g in genres},
        )
        return artists

    @mcp.tool()
    async def artists_to_tracks(
        artists: list[str],
        genre: str | None = None,
        year: str | None = None,
        per_artist: int | None = None,
        user_token: str | None = None,
    ) -> list[dict]:
        """Get tracks for each of the given artists. Pass ALL artists at once.

        This is the workhorse for both kinds of request:
          - "songs BY <artist>"   -> artists_to_tracks(["<artist>"])
          - genre discovery       -> feed it the artists from `genres_to_artists`

        Adding `genre` narrows each artist's catalogue to that side of their work (e.g. Lady Gaga
        + jazz returns "Cheek To Cheek", not "Bad Romance") and returns MORE tracks than an
        artist-only lookup. `year` accepts "1991" or a range like "2018-2024".

        Every artist is searched concurrently. Results are deduplicated by track id and then
        interleaved so consecutive tracks come from different artists — take the first N for a
        varied set.
        """
        want = per_artist or settings.tracks_per_artist
        _log_call(
            "artists_to_tracks", artists=artists, genre=genre, year=year, per_artist=want
        )

        filters = ""
        if genre:
            filters += f' genre:"{genre}"'
        if year:
            filters += f" year:{year}"

        jobs = []
        for artist in artists:
            for limit, offset in _pages(want):
                jobs.append(
                    _spotify.get(
                        "/search",
                        params={
                            "q": f'artist:"{artist}"{filters}',
                            "type": "track",
                            "limit": limit,
                            "offset": offset,
                        },
                        user_token=user_token,
                    )
                )

        results = await _gather(jobs)
        tracks, seen = [], set()
        for result in results:
            for raw in _items(result, "tracks"):
                if raw["id"] in seen:
                    continue
                seen.add(raw["id"])
                tracks.append(normalize.track(raw))

        ordered = _round_robin(tracks)
        logger.info(
            "   artists_to_tracks: %d calls -> %d unique tracks across %d artists",
            len(jobs),
            len(ordered),
            len({t["artists"][0] for t in ordered if t.get("artists")}),
        )
        return ordered

    @mcp.tool()
    async def album_to_tracks(
        album: str,
        user_token: str | None = None,
    ) -> list[dict]:
        """Get every track on an album, given the album NAME (not an id).

        Resolves the name to an album, then returns its track listing — use this when the user
        names an album and wants what is on it.
        """
        _log_call("album_to_tracks", album=album)
        found = await _spotify.get(
            "/search",
            params={"q": f'album:"{album}"', "type": "album", "limit": 1},
            user_token=user_token,
        )
        items = _items(found, "albums")
        if not items:
            logger.info("   album_to_tracks: no album matched %r", album)
            return []

        found_album = items[0]
        # Unlike /search, this endpoint accepts a larger limit, so one call covers most albums.
        data = await _spotify.get(
            f"/albums/{found_album['id']}/tracks",
            params={"limit": 50},
            user_token=user_token,
        )
        tracks = [normalize.track(t) for t in data.get("items", []) if t]
        # Album-track entries omit the parent album, so fill it in from what we resolved.
        for t in tracks:
            t["album"] = found_album.get("name")
        logger.info(
            "   album_to_tracks: %r -> %d tracks", found_album.get("name"), len(tracks)
        )
        return tracks

    @mcp.tool()
    async def get_artist(artist_id: str, user_token: str | None = None) -> dict:
        """Get a single artist by Spotify ID (name, url).

        NOTE: `genres` and `popularity` come back empty — Spotify removed those fields from
        artist objects. There is no API route from an artist to its genres, so do NOT call this
        hoping to seed a genre search; choose genres yourself and use `genres_to_artists`.
        """
        _log_call("get_artist", artist_id=artist_id)
        return normalize.artist(
            await _spotify.get(f"/artists/{artist_id}", user_token=user_token)
        )

    @mcp.tool()
    async def get_artist_albums(
        artist_id: str, limit: int = _MAX_PAGE, user_token: str | None = None
    ) -> list[dict]:
        """Get an artist's albums and singles. Use to dig into a seed artist's catalogue,
        then call `get_album_tracks` to pull specific songs from an album.

        `limit` is capped at 10 — this endpoint rejects anything larger."""
        _log_call("get_artist_albums", artist_id=artist_id, limit=limit)
        data = await _spotify.get(
            f"/artists/{artist_id}/albums",
            params={
                "limit": min(limit, _MAX_PAGE),
                "include_groups": "album,single",
            },
            user_token=user_token,
        )
        return [normalize.album(a) for a in data.get("items", []) if a]

    @mcp.tool()
    async def get_album_tracks(
        album_id: str, limit: int = 50, user_token: str | None = None
    ) -> list[dict]:
        """Get the tracks on an album. These simplified tracks omit the album name; use
        `get_track` or `search` if you need that per-track detail."""
        _log_call("get_album_tracks", album_id=album_id, limit=limit)
        data = await _spotify.get(
            f"/albums/{album_id}/tracks",
            params={"limit": limit},
            user_token=user_token,
        )
        return [normalize.track(t) for t in data.get("items", []) if t]

    @mcp.tool()
    async def get_track(track_id: str, user_token: str | None = None) -> dict:
        """Get full detail for a SINGLE track by Spotify ID (album name, duration).
        Note: batch track lookup is deprecated — fetch one track at a time."""
        _log_call("get_track", track_id=track_id)
        return normalize.track(
            await _spotify.get(f"/tracks/{track_id}", user_token=user_token)
        )
