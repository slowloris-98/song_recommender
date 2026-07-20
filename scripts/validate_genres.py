"""Dev-time builder/refresher for backend/app/genres.py's VETTED_GENRES.

NOT part of the server runtime. Spotify gives us no way to enumerate valid genre tags
(the `available-genre-seeds` endpoint is 404 and artist objects no longer carry `genres`),
so we validate a candidate list empirically: probe each tag with a `genre:"<g>"` track
search and keep the ones that return at least MIN_TOTAL results.

Usage (from the repo root):
    python scripts/validate_genres.py

Reads SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET from mcp_server/.env (same credentials the
MCP server uses). Prints a per-genre report and a ready-to-paste VETTED_GENRES block.
"""

import base64
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"

# Keep a genre only if `genre:"<g>"` returns at least this many tracks. Common genres return
# ~100 (Spotify's search cap); thin/misspelled tags return 0-4.
MIN_TOTAL = 20

# Superset of genres to test. Survivors become VETTED_GENRES. Add guesses freely here — the
# probe drops whatever Spotify doesn't recognize.
CANDIDATES = [
    "pop", "rock", "indie pop", "indie rock", "dream pop", "chamber pop", "shoegaze",
    "synthpop", "new wave", "post-punk", "punk", "grunge", "hip hop", "trap", "r&b",
    "soul", "funk", "disco", "jazz", "blues", "lo-fi", "ambient", "house", "techno",
    "edm", "dance pop", "electropop", "folk", "singer-songwriter", "country", "americana",
    "metal", "classical", "afrobeats", "k-pop", "reggae", "latin pop", "bossa nova",
    "gospel", "hyperpop",
    # thin/unrecognized examples worth keeping here so the report shows they get dropped:
    "bedroom pop", "reggaeton", "slowcore", "sad indie",
]


def _get_token(client: httpx.Client, client_id: str, client_secret: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = client.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _total_for(client: httpx.Client, genre: str, token: str) -> int:
    resp = client.get(
        SEARCH_URL,
        params={"q": f'genre:"{genre}"', "type": "track", "limit": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return (resp.json().get("tracks") or {}).get("total", 0)


def main() -> None:
    # Credentials live in the MCP server's .env (this script sits at <repo>/scripts/).
    load_dotenv(Path(__file__).resolve().parent.parent / "mcp_server" / ".env")
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET (checked mcp_server/.env).")

    with httpx.Client(timeout=15.0) as client:
        token = _get_token(client, client_id, client_secret)
        kept: list[str] = []
        for genre in CANDIDATES:
            total = _total_for(client, genre, token)
            verdict = "keep" if total >= MIN_TOTAL else "drop"
            print(f"{genre:<20} total={total:<5} {verdict}")
            if total >= MIN_TOTAL:
                kept.append(genre)

    print(f"\n# {len(kept)}/{len(CANDIDATES)} genres passed (MIN_TOTAL={MIN_TOTAL})")
    print("VETTED_GENRES = [")
    for genre in kept:
        print(f'    "{genre}",')
    print("]")


if __name__ == "__main__":
    main()
