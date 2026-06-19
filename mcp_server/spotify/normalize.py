"""Trim large Spotify payloads into compact dicts.

Raw Spotify objects are huge and would bloat the agent's token usage and confuse tool
reasoning. Every MCP tool returns these normalized shapes instead.
"""


def _images(obj: dict) -> list[str]:
    return [img["url"] for img in (obj.get("images") or []) if img.get("url")]


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
        "images": _images(a),
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
        "images": _images(al),
    }


def track(t: dict | None) -> dict | None:
    if not t:
        return None
    al = t.get("album") or {}
    return {
        "id": t.get("id"),
        "name": t.get("name"),
        "artists": [ar.get("name") for ar in t.get("artists", [])],
        "album": al.get("name"),
        # Album-track endpoints omit `album`, so images may be empty there.
        "images": _images(al),
        "url": _spotify_url(t),
        "preview_url": t.get("preview_url"),
        "duration_ms": t.get("duration_ms"),
    }
