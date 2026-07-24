"""Dev-time probe: how much does each half of `genres_to_artists` actually contribute?

NOT part of the server runtime. `genres_to_artists` searches `genre:"<g>"` with
type=artist,track and harvests artists from both blocks — the tagged artists first, then the
artists behind the matching tracks. The obvious objection is that the second half is
redundant: if a track matches the genre because its artist carries the tag, those artists
should already be in the artist block.

This measures whether that holds. For each vetted genre it runs both searches at the depth
the tool actually uses (settings.artists_per_genre) and reports the set difference:

    artist_only  artists only the artist block has
    overlap      artists in both  -> the genuinely redundant part
    track_only   artists only the track block can reach

Run 2026-07-21 (40 genres, want=10): mean overlap 1.1, mean track_only 8.2, and type=artist
returned ZERO artists for 13 genres. The two blocks are near-disjoint, so both are load-bearing.

Note VETTED_GENRES was built by scripts/validate_genres.py, which probes with type=track
only — no genre there has ever been checked against type=artist. That is the bias this script
exists to quantify, and it explains most of the 13 zeroes.

Usage (from the repo root):
    python scripts/compare_genre_search.py

Reads SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET from mcp_server/.env (same credentials the
MCP server uses).
"""

import base64
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.genres import VETTED_GENRES  # noqa: E402

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"

# Mirror the runtime: settings.artists_per_genre=10 fetched in pages of at most 10.
WANT = 10
MAX_PAGE = 10


def _get_token(client: httpx.Client, client_id: str, client_secret: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = client.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _pages(wanted: int) -> list[tuple[int, int]]:
    """Same paging split as mcp_server/tools.py so depths are comparable."""
    pages, offset = [], 0
    while offset < wanted:
        pages.append((min(MAX_PAGE, wanted - offset), offset))
        offset += MAX_PAGE
    return pages


def _search(client: httpx.Client, genre: str, type_: str, token: str) -> tuple[set[str], int]:
    """Return (distinct artist ids, envelope total) for one genre/type at runtime depth."""
    ids: set[str] = set()
    total = 0
    for limit, offset in _pages(WANT):
        resp = client.get(
            SEARCH_URL,
            params={
                "q": f'genre:"{genre}"',
                "type": type_,
                "limit": limit,
                "offset": offset,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        block = resp.json().get(f"{type_}s") or {}
        total = block.get("total", 0)
        for item in block.get("items") or []:
            if not item:
                continue
            if type_ == "artist":
                if item.get("id"):
                    ids.add(item["id"])
            else:  # track -> harvest its artists, exactly as pass 2 does
                for raw in item.get("artists") or []:
                    if raw and raw.get("id"):
                        ids.add(raw["id"])
    return ids, total


def main() -> None:
    load_dotenv(REPO_ROOT / "mcp_server" / ".env")
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET (checked mcp_server/.env).")

    rows = []
    with httpx.Client(timeout=15.0) as client:
        token = _get_token(client, client_id, client_secret)
        header = (
            f"{'genre':<20} {'a_cnt':>5} {'t_cnt':>5} "
            f"{'a_only':>6} {'overlap':>7} {'t_only':>6} {'a_total':>8} {'t_total':>8}"
        )
        print(header)
        print("-" * len(header))
        for genre in VETTED_GENRES:
            a_ids, a_total = _search(client, genre, "artist", token)
            t_ids, t_total = _search(client, genre, "track", token)
            a_only = len(a_ids - t_ids)
            overlap = len(a_ids & t_ids)
            t_only = len(t_ids - a_ids)
            rows.append((genre, len(a_ids), len(t_ids), a_only, overlap, t_only))
            print(
                f"{genre:<20} {len(a_ids):>5} {len(t_ids):>5} "
                f"{a_only:>6} {overlap:>7} {t_only:>6} {a_total:>8} {t_total:>8}"
            )

    n = len(rows)
    zero_artist = sum(1 for r in rows if r[1] == 0)
    thin_artist = sum(1 for r in rows if r[1] < WANT)
    mean_t_only = sum(r[5] for r in rows) / n
    mean_overlap = sum(r[4] for r in rows) / n
    total_t_only = sum(r[5] for r in rows)

    print(f"\ngenres probed:                  {n}")
    print(f"type=artist returned 0:         {zero_artist}")
    print(f"type=artist under quota ({WANT}):  {thin_artist}")
    print(f"mean overlap (redundant):       {mean_overlap:.1f}")
    print(f"mean track_only (pass 2 gain):  {mean_t_only:.1f}")
    print(f"total track_only across genres: {total_t_only}")

    if total_t_only == 0:
        print("\n=> Pass 2 adds nothing. Subset hypothesis holds; delete it.")
    elif zero_artist > n / 3:
        print("\n=> Pass 1 fails on many genres. Consider making type=track the primary search.")
    else:
        print("\n=> Both passes contribute. Keep both, merge into one type=artist,track request.")


if __name__ == "__main__":
    main()
