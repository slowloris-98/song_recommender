"""Vetted Spotify search vocabulary for the recommendation agent.

Spotify no longer exposes genres on artist objects, and the `available-genre-seeds`
endpoint is gone (404), so there is no runtime way to discover which tags are valid.
The `genre:"..."` SEARCH filter still works, but only for terms Spotify recognizes.

VETTED_VOCAB below is a hand-curated palette grouped by the axis each term serves. Every
entry was probed with `genre:"<term>"&type=artist,track` (the runtime query shape) AND its
sample results eyeballed for relevance — a raw hit count is not enough, since a free-text
term like "rock" clears the threshold while returning name-substring junk. Rebuild/refresh
with `scripts/validate_genres.py`, which prints those samples for curation.

Empirical finding baked into the split below (measured 2026-07-21):
  * genre, region/language, and CONTEXT moods (workout, sleep, chill...) work as `genre:`
    filters and are safe to pass straight through.
  * EMOTION and WEATHER words do NOT — `genre:"love"` returns doom metal, `genre:"rainy"`
    returns nothing, because Spotify name-matches them. Those must be translated to real
    genres instead, which is what MOOD_GENRES / the `mood_to_genres` tool exist to do.
"""

# Curated search terms, grouped by the axis each serves. The agent picks from these directly
# for genre/region/context requests; see backend/app/prompts.py.
VETTED_VOCAB: dict[str, list[str]] = {
    # Musical style — the backbone.
    "genre": [
        "pop", "rock", "indie pop", "indie rock", "dream pop", "chamber pop", "shoegaze",
        "synthpop", "new wave", "post-punk", "punk", "grunge", "hip hop", "trap", "r&b",
        "soul", "funk", "disco", "jazz", "blues", "lo-fi", "ambient", "house", "techno",
        "edm", "dance pop", "electropop", "folk", "singer-songwriter", "country", "americana",
        "metal", "classical", "gospel", "hyperpop", "reggae", "bossa nova", "hard rock",
        "soft rock", "alt rock", "classic rock", "psychedelic rock", "post-rock", "emo",
        "math rock", "garage rock", "phonk", "boom bap", "neo soul", "bluegrass", "ska",
        "progressive rock", "death metal", "indie folk", "alternative", "electronic",
        "acoustic",
    ],
    # CONTEXT/activity moods only — these survive as `genre:` filters. Emotion words
    # (happy, sad, love...) do NOT; route those through MOOD_GENRES instead.
    "mood": [
        "chill", "uplifting", "party", "workout", "focus", "sleep",
    ],
    # Language / region / country. The lever for requests like "hindi songs".
    "region": [
        "bollywood", "hindi", "filmi", "punjabi", "bhangra", "tamil", "telugu", "indian",
        "arabic", "turkish", "french", "spanish", "italian", "german", "japanese", "j-pop",
        "j-rock", "mandopop", "cantopop", "k-pop", "korean", "brazilian", "afrobeats",
        "latin", "latin pop", "nigerian", "mexican", "french pop", "russian", "greek",
        "portuguese",
    ],
    # Occasion. Only the terms that actually resolve as filters survived curation.
    "scene": [
        "beach", "christmas",
    ],
}

# Flat union of every vetted term. Kept for importers that just need the membership set:
# local_tools.py's `mood_to_genres` guard, scripts/compare_genre_search.py.
VETTED_GENRES: list[str] = [term for terms in VETTED_VOCAB.values() for term in terms]

# Region/language term -> ISO 3166-1 alpha-2 market. The agent sets `market` on the tools for
# regional requests so Spotify biases results to that catalogue (see prompts.py). Terms not
# listed here need no market (they are style tags, not places).
REGION_MARKETS: dict[str, str] = {
    "bollywood": "IN", "hindi": "IN", "filmi": "IN", "punjabi": "IN", "bhangra": "IN",
    "tamil": "IN", "telugu": "IN", "indian": "IN", "desi": "IN",
    "japanese": "JP", "j-pop": "JP", "j-rock": "JP",
    "mandopop": "TW", "cantopop": "HK",
    "k-pop": "KR", "korean": "KR",
    "brazilian": "BR", "portuguese": "PT",
    "french": "FR", "french pop": "FR", "spanish": "ES", "italian": "IT", "german": "DE",
    "russian": "RU", "greek": "GR", "turkish": "TR", "arabic": "AE",
    "nigerian": "NG", "afrobeats": "NG", "mexican": "MX", "latin": "MX", "latin pop": "MX",
}

# Emotion/weather/vibe keyword -> vetted GENRES, used by the `mood_to_genres` tool.
#
# This is the translation layer for words that do NOT work as `genre:` filters. Keys are
# matched as substrings against the user's phrasing, so several entries can fire for
# "happy and energetic". Every value MUST appear in VETTED_GENRES — `mood_to_genres` filters
# against it, so a typo silently drops a genre rather than reaching Spotify as a bad tag.
MOOD_GENRES: dict[str, list[str]] = {
    "happy": ["pop", "dance pop", "funk", "soul"],
    "feel good": ["pop", "funk", "soul", "disco"],
    "feel-good": ["pop", "funk", "soul", "disco"],
    "good vibe": ["pop", "funk", "soul", "afrobeats"],
    "upbeat": ["dance pop", "funk", "disco", "pop"],
    "cheerful": ["pop", "funk", "soul", "afrobeats"],
    "joy": ["pop", "funk", "gospel", "soul"],
    "sad": ["folk", "singer-songwriter", "blues", "ambient"],
    "melancholy": ["folk", "dream pop", "ambient", "singer-songwriter"],
    "heartbreak": ["r&b", "singer-songwriter", "soul", "folk"],
    "lonely": ["folk", "singer-songwriter", "ambient", "dream pop"],
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
    "winter": ["ambient", "classical", "folk", "dream pop"],
}

# Used when nothing in MOOD_GENRES matches — a deliberately broad spread rather than nothing,
# so an unrecognised mood still yields a usable (if generic) starting point.
FALLBACK_GENRES: list[str] = ["pop", "indie pop", "rock", "folk"]
