from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from semanticcache_api.testing import Stack
from semanticcache_api.upstream import UpstreamClient

pytestmark = pytest.mark.integration
PW = "How do I reset my password?"


def sse_events(text: str) -> list[Any]:
    out: list[Any] = []
    for block in text.split("\n\n"):
        if block.startswith("data: "):
            data = block[6:]
            out.append("[DONE]" if data == "[DONE]" else json.loads(data))
    return out


async def test_miss_then_hit_calls_the_provider_once(stack: Stack) -> None:
    first = await stack.ask(PW)
    assert first.status_code == 200 and first.headers["x-semanticcache"] == "MISS"
    assert first.json()["semantic_cache"]["stored"] is True
    second = await stack.ask(PW)
    assert second.headers["x-semanticcache"] == "HIT" and second.headers["x-semanticcache-type"] == "exact"
    assert second.json()["choices"] == first.json()["choices"]
    sc = second.json()["semantic_cache"]
    assert sc["hit"] and sc["type"] == "exact" and sc["similarity"] == 1.0 and sc["saved_tokens"] > 0
    assert (
        second.json()["id"].startswith("chatcmpl-sc-")
        and second.headers["x-semanticcache-id"] == sc["entry_id"]
    )
    assert await stack.provider_calls() == 1


async def test_semantic_hit_for_a_paraphrase(stack: Stack) -> None:
    await stack.ask(PW)
    r = await stack.ask("how can I reset my password")
    assert r.headers["x-semanticcache"] == "HIT" and r.headers["x-semanticcache-type"] == "semantic"
    assert await stack.provider_calls() == 1


async def test_guards_send_look_alike_prompts_to_the_provider(stack: Stack) -> None:
    q = "Please write a detailed summary of the quarterly sales report for {} including every key metric"
    await stack.ask(q.format("region 4"))
    r = await stack.ask(q.format("region 5"))
    assert r.headers["x-semanticcache"] == "MISS"
    sc = r.json()["semantic_cache"]
    assert sc["rejected_reason"] == "numbers differ" and sc["rejected_similarity"] > 0.85
    assert await stack.provider_calls() == 2


async def test_model_and_system_prompt_partition_the_cache(stack: Stack) -> None:
    await stack.ask(PW)
    assert (await stack.ask(PW, model="gpt-4o")).headers["x-semanticcache"] == "MISS"
    sys = {"role": "system", "content": "Answer as a pirate"}
    r = await stack.api.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [sys, {"role": "user", "content": PW}]},
    )
    assert r.headers["x-semanticcache"] == "MISS"
    assert await stack.provider_calls() == 3


async def test_namespaces_do_not_share_answers(stack: Stack) -> None:
    await stack.ask(PW, headers={"X-SC-Namespace": "one"})
    assert (await stack.ask(PW, headers={"X-SC-Namespace": "one"})).headers["x-semanticcache"] == "HIT"
    assert (await stack.ask(PW, headers={"X-SC-Namespace": "two"})).headers["x-semanticcache"] == "MISS"


# ── per-request control ──────────────────────────────────────────────────────────────────────────────────────
async def test_bypass_neither_reads_nor_writes(stack: Stack) -> None:
    await stack.ask(PW)
    r = await stack.ask(PW, headers={"X-SC-Cache": "bypass"})
    assert r.headers["x-semanticcache"] == "BYPASS" and r.json()["semantic_cache"]["bypass"] is True
    assert await stack.provider_calls() == 2
    assert (await stack.ask("fresh question", headers={"X-SC-Cache": "bypass"})).headers[
        "x-semanticcache"
    ] == "BYPASS"
    assert (await stack.ask("fresh question")).headers[
        "x-semanticcache"
    ] == "MISS"  # nothing was stored by the bypass


async def test_refresh_skips_the_lookup_but_replaces_the_entry(stack: Stack) -> None:
    first = await stack.ask(PW)
    r = await stack.ask(PW, headers={"X-SC-Cache": "refresh"})
    assert r.headers["x-semanticcache"] == "MISS" and await stack.provider_calls() == 2
    assert r.json()["semantic_cache"]["entry_id"] != first.json()["semantic_cache"]["entry_id"]
    assert (await stack.ask(PW)).json()["semantic_cache"]["entry_id"] == r.json()["semantic_cache"][
        "entry_id"
    ]


async def test_no_store_serves_hits_but_never_saves(stack: Stack) -> None:
    r = await stack.ask(PW, headers={"X-SC-Cache": "no-store"})
    assert r.headers["x-semanticcache"] == "MISS" and r.json()["semantic_cache"]["stored"] is False
    assert (await stack.ask(PW)).headers["x-semanticcache"] == "MISS"


async def test_only_if_cached(stack: Stack) -> None:
    r = await stack.ask(PW, headers={"X-SC-Cache": "only-if-cached"})
    assert (
        r.status_code == 504
        and r.json()["error"]["code"] == "not_cached"
        and await stack.provider_calls() == 0
    )
    await stack.ask(PW)
    assert (await stack.ask(PW, headers={"X-SC-Cache": "only-if-cached"})).headers["x-semanticcache"] == "HIT"


async def test_unknown_cache_mode_is_rejected(stack: Stack) -> None:
    assert (await stack.ask(PW, headers={"X-SC-Cache": "maybe"})).status_code == 422


async def test_ttl_header_sets_the_entry_lifetime(stack: Stack) -> None:
    await stack.ask("short lived", headers={"X-SC-TTL": "1"})
    assert (await stack.ask("short lived")).headers["x-semanticcache"] == "HIT"
    await asyncio.sleep(1.2)
    assert (await stack.ask("short lived")).headers["x-semanticcache"] == "MISS"


async def test_tags_enable_targeted_invalidation(stack: Stack) -> None:
    await stack.ask("what is your pricing", headers={"X-SC-Tags": "pricing, v2"})
    await stack.ask("where is the office", headers={"X-SC-Tags": "company"})
    assert (await stack.api.post("/v1/cache/invalidate", json={"tag": "pricing"})).json() == {"deleted": 1}
    assert (await stack.ask("what is your pricing")).headers["x-semanticcache"] == "MISS"
    assert (await stack.ask("where is the office")).headers["x-semanticcache"] == "HIT"


# ── what must never be cached ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("marker", ["[tool] weather", "[length] essay"])
async def test_tool_calls_and_truncated_answers_are_not_cached(stack: Stack, marker: str) -> None:
    r = await stack.ask(marker)
    assert r.status_code == 200 and r.json()["semantic_cache"]["stored"] is False
    assert (await stack.ask(marker)).headers[
        "x-semanticcache"
    ] == "MISS" and await stack.provider_calls() == 2


async def test_multiple_choices_bypass_the_cache(stack: Stack) -> None:
    assert (await stack.ask(PW, n=3)).headers["x-semanticcache"] == "BYPASS"


async def test_provider_errors_pass_through_and_are_not_cached(stack: Stack) -> None:
    r = await stack.ask("[fail] please")
    assert r.status_code == 500 and r.json()["error"]["code"] == "error"
    assert (await stack.ask("[fail] please")).status_code == 500 and await stack.provider_calls() == 2


async def test_unreachable_provider_is_a_502(stack: Stack) -> None:
    dead = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    )
    stack.app.state.upstream = UpstreamClient("http://down.invalid/v1", client=dead)
    r = await stack.ask("anything")
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_unreachable"


async def test_cache_still_serves_when_the_provider_is_down(stack: Stack) -> None:
    await stack.ask(PW)
    dead = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    )
    stack.app.state.upstream = UpstreamClient("http://down.invalid/v1", client=dead)
    assert (await stack.ask(PW)).headers["x-semanticcache"] == "HIT"
    assert (await stack.ask("how can I reset my password")).headers["x-semanticcache"] == "HIT"


@pytest.mark.parametrize(
    "body",
    [{}, {"model": "m"}, {"model": "m", "messages": []}, {"messages": [{"role": "user", "content": "x"}]}],
)
async def test_invalid_requests_are_422(stack: Stack, body: dict[str, object]) -> None:
    r = await stack.api.post("/v1/chat/completions", json=body)
    assert (
        r.status_code == 422 and r.json()["error"]["code"] == "invalid" and await stack.provider_calls() == 0
    )


async def test_non_json_body_is_422(stack: Stack) -> None:
    r = await stack.api.post(
        "/v1/chat/completions", content="not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422


# ── stampede ─────────────────────────────────────────────────────────────────────────────────────────────────
async def test_concurrent_identical_misses_make_one_provider_call(stack: Stack) -> None:
    await stack.mock.post("/reset")
    results = await asyncio.gather(
        *(stack.ask("a brand new question everyone asks at once") for _ in range(25))
    )
    assert all(r.status_code == 200 for r in results)
    kinds = sorted(r.headers["x-semanticcache"] for r in results)
    assert kinds.count("MISS") == 1 and kinds.count("COALESCED") + kinds.count("HIT") == 24
    assert await stack.provider_calls() == 1
    assert len({r.json()["choices"][0]["message"]["content"] for r in results}) == 1
    s = (await stack.api.get("/v1/stats/overview")).json()["totals"]
    assert s["misses"] == 1 and s["hits"] == 24 and s["cost_saved_usd"] > 0


# ── streaming ────────────────────────────────────────────────────────────────────────────────────────────────
async def test_streaming_replays_a_cached_answer_as_sse(stack: Stack) -> None:
    plain = await stack.ask(PW)
    expected = plain.json()["choices"][0]["message"]["content"]
    r = await stack.ask(PW, stream=True)
    assert r.headers["content-type"].startswith("text/event-stream") and r.headers["x-semanticcache"] == "HIT"
    events = sse_events(r.text)
    assert events[-1] == "[DONE]"
    chunks = [e for e in events if isinstance(e, dict)]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text == expected
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop" and chunks[-1]["semantic_cache"]["hit"] is True
    assert await stack.provider_calls() == 1


async def test_streaming_a_miss_is_forwarded_then_cached(stack: Stack) -> None:
    r = await stack.ask("stream this new question please", stream=True)
    assert r.headers["x-semanticcache"] == "MISS"
    text = "".join(
        c["choices"][0]["delta"].get("content", "") for c in sse_events(r.text) if isinstance(c, dict)
    )
    assert text
    assert (await stack.ask("stream this new question please")).headers["x-semanticcache"] == "HIT"
    assert await stack.provider_calls() == 1
