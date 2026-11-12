from __future__ import annotations

import datetime as dt
import io
from typing import Any

import pytest
from semanticcache_api.testing import Stack

pytestmark = pytest.mark.integration
PW = "How do I reset my password?"
MSGS = [{"role": "user", "content": PW}]
RESPONSE = {
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "Warmed answer."}, "finish_reason": "stop"}
    ]
}


async def test_lookup_never_calls_the_provider_and_is_not_counted(stack: Stack) -> None:
    body = {"model": "gpt-4o-mini", "messages": MSGS}
    assert (await stack.api.post("/v1/cache/lookup", json=body)).json()["hit"] is False
    await stack.ask(PW)
    r = (await stack.api.post("/v1/cache/lookup", json=body)).json()
    assert r["hit"] and r["match"] == "exact" and r["entry"]["prompt"] == PW
    s = (await stack.api.get("/v1/stats/overview")).json()["totals"]
    assert s["requests"] == 1, "lookups through the cache API are free and uncounted"
    assert await stack.provider_calls() == 1


async def test_explain_shows_neighbours_and_verdicts(stack: Stack) -> None:
    await stack.ask(PW)
    await stack.ask("What is the capital of France?")
    other = {"role": "system", "content": "Other persona"}
    await stack.api.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [other, *MSGS]})
    r = (
        await stack.api.post(
            "/v1/cache/explain",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "how can I reset my password"}],
            },
        )
    ).json()
    assert r["threshold"] == 0.85 and r["guards"] is True
    best = r["neighbors"][0]
    assert best["would_hit"] and best["in_scope"] and best["similarity"] >= 0.85
    assert any(not n["in_scope"] and not n["would_hit"] for n in r["neighbors"])


async def test_warming_the_cache_then_hitting_it_through_the_proxy(stack: Stack) -> None:
    body = {
        "model": "gpt-4o-mini",
        "messages": MSGS,
        "response": RESPONSE,
        "tags": ["faq"],
        "ttl_seconds": 600,
        "latency_ms": 900,
    }
    r = await stack.api.post("/v1/cache/entries", json=body)
    assert r.status_code == 201 and r.json()["tags"] == ["faq"] and r.json()["usage"]["prompt_tokens"] > 0
    hit = await stack.ask(PW)
    assert (
        hit.headers["x-semanticcache"] == "HIT"
        and hit.json()["choices"][0]["message"]["content"] == "Warmed answer."
    )
    assert await stack.provider_calls() == 0


async def test_browse_search_get_delete_flush(stack: Stack) -> None:
    for q in ("alpha question one", "beta question two", "alpha question three"):
        await stack.ask(q)
    page = (await stack.api.get("/v1/cache/entries")).json()
    assert page["total"] == 3 and len(page["items"]) == 3
    assert {
        e["prompt"] for e in (await stack.api.get("/v1/cache/entries", params={"q": "ALPHA"})).json()["items"]
    } == {"alpha question one", "alpha question three"}
    assert (
        len((await stack.api.get("/v1/cache/entries", params={"limit": 2, "offset": 2})).json()["items"]) == 1
    )
    eid = page["items"][0]["id"]
    assert (await stack.api.get(f"/v1/cache/entries/{eid}")).json()["id"] == eid
    assert (await stack.api.delete(f"/v1/cache/entries/{eid}")).json() == {"deleted": 1}
    assert (await stack.api.delete(f"/v1/cache/entries/{eid}")).status_code == 404
    assert (await stack.api.get(f"/v1/cache/entries/{eid}")).status_code == 404
    assert (await stack.api.delete("/v1/cache/entries")).json() == {"deleted": 2}
    assert (await stack.api.get("/v1/cache/entries")).json()["total"] == 0


async def test_hit_counts_show_up_on_entries(stack: Stack) -> None:
    await stack.ask(PW)
    for _ in range(3):
        await stack.ask(PW)
    e = (await stack.api.get("/v1/cache/entries")).json()["items"][0]
    assert e["hits"] == 3 and e["last_hit_at"]


# ── S3 export / import with a fake S3 ────────────────────────────────────────────────────────────────────────
class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_: Any) -> None:
        assert Bucket == "test-bucket"
        self.objects[Key] = Body

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objects[Key])}

    def list_objects_v2(self, Bucket: str, Prefix: str) -> dict[str, Any]:
        now = dt.datetime.now(dt.UTC)
        return {
            "Contents": [
                {"Key": k, "Size": len(v), "LastModified": now}
                for k, v in self.objects.items()
                if k.startswith(Prefix)
            ]
        }


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    fake = FakeS3()
    monkeypatch.setattr("semanticcache_api.routers.cache.aws_client", lambda *_: fake)
    return fake


async def test_export_then_import_into_another_namespace(stack: Stack, s3: FakeS3) -> None:
    await stack.ask(PW, headers={"X-SC-Namespace": "src"})
    await stack.ask("What is the capital of France?", headers={"X-SC-Namespace": "src"})
    ex = (await stack.api.post("/v1/cache/export", json={"namespace": "src"})).json()
    assert ex["entries"] == 2 and ex["key"].startswith("exports/src/") and ex["key"] in s3.objects
    assert b"lease" not in s3.objects[ex["key"]] and b'"vec"' not in s3.objects[ex["key"]], (
        "vectors are not exported"
    )
    assert (await stack.api.get("/v1/cache/exports", params={"namespace": "src"})).json()[0]["key"] == ex[
        "key"
    ]

    imp = (await stack.api.post("/v1/cache/import", json={"key": ex["key"], "namespace": "dst"})).json()
    assert imp == {"imported": 2, "skipped_expired": 0, "namespace": "dst"}
    before = await stack.provider_calls()
    assert (await stack.ask(PW, headers={"X-SC-Namespace": "dst"})).headers["x-semanticcache"] == "HIT"
    assert (await stack.ask("how can I reset my password", headers={"X-SC-Namespace": "dst"})).headers[
        "x-semanticcache-type"
    ] == "semantic"
    assert await stack.provider_calls() == before


async def test_import_rejects_bad_keys_missing_objects_and_corrupt_lines(stack: Stack, s3: FakeS3) -> None:
    for key in ("not-an-export", "exports/../secrets/x.jsonl", "other/ns/file.jsonl"):
        assert (await stack.api.post("/v1/cache/import", json={"key": key})).status_code == 422, key
    assert (
        await stack.api.post("/v1/cache/import", json={"key": "exports/ns/missing.jsonl"})
    ).status_code == 404
    s3.objects["exports/ns/bad.jsonl"] = b'{"not": "an entry"}\n'
    assert (await stack.api.post("/v1/cache/import", json={"key": "exports/ns/bad.jsonl"})).status_code == 422


async def test_export_requires_a_configured_bucket(stack: Stack) -> None:
    stack.app.state.settings = stack.app.state.settings.model_copy(update={"export_bucket": None})
    assert (await stack.api.post("/v1/cache/export", json={})).status_code == 501


async def test_a_bound_key_can_only_import_its_own_exports(stack: Stack, s3: FakeS3) -> None:
    key = (
        await stack.api.post(
            "/v1/api-keys", json={"name": "a", "scopes": ["cache:write"], "namespace": "tenant-a"}
        )
    ).json()["key"]
    s3.objects["exports/tenant-b/x.jsonl"] = b""
    r = await stack.api.post(
        "/v1/cache/import", json={"key": "exports/tenant-b/x.jsonl"}, headers={"X-API-Key": key}
    )
    assert r.status_code == 403


async def test_cache_endpoints_accept_the_namespace_as_a_header_like_the_proxy(stack: Stack) -> None:
    """Regression: only ?namespace= was honoured, so X-SC-Namespace on /v1/cache/* silently hit 'default'."""
    h = {"X-SC-Namespace": "via-header"}
    await stack.ask(PW, headers=h)
    assert (await stack.api.get("/v1/cache/entries", headers=h)).json()["total"] == 1
    assert (await stack.api.get("/v1/cache/entries")).json()["total"] == 0, (
        "the default namespace must stay empty"
    )
    assert (await stack.api.get("/v1/cache/entries", params={"namespace": "via-query"})).json()["total"] == 0
    both = await stack.api.get("/v1/cache/entries", headers=h, params={"namespace": "via-header"})
    assert both.json()["total"] == 1
    warm = {"model": "gpt-4o-mini", "messages": MSGS, "response": RESPONSE}
    assert (await stack.api.post("/v1/cache/entries", json=warm, headers=h)).status_code == 201
    assert (await stack.api.post("/v1/cache/invalidate", json={"tag": "none"}, headers=h)).json() == {
        "deleted": 0
    }
    assert (await stack.api.delete("/v1/cache/entries", headers=h)).json()["deleted"] == 1
