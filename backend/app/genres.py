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

# Mood/vibe keyword -> vetted genres, used by the `mood_to_genres` tool.
#
# Keys are matched as substrings against the user's phrasing, so several entries can fire for
# "happy and energetic". Every value MUST appear in VETTED_GENRES — `mood_to_genres` filters
# against it, so a typo silently drops a genre rather than reaching Spotify as a bad tag.
MOOD_GENRES: dict[str, list[str]] = {
    "happy": ["pop", "dance pop", "funk", "soul"],
    "upbeat": ["dance pop", "funk", "disco", "pop"],
    "cheerful": ["pop", "funk", "soul", "afrobeats"],
    "sad": ["folk", "singer-songwriter", "blues", "ambient"],
    "melancholy": ["folk", "dream pop", "ambient", "singer-songwriter"],
    "heartbreak": ["r&b", "singer-songwriter", "soul", "folk"],
    "chill": ["lo-fi", "ambient", "bossa nova", "dream pop"],
    "relax": ["ambient", "lo-fi", "bossa nova", "classical"],
    "calm": ["ambient", "classical", "lo-fi", "folk"],
    "mellow": ["lo-fi", "bossa nova", "soul", "dream pop"],
    "energetic": ["edm", "house", "dance pop", "hyperpop"],
    "hype": ["trap", "hip hop", "edm", "hyperpop"],
    "workout": ["edm", "trap", "house", "metal"],
    "party": ["dance pop", "house", "afrobeats", "hip hop"],
    "angry": ["metal", "punk", "grunge", "trap"],
    "aggressive": ["metal", "punk", "trap", "grunge"],
    "romantic": ["r&b", "soul", "jazz", "bossa nova"],
    "love": ["r&b", "soul", "pop", "jazz"],
    "dreamy": ["dream pop", "shoegaze", "ambient", "chamber pop"],
    "ethereal": ["ambient", "dream pop", "shoegaze", "classical"],
    "moody": ["post-punk", "shoegaze", "trap", "ambient"],
    "dark": ["post-punk", "metal", "trap", "ambient"],
    "nostalgic": ["new wave", "synthpop", "disco", "soul"],
    "retro": ["disco", "new wave", "funk", "synthpop"],
    "focus": ["lo-fi", "ambient", "classical", "jazz"],
    "study": ["lo-fi", "ambient", "classical", "bossa nova"],
    "uplifting": ["gospel", "soul", "pop", "americana"],
    "hopeful": ["americana", "folk", "gospel", "pop"],
    "rainy": ["lo-fi", "ambient", "folk", "dream pop"],
    "summer": ["reggae", "afrobeats", "dance pop", "latin pop"],
}

# Used when nothing in MOOD_GENRES matches — a deliberately broad spread rather than nothing,
# so an unrecognised mood still yields a usable (if generic) starting point.
FALLBACK_GENRES: list[str] = ["pop", "indie pop", "rock", "folk"]
