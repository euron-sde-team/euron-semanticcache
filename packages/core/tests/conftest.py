from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as aioredis
from semanticcache_core import HashingEmbedder, SemanticCache

REDIS_URL = os.environ.get("SC_TEST_REDIS_URL", "redis://localhost:6391/15")


@pytest.fixture
async def redis_client() -> AsyncIterator[aioredis.Redis]:
    client = aioredis.Redis.from_url(REDIS_URL, decode_responses=False)
    try:
        await client.ping()
    except Exception:  # pragma: no cover
        await client.aclose()
        pytest.skip(f"Redis not reachable at {REDIS_URL} (set SC_TEST_REDIS_URL)")
    yield client
    await client.aclose()


@pytest.fixture
async def cache(redis_client: aioredis.Redis) -> AsyncIterator[SemanticCache]:
    """A SemanticCache on an isolated key prefix, cleaned up afterwards."""
    prefix = f"sct{uuid.uuid4().hex[:8]}"
    yield SemanticCache(redis_client, HashingEmbedder(256), prefix=prefix)
    keys = [k async for k in redis_client.scan_iter(match=f"{prefix}:*", count=500)]
    if keys:
        await redis_client.delete(*keys)
