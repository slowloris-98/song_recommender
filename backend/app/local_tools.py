"""Agent tools that run in the backend rather than on the MCP server.

`mood_to_genres` touches no Spotify API — it is a pure mapping onto VETTED_GENRES. Keeping it
here rather than in the MCP server avoids shipping a second copy of the genre list into a
separately-deployed service, where the two would drift apart.

LangGraph accepts local and MCP tools in one list, so the agent cannot tell the difference.
"""

import logging

from langchain_core.tools import tool

from .genres import FALLBACK_GENRES, MOOD_GENRES, VETTED_GENRES

logger = logging.getLogger(__name__)

_VETTED = set(VETTED_GENRES)


@tool
def mood_to_genres(mood: str, count: int = 4) -> list[str]:
    """Map a mood, vibe, or feeling to Spotify genres that are known to work.

    Pass the user's own words ("happy", "sad and rainy", "something for studying"). Returns up
    to `count` genre names, ready to hand to `genres_to_artists`.

    Only use this for moods/vibes. If the user names a GENRE outright, pass it to
    `genres_to_artists` directly. If they name an artist, album, or track, this tool cannot
    help — Spotify does not expose genres for those, so choose genres yourself.
    """
    text = mood.lower()
    picked: list[str] = []
    for keyword, genres in MOOD_GENRES.items():
        if keyword in text:
            for g in genres:
                # Guard against a typo in MOOD_GENRES reaching Spotify as an invalid tag.
                if g in _VETTED and g not in picked:
                    picked.append(g)

    if not picked:
        logger.info("mood_to_genres: no keyword matched %r, using fallback", mood)
        picked = list(FALLBACK_GENRES)

    result = picked[:count]
    logger.info("mood_to_genres(%r) -> %s", mood, result)
    return result
