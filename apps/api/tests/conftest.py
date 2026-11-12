from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import redis.asyncio as aioredis
from mock_llm.main import create_app as create_mock
from semanticcache_api.main import create_app
from semanticcache_api.settings import ApiSettings, build_redis
from semanticcache_api.testing import ROOT_KEY, Stack
from semanticcache_api.upstream import UpstreamClient

REDIS_URL = os.environ.get("SC_TEST_REDIS_URL", "redis://localhost:6391/15")


@pytest.fixture
async def redis_client() -> AsyncIterator[aioredis.Redis]:
    client = aioredis.Redis.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.ping()
    except Exception:  # pragma: no cover
        await client.aclose()
        pytest.skip(f"Redis not reachable at {REDIS_URL}")
    yield client
    await client.aclose()


@pytest.fixture
async def stack(redis_client: aioredis.Redis) -> AsyncIterator[Stack]:
    prefix = f"scapi{uuid.uuid4().hex[:8]}"
    settings = ApiSettings(
        redis_url=REDIS_URL, prefix=prefix, embedding_dim=256, api_key_pepper="test-pepper-123",
        bootstrap_api_key=ROOT_KEY, cors_origins=["http://localhost:3100"], export_bucket="test-bucket",
    )  # fmt: skip
    mock_app = create_mock(latency_ms=0)
    mock_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://mock")
    upstream = UpstreamClient("http://mock/v1", client=mock_client)
    app = create_app(settings, redis=redis_client, upstream=upstream)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers={"X-API-Key": ROOT_KEY}
        ) as api:
            yield Stack(api, mock_client, app)
    keys = [k async for k in redis_client.scan_iter(match=f"{prefix}:*", count=500)]
    if keys:
        await redis_client.delete(*keys)
    await mock_client.aclose()


@pytest.fixture
async def retrying_stack(redis_client: aioredis.Redis) -> AsyncIterator[Stack]:
    """Like ``stack`` but the app owns a production-configured Redis client (retries, health checks)."""
    prefix = f"scrt{uuid.uuid4().hex[:8]}"
    settings = ApiSettings(
        redis_url=REDIS_URL,
        prefix=prefix,
        embedding_dim=256,
        api_key_pepper="test-pepper-123",
        bootstrap_api_key=ROOT_KEY,
    )
    mock_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_mock(latency_ms=0)), base_url="http://mock"
    )
    app = create_app(
        settings, redis=build_redis(REDIS_URL), upstream=UpstreamClient("http://mock/v1", client=mock_client)
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"X-API-Key": ROOT_KEY}
        ) as api:
            yield Stack(api, mock_client, app)
        await app.state.redis.aclose()
    keys = [k async for k in redis_client.scan_iter(match=f"{prefix}:*", count=500)]
    if keys:
        await redis_client.delete(*keys)
    await mock_client.aclose()
