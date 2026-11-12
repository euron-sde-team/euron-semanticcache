from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import NoDecode
from semanticcache_core import CoreSettings


class ApiSettings(CoreSettings):
    host: str = "0.0.0.0"  # noqa: S104 - containers bind all interfaces
    port: int = 8180
    # Secret used to HMAC API keys at rest. Generate a long random value for any shared deployment.
    api_key_pepper: str = Field(default="dev-only-pepper-change-me", min_length=8)
    # Seeded as an all-scopes key on startup when set (handy for local demos and CI).
    bootstrap_api_key: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3100"])
    environment: str = "local"
    default_namespace: str = "default"

    # The real LLM provider (any OpenAI-compatible /chat/completions endpoint). Misses are forwarded here.
    upstream_base_url: str = "http://localhost:8190/v1"
    upstream_api_key: str | None = None
    upstream_timeout_s: float = 60.0

    # Optional AWS: Secrets Manager for deployment secrets, S3 for cache export and import.
    secrets_arn: str | None = None
    aws_region: str | None = None  # falls back to AWS_REGION / AWS_DEFAULT_REGION
    aws_endpoint_url: str | None = None
    export_bucket: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            text = v.strip()
            if text.startswith("["):
                return json.loads(text)
            return [o.strip() for o in text.split(",") if o.strip()]
        return v


def resolve_region(configured: str | None) -> str | None:
    """boto3 only reads AWS_DEFAULT_REGION; ECS and most tooling set AWS_REGION, so honour both."""
    return configured or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")


def aws_client(service: str, settings: ApiSettings) -> Any:
    import boto3  # type: ignore[import-untyped]

    return boto3.client(
        service, region_name=resolve_region(settings.aws_region), endpoint_url=settings.aws_endpoint_url
    )


def apply_aws_secrets(settings: ApiSettings, client: Any = None) -> ApiSettings:
    """Overlays pepper, bootstrap key and provider keys from Secrets Manager when `secrets_arn` is set."""
    if not settings.secrets_arn:
        return settings
    client = client or aws_client("secretsmanager", settings)
    data = json.loads(client.get_secret_value(SecretId=settings.secrets_arn)["SecretString"])
    update = {
        k: data[k]
        for k in ("api_key_pepper", "bootstrap_api_key", "upstream_api_key", "embedding_api_key")
        if data.get(k)
    }
    return settings.model_copy(update=update)


@lru_cache
def get_settings() -> ApiSettings:
    return ApiSettings()
