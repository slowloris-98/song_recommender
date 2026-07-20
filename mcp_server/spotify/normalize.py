"""Trim large Spotify payloads into compact dicts.

Raw Spotify objects are huge and would bloat the agent's token usage and confuse tool
reasoning. Every MCP tool returns these normalized shapes instead.

Album-art `images` are deliberately excluded: they were ~48% of a track payload (three long
CDN URLs each), the agent never reasons over them, and every tool result is replayed into the
LLM context on each turn by the checkpointer. Nothing renders them today either — tool output
never reaches the frontend. If a structured track list is ever streamed to the UI, re-source
art on a path that bypasses the LLM context.
"""


def _spotify_url(obj: dict) -> str | None:
    return (obj.get("external_urls") or {}).get("spotify")


def artist(a: dict | None) -> dict | None:
    if not a:
        return None
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "genres": a.get("genres", []),
        "popularity": a.get("popularity"),
        "url": _spotify_url(a),
    }


def album(al: dict | None) -> dict | None:
    if not al:
        return None
    return {
        "id": al.get("id"),
        "name": al.get("name"),
        "artists": [ar.get("name") for ar in al.get("artists", [])],
        "release_date": al.get("release_date"),
        "total_tracks": al.get("total_tracks"),
        "url": _spotify_url(al),
    }


def track(t: dict | None) -> dict | None:
    if not t:
        return None
    al = t.get("album") or {}
    return {
        "id": t.get("id"),
        "name": t.get("name"),
        "artists": [ar.get("name") for ar in t.get("artists", [])],
        # Album-track endpoints omit `album`, so this may be None there.
        "album": al.get("name"),
        "url": _spotify_url(t),
        "preview_url": t.get("preview_url"),
        "duration_ms": t.get("duration_ms"),
    }
