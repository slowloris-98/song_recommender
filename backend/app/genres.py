"""Vetted Spotify genre vocabulary for the recommendation agent.

Spotify no longer exposes genres on artist objects, and the `available-genre-seeds`
endpoint is gone (404), so there is no runtime way to discover which genre tags are valid.
The `genre:"..."` SEARCH filter still works, but only for tags Spotify recognizes — plausible
guesses like "slowcore" or "sad indie" return zero results.

So instead of letting the agent invent tags, we hand it this pre-validated palette: every
entry below was confirmed to return a healthy number of tracks via `genre:"<g>"` search.
Rebuild/refresh this list with `scripts/validate_genres.py`.
"""

VETTED_GENRES = [
    "pop",
    "rock",
    "indie pop",
    "indie rock",
    "dream pop",
    "chamber pop",
    "shoegaze",
    "synthpop",
    "new wave",
    "post-punk",
    "punk",
    "grunge",
    "hip hop",
    "trap",
    "r&b",
    "soul",
    "funk",
    "disco",
    "jazz",
    "blues",
    "lo-fi",
    "ambient",
    "house",
    "techno",
    "edm",
    "dance pop",
    "electropop",
    "folk",
    "singer-songwriter",
    "country",
    "americana",
    "metal",
    "classical",
    "afrobeats",
    "k-pop",
    "reggae",
    "latin pop",
    "bossa nova",
    "gospel",
    "hyperpop",
]
