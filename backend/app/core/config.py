"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the CYBERGUARD backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Async SQLAlchemy connection (Phase A domain layer). Defaults to the
    # local Supabase Postgres instance; the supabase-py client above remains
    # the transport for Auth, Storage, and Realtime.
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:54322/postgres"

    # Phase C-1 background workers: Redis-backed Arq queue for heavy analysis
    # (deepfake media, bulk log ingestion). When Redis is unreachable or
    # BACKGROUND_WORKERS_ENABLED is false, callers fall back to synchronous
    # processing on the request thread.
    REDIS_URL: str = "redis://localhost:6379"
    BACKGROUND_WORKERS_ENABLED: bool = True

    # Phase D-1: per-user (or per-IP) request budget, in requests per minute.
    RATE_LIMIT_RPM: int = 300

    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Explanation provider chain (strict order): Groq (15 s) -> OpenRouter
    # (20 s) -> rule-based template. Timeouts bound how long each provider may
    # take before the gateway falls through to the next one.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_TIMEOUT_SECONDS: float = 15

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "liquid/lfm-2.5-2.6b:free"
    OPENROUTER_TIMEOUT_SECONDS: float = 20

    ML_ENABLED: bool = True
    ML_MODELS_DIR: str = "ml/models"

    APP_TITLE: str = "CYBERGUARD API"
    APP_VERSION: str = "0.1.0"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS variable into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Lowercase accessor aliases used by the LLM provider clients.
    @property
    def groq_api_key(self) -> str:
        return self.GROQ_API_KEY

    @property
    def groq_model(self) -> str:
        return self.GROQ_MODEL

    @property
    def openrouter_timeout_seconds(self) -> float:
        return self.OPENROUTER_TIMEOUT_SECONDS

    @property
    def groq_timeout_seconds(self) -> float:
        return self.GROQ_TIMEOUT_SECONDS


@lru_cache
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()
