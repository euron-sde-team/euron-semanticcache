from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as aioredis
from semanticcache_api.settings import build_redis
from semanticcache_api.testing import Stack

pytestmark = pytest.mark.integration
PW = "How do I reset my password?"


async def kill_all_other_connections(admin: aioredis.Redis) -> None:
    """What a Redis restart or failover does to a client's connection pool."""
    await admin.execute_command("CLIENT", "KILL", "TYPE", "normal", "SKIPME", "yes")  # type: ignore[no-untyped-call]


async def test_requests_survive_stale_pooled_connections(
    retrying_stack: Stack, redis_client: aioredis.Redis
) -> None:
    """Regression: after a Redis restart every pooled connection was dead and each surfaced as a 500."""
    stack = retrying_stack
    # open many pooled connections, so that several are stale at once
    await asyncio.gather(*(stack.ask(f"warm the pool with question {i}") for i in range(20)))
    for _ in range(3):
        await kill_all_other_connections(redis_client)
        results = await asyncio.gather(*(stack.ask(f"after the kill {i}") for i in range(15)), stack.ask(PW))
        assert [r.status_code for r in results] == [200] * 16, {r.status_code for r in results}
        assert (await stack.api.get("/readyz", headers={"X-API-Key": ""})).status_code == 200
        assert (await stack.api.get("/v1/stats/overview")).status_code == 200


async def test_the_production_client_is_configured_for_recovery() -> None:
    client = build_redis("redis://localhost:6391/15")
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["decode_responses"] is False, "embeddings are raw bytes"
    assert kwargs["health_check_interval"] > 0 and kwargs["socket_keepalive"] is True
    assert kwargs["retry"] is not None
    await client.aclose()
