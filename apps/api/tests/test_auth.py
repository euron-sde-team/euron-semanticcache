from __future__ import annotations

import httpx
import pytest
from semanticcache_api.testing import ROOT_KEY, Stack

pytestmark = pytest.mark.integration


async def test_requires_a_key(stack: Stack) -> None:
    r = await stack.api.get("/v1/namespaces", headers={"X-API-Key": ""})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert (
        await stack.api.get("/v1/namespaces", headers={"X-API-Key": "sc_nope0000_wrong"})
    ).status_code == 401
    assert (
        await stack.api.post("/v1/chat/completions", json={}, headers={"X-API-Key": ""})
    ).status_code == 401


async def test_bearer_token_works_like_the_openai_sdk_sends_it(stack: Stack) -> None:
    r = await stack.api.get(
        "/v1/namespaces", headers={"X-API-Key": "", "Authorization": f"Bearer {ROOT_KEY}"}
    )
    assert r.status_code == 200


async def test_scopes_are_enforced(stack: Stack) -> None:
    key = (await stack.api.post("/v1/api-keys", json={"name": "app", "scopes": ["proxy:use"]})).json()["key"]
    h = {"X-API-Key": key}
    assert (
        await stack.api.post(
            "/v1/chat/completions",
            headers=h,
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        )
    ).status_code == 200
    for method, path in [
        ("GET", "/v1/cache/entries"),
        ("GET", "/v1/namespaces"),
        ("GET", "/v1/stats/overview"),
        ("GET", "/v1/api-keys"),
    ]:
        r = await stack.api.request(method, path, headers=h)
        assert r.status_code == 403, path
        assert "missing scope" in r.json()["error"]["message"]
    assert (await stack.api.put("/v1/namespaces/x", json={}, headers=h)).status_code == 403


async def test_key_lifecycle_and_no_escalation(stack: Stack) -> None:
    admin = (
        await stack.api.post("/v1/api-keys", json={"name": "admin", "scopes": ["keys:admin", "stats:read"]})
    ).json()
    assert admin["key"].startswith("sc_")
    h = {"X-API-Key": admin["key"]}
    assert (
        await stack.api.post("/v1/api-keys", json={"name": "x", "scopes": ["proxy:use"]}, headers=h)
    ).status_code == 403
    assert (
        await stack.api.post("/v1/api-keys", json={"name": "x", "scopes": ["*"]}, headers=h)
    ).status_code == 403
    assert (await stack.api.post("/v1/api-keys", json={"name": "x", "scopes": ["bogus"]})).status_code == 422

    listed = (await stack.api.get("/v1/api-keys")).json()
    assert {k["name"] for k in listed} >= {"bootstrap", "admin"} and all("key" not in k for k in listed)
    assert (await stack.api.delete(f"/v1/api-keys/{admin['prefix']}")).status_code == 200
    assert (await stack.api.get("/v1/stats/overview", headers=h)).status_code == 401
    assert (await stack.api.delete("/v1/api-keys/root0001")).status_code == 409
    assert (await stack.api.delete("/v1/api-keys/ghost000")).status_code == 404


# ── namespace-bound keys are the tenant boundary ─────────────────────────────────────────────────────────────
async def bound(stack: Stack, ns: str, scopes: list[str] | None = None) -> dict[str, str]:
    r = await stack.api.post(
        "/v1/api-keys",
        json={
            "name": f"tenant-{ns}",
            "scopes": scopes or ["proxy:use", "cache:read", "cache:write", "stats:read"],
            "namespace": ns,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["namespace"] == ns
    return {"X-API-Key": r.json()["key"]}


async def test_a_bound_key_is_confined_to_its_namespace(stack: Stack) -> None:
    a, b = await bound(stack, "tenant-a"), await bound(stack, "tenant-b")

    async def ask(h: dict[str, str], q: str, **x: str) -> httpx.Response:
        return await stack.api.post(
            "/v1/chat/completions",
            headers={**h, **x},
            json={"model": "m", "messages": [{"role": "user", "content": q}]},
        )

    first = await ask(a, "Where is my order tenant secret?")
    assert first.headers["x-semanticcache"] == "MISS"
    assert (await ask(a, "Where is my order tenant secret?")).headers["x-semanticcache"] == "HIT"
    # tenant B asking the identical question must NOT be served tenant A's answer
    assert (await ask(b, "Where is my order tenant secret?")).headers["x-semanticcache"] == "MISS"
    assert (await ask(b, "where is my order, tenant secret")).headers[
        "x-semanticcache"
    ] == "HIT"  # B's own entry
    # explicitly asking for the other tenant's namespace is refused, in every endpoint
    assert (await ask(a, "x", **{"X-SC-Namespace": "tenant-b"})).status_code == 403
    assert (
        await stack.api.get("/v1/cache/entries", params={"namespace": "tenant-b"}, headers=a)
    ).status_code == 403
    assert (
        await stack.api.delete("/v1/cache/entries", params={"namespace": "tenant-b"}, headers=a)
    ).status_code == 403
    ids_a = {e["id"] for e in (await stack.api.get("/v1/cache/entries", headers=a)).json()["items"]}
    ids_b = {e["id"] for e in (await stack.api.get("/v1/cache/entries", headers=b)).json()["items"]}
    assert ids_a and ids_b and not ids_a & ids_b
    assert (await stack.api.get(f"/v1/cache/entries/{next(iter(ids_b))}", headers=a)).status_code == 404


async def test_a_bound_key_sees_only_its_own_stats_and_cannot_manage_namespaces(stack: Stack) -> None:
    a = await bound(stack, "tenant-a")
    await bound(stack, "tenant-b")
    await stack.api.post(
        "/v1/chat/completions",
        headers={**a},
        json={"model": "m", "messages": [{"role": "user", "content": "q"}]},
    )
    await stack.api.post(
        "/v1/chat/completions",
        headers={"X-SC-Namespace": "tenant-b"},
        json={"model": "m", "messages": [{"role": "user", "content": "q"}]},
    )
    assert [n["name"] for n in (await stack.api.get("/v1/namespaces", headers=a)).json()] == ["tenant-a"]
    assert [
        n["name"] for n in (await stack.api.get("/v1/stats/overview", headers=a)).json()["namespaces"]
    ] == ["tenant-a"]
    assert {n["name"] for n in (await stack.api.get("/v1/namespaces")).json()} == {"tenant-a", "tenant-b"}
    scoped = await bound(stack, "tenant-a", ["namespaces:write", "keys:admin"])
    assert (await stack.api.put("/v1/namespaces/tenant-a", json={}, headers=scoped)).status_code == 403
    assert (await stack.api.delete("/v1/namespaces/tenant-a", headers=scoped)).status_code == 403


async def test_a_bound_key_cannot_mint_an_unbound_key(stack: Stack) -> None:
    h = await bound(stack, "tenant-a", ["keys:admin", "proxy:use"])
    assert (
        await stack.api.post("/v1/api-keys", json={"name": "x", "scopes": ["proxy:use"]}, headers=h)
    ).status_code == 403
    assert (
        await stack.api.post(
            "/v1/api-keys", json={"name": "x", "scopes": ["proxy:use"], "namespace": "tenant-b"}, headers=h
        )
    ).status_code == 403
    ok = await stack.api.post(
        "/v1/api-keys", json={"name": "x", "scopes": ["proxy:use"], "namespace": "tenant-a"}, headers=h
    )
    assert ok.status_code == 201


async def test_invalid_namespace_names_are_rejected(stack: Stack) -> None:
    assert (
        await stack.api.post("/v1/api-keys", json={"name": "x", "namespace": "bad name!"})
    ).status_code == 422
    r = await stack.ask("hi", headers={"X-SC-Namespace": "../etc"})
    assert r.status_code == 422
