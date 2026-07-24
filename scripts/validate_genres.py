"""Dev-time builder/refresher for backend/app/genres.py's VETTED_VOCAB.

NOT part of the server runtime. Spotify gives us no way to enumerate valid genre tags
(the `available-genre-seeds` endpoint is 404 and artist objects no longer carry `genres`),
so we validate a candidate list empirically: probe each tag with a `genre:"<g>"` search and
keep the ones that return enough results.

Two things this probe does that matter:

  * It searches with the RUNTIME query shape — `type=artist,track` — because that is what
    `genres_to_artists` actually issues. A tag that is healthy for track search can be empty
    for artist search (and vice versa).
  * It prints the TOP sample tracks for each surviving tag. A raw count is not enough: a
    free-text term like "rock" clears MIN_TOTAL while returning name-substring junk (Gene
    Rockwell, Genki Rockets), so the count is a filter and the samples are the acceptance
    gate. Read the samples and hand-curate the survivors into VETTED_VOCAB — do not paste the
    block blindly.

Usage (from the repo root):
    python scripts/validate_genres.py

Reads SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET from mcp_server/.env (same credentials the
MCP server uses). Prints a per-tag report grouped by category and a ready-to-curate block.
"""

import base64
import os
import sys
from pathlib import Path

# Track/artist names carry non-Latin characters; the Windows console defaults to cp1252 and
# would crash on them. Force UTF-8 so the samples print regardless of the host codepage.
sys.stdout.reconfigure(encoding="utf-8")

import httpx
from dotenv import load_dotenv

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"

# Keep a tag only if `genre:"<g>"` returns at least this many tracks. Common tags return
# ~100 (Spotify's search cap); thin/misspelled tags return 0-4. This is a coarse filter —
# read the printed samples before trusting a survivor.
MIN_TOTAL = 20

# How many sample tracks to print per surviving tag, for eyeball relevance-checking.
SAMPLE_N = 5

# Candidate tags grouped by the axis they serve. Survivors become VETTED_VOCAB. Add guesses
# freely — the probe drops whatever Spotify doesn't recognize or returns too few results for.
# The grouping here is the grouping the runtime uses, so curate within each list.
CANDIDATES: dict[str, list[str]] = {
    # Musical style. The backbone — these are the classic taxonomy tags plus subgenres.
    "genre": [
        "pop", "rock", "indie pop", "indie rock", "dream pop", "chamber pop", "shoegaze",
        "synthpop", "new wave", "post-punk", "punk", "grunge", "hip hop", "trap", "r&b",
        "soul", "funk", "disco", "jazz", "blues", "lo-fi", "ambient", "house", "techno",
        "edm", "dance pop", "electropop", "folk", "singer-songwriter", "country", "americana",
        "metal", "classical", "gospel", "hyperpop", "reggae", "bossa nova",
        # subgenre guesses worth probing:
        "hard rock", "soft rock", "alt rock", "classic rock", "psychedelic rock", "post-rock",
        "emo", "math rock", "garage rock", "drum and bass", "dubstep", "phonk", "boom bap",
        "neo soul", "bluegrass", "ska", "progressive rock", "heavy metal", "death metal",
        "indie folk", "alternative", "electronic", "acoustic",
    ],
    # Mood / feeling. The user observed these return results as `genre:"<mood>"`.
    "mood": [
        "love", "sad", "happy", "chill", "feel good", "heartbreak", "dreamy", "angry",
        "energetic", "nostalgic", "romantic", "melancholy", "moody", "uplifting", "party",
        "relaxing", "sensual", "workout", "study", "focus", "sleep",
    ],
    # Language / region / country.
    "region": [
        "bollywood", "hindi", "filmi", "desi", "punjabi", "bhangra", "tamil", "telugu",
        "indian", "arabic", "turkish", "french", "spanish", "italian", "german", "japanese",
        "j-pop", "j-rock", "mandopop", "cantopop", "k-pop", "korean", "brazilian", "afrobeats",
        "latin", "latin pop", "reggaeton", "nigerian", "mexican", "french pop", "russian",
        "greek", "portuguese",
    ],
    # Weather / scene / occasion.
    "scene": [
        "rainy", "summer", "winter", "sunny", "night", "driving", "beach", "christmas",
        "morning", "coffee", "roadtrip", "sunset",
    ],
}


def _get_token(client: httpx.Client, client_id: str, client_secret: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = client.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _probe(client: httpx.Client, tag: str, token: str) -> tuple[int, int, list[str]]:
    """Probe one tag with the runtime query shape.

    Returns (track_total, artist_total, sample "track - artist" strings). Artist total is
    reported alongside because `genres_to_artists` harvests the artist block too, and a tag
    can be track-healthy but artist-empty.
    """
    resp = client.get(
        SEARCH_URL,
        params={"q": f'genre:"{tag}"', "type": "artist,track", "limit": SAMPLE_N},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    tracks = data.get("tracks") or {}
    artists = data.get("artists") or {}
    samples = []
    for t in (tracks.get("items") or [])[:SAMPLE_N]:
        if not t:
            continue
        names = ", ".join(a.get("name", "?") for a in (t.get("artists") or []))
        samples.append(f"{t.get('name', '?')} - {names}")
    return tracks.get("total", 0), artists.get("total", 0), samples


def main() -> None:
    # Credentials live in the MCP server's .env (this script sits at <repo>/scripts/).
    load_dotenv(Path(__file__).resolve().parent.parent / "mcp_server" / ".env")
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET (checked mcp_server/.env).")

    kept: dict[str, list[str]] = {cat: [] for cat in CANDIDATES}
    n_total = sum(len(v) for v in CANDIDATES.values())

    with httpx.Client(timeout=15.0) as client:
        token = _get_token(client, client_id, client_secret)
        for category, tags in CANDIDATES.items():
            print(f"\n{'=' * 70}\n{category.upper()}\n{'=' * 70}")
            for tag in tags:
                t_total, a_total, samples = _probe(client, tag, token)
                verdict = "keep" if t_total >= MIN_TOTAL else "DROP"
                print(f"\n{tag:<20} tracks={t_total:<5} artists={a_total:<5} {verdict}")
                for s in samples:
                    print(f"      - {s}")
                if t_total >= MIN_TOTAL:
                    kept[category].append(tag)

    n_kept = sum(len(v) for v in kept.values())
    print(f"\n\n# {n_kept}/{n_total} tags passed MIN_TOTAL={MIN_TOTAL}.")
    print("# REVIEW THE SAMPLES ABOVE before pasting — count alone lets name-matches through.\n")
    print("VETTED_VOCAB = {")
    for category, tags in kept.items():
        print(f'    "{category}": [')
        for tag in tags:
            print(f'        "{tag}",')
        print("    ],")
    print("}")


if __name__ == "__main__":
    main()
