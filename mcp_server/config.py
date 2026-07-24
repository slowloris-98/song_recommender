from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP server configuration (loaded from environment / .env).

    SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET come from a Spotify app you create at
    https://developer.spotify.com/dashboard. Client Credentials flow only needs these
    two values (no user login) for the Phase-1 read-only tools.
    """

    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001

    # DEBUG adds a line per Spotify HTTP request (method, path, params, status, latency).
    log_level: str = "INFO"

    # Discovery fan-out. The batched tools issue many Spotify calls per invocation and run
    # them concurrently, so these bound both breadth and load. Tool arguments override them
    # per call; these are the defaults an operator can retune without a code change.
    #
    # Spotify caps `limit` at 10 per request, so anything above 10 is fetched by paging with
    # `offset` rather than sending a larger limit (which returns 400 Invalid limit).
    artists_per_genre: int = 10
    tracks_per_artist: int = 10
    # Measured safe: 26 concurrent calls completed in 1.6s with no 429s.
    discovery_concurrency: int = 8
    # Guard against unbounded fan-out if the agent passes a long genre list.
    max_genres_per_call: int = 4

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
