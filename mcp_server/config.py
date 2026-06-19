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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
