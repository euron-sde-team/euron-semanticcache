"""Settings shared by the API, read from ``SC_*`` environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SC_", env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    prefix: str = "sc"
    embedder: str = Field(default="hashing", description="hashing | openai")
    embedding_dim: int = 512
    embedding_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str | None = None
    pricing_file: str | None = None
    log_level: str = "INFO"
