"""Backend configuration.

`load_dotenv()` populates os.environ from .env so that whichever LLM provider you select
finds its own standard key variable (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...) without any
provider-specific code here. pydantic-settings then reads the app-level config.
"""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    # Provider abstraction: change these two to swap LLMs (config-only, no code change).
    # Examples: ("openai", "gpt-4o"), ("anthropic", "claude-opus-4-8"), ("ollama", "llama3.1")
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"

    # MCP (FastMCP streamable-http) endpoint.
    mcp_url: str = "http://localhost:8001/mcp"

    # Comma-separated allowed CORS origins for the React dev server.
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
