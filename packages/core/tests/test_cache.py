"""Matching behaviour of the cache against a real Redis."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from semanticcache_core import (
    ChatMessage,
    ChatRequest,
    MatchType,
    NamespaceConfig,
    SemanticCache,
    SingleFlight,
    Usage,
)

pytestmark = pytest.mark.integration
RESP: dict[str, Any] = {"choices": [{"message": {"role": "assistant", "content": "answer"}}]}


def chat(q: str, *, system: str = "Be brief", model: str = "gpt-4o-mini", **kw: Any) -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[ChatMessage(role="system", content=system), ChatMessage(role="user", content=q)],
        **kw,
    )


async def store(cache: SemanticCache, q: str, ns: str = "t", **kw: Any) -> Any:
    return await cache.put(ns, chat(q, **kw), RESP, Usage(prompt_tokens=100, completion_tokens=50), 1200)


async def test_miss_then_exact_hit(cache: SemanticCache) -> None:
    assert (await cache.lookup("t", chat("How do I reset my password?"))).hit is False
    entry = await store(cache, "How do I reset my password?")
    hit = await cache.lookup("t", chat("How do I reset my password?"))
    assert hit.hit and hit.match == MatchType.EXACT and hit.similarity == 1.0 and hit.entry
    assert hit.entry.id == entry.id and hit.entry.response == RESP


async def test_exact_match_ignores_case_and_whitespace(cache: SemanticCache) -> None:
    await store(cache, "How do I reset my password?")
    hit = await cache.lookup("t", chat("  how DO i   reset my password? "))
    assert hit.hit and hit.match == MatchType.EXACT


async def test_semantic_hit_for_a_paraphrase(cache: SemanticCache) -> None:
    await store(cache, "How do I reset my password?")
    hit = await cache.lookup("t", chat("how can I reset my password"))
    assert hit.hit and hit.match == MatchType.SEMANTIC and hit.similarity >= 0.85


async def test_unrelated_prompt_misses(cache: SemanticCache) -> None:
    await store(cache, "How do I reset my password?")
    assert (await cache.lookup("t", chat("What is the capital of France?"))).hit is False


LONG = "Please write a detailed summary of the quarterly sales report for {} including every key metric"


async def test_guards_stop_look_alike_prompts(cache: SemanticCache) -> None:
    """Each pair is close enough that embedding similarity ALONE would serve the wrong answer."""
    await store(cache, LONG.format("region 4"))
    await store(cache, "Explain in plain language why cats really do like drinking milk so much")
    await store(
        cache,
        "Explain step by step how to fix error E404 in my web application that is running behind nginx on a small server",
    )
    for q, reason in [
        (LONG.format("region 5"), "numbers differ"),
        ("Explain in plain language why cats really don't like drinking milk so much", "negation differs"),
        (
            "Explain step by step how to fix error E500 in my web application that is running behind nginx on a small server",
            "identifiers differ",
        ),
    ]:
        miss = await cache.lookup("t", chat(q))
        assert miss.hit is False and miss.rejected_reason == reason, q
        assert miss.rejected_similarity and miss.rejected_similarity > 0.85, (
            "the embedding alone would have matched"
        )


async def test_guards_can_be_disabled_per_namespace(cache: SemanticCache) -> None:
    await cache.set_config("t", NamespaceConfig(guards=False, threshold=0.85))
    await store(cache, LONG.format("region 4"))
    assert (await cache.lookup("t", chat(LONG.format("region 5")))).hit is True


async def test_threshold_is_respected(cache: SemanticCache) -> None:
    await store(cache, "How do I reset my password?")
    probe = chat("password reset steps please")
    await cache.set_config("t", NamespaceConfig(threshold=0.5))
    loose = await cache.lookup("t", probe)
    await cache.set_config("t", NamespaceConfig(threshold=1.0))
    cache._cfg.clear()
    strict = await cache.lookup("t", probe)
    assert loose.hit and not strict.hit and strict.rejected_reason == "below threshold"


async def test_semantic_matching_can_be_turned_off(cache: SemanticCache) -> None:
    await cache.set_config("t", NamespaceConfig(semantic=False))
    await store(cache, "How do I reset my password?")
    assert (await cache.lookup("t", chat("how can I reset my password"))).hit is False
    assert (await cache.lookup("t", chat("How do I reset my password?"))).match == MatchType.EXACT


async def test_disabled_namespace_never_hits(cache: SemanticCache) -> None:
    await store(cache, "q one")
    await cache.set_config("t", NamespaceConfig(enabled=False))
    assert (await cache.lookup("t", chat("q one"))).hit is False


# ── isolation: the properties that make the cache safe to run in front of real traffic ──────────────────────────
async def test_namespaces_are_isolated(cache: SemanticCache) -> None:
    await store(cache, "How do I reset my password?", ns="tenant-a")
    assert (await cache.lookup("tenant-b", chat("How do I reset my password?"))).hit is False
    assert (await cache.lookup("tenant-b", chat("how can I reset my password"))).hit is False


@pytest.mark.parametrize(
    "other",
    [
        {"model": "gpt-4o"},
        {"system": "You are a pirate"},
    ],
)
async def test_a_hit_never_crosses_model_or_system_prompt(
    cache: SemanticCache, other: dict[str, str]
) -> None:
    await store(cache, "How do I reset my password?")
    assert (await cache.lookup("t", chat("How do I reset my password?", **other))).hit is False
    assert (await cache.lookup("t", chat("how can I reset my password", **other))).hit is False


async def test_a_hit_never_crosses_conversation_history(cache: SemanticCache) -> None:
    def convo(first: str, last: str) -> ChatRequest:
        return ChatRequest(
            model="m",
            messages=[
                ChatMessage(role="user", content=first),
                ChatMessage(role="assistant", content="sure"),
                ChatMessage(role="user", content=last),
            ],
        )

    await cache.put("t", convo("Tell me about Python", "and its speed?"), RESP, Usage(), 10)
    assert (await cache.lookup("t", convo("Tell me about Python", "and its speed?"))).hit is True
    assert (await cache.lookup("t", convo("Tell me about Rust", "and its speed?"))).hit is False
    assert (await cache.lookup("t", convo("Tell me about Rust", "and its speed"))).hit is False


async def test_output_shape_params_partition_the_cache(cache: SemanticCache) -> None:
    await store(cache, "List three colours", response_format={"type": "json_object"})
    assert (await cache.lookup("t", chat("List three colours"))).hit is False
    assert (await cache.lookup("t", chat("List three colours", response_format={"type": "json_object"}))).hit


# ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────────
async def test_ttl_expiry(cache: SemanticCache) -> None:
    await cache.put("t", chat("short lived"), RESP, Usage(), 10, ttl_s=1)
    assert (await cache.lookup("t", chat("short lived"))).hit
    await asyncio.sleep(1.2)
    assert (await cache.lookup("t", chat("short lived"))).hit is False
    assert (await cache.lookup("t", chat("short lived!"))).hit is False  # semantic path sees the expiry too


async def test_delete_removes_exact_and_semantic_matches(cache: SemanticCache) -> None:
    e = await store(cache, "How do I reset my password?")
    assert (await cache.lookup("t", chat("how can I reset my password"))).hit
    assert await cache.store.delete("t", e.id) is True
    assert await cache.store.delete("t", e.id) is False
    assert (await cache.lookup("t", chat("How do I reset my password?"))).hit is False
    assert (await cache.lookup("t", chat("how can I reset my password"))).hit is False


async def test_flush_clears_a_namespace_only(cache: SemanticCache) -> None:
    await store(cache, "alpha question", ns="a")
    await store(cache, "beta question", ns="b")
    assert await cache.store.flush("a") == 1
    assert (await cache.lookup("a", chat("alpha question"))).hit is False
    assert (await cache.lookup("b", chat("beta question"))).hit is True


async def test_lru_eviction_keeps_the_most_recently_used(cache: SemanticCache) -> None:
    await cache.set_config("t", NamespaceConfig(max_entries=10))
    first = await store(cache, "question number 0 about topic zero")
    for i in range(1, 10):
        await store(cache, f"question number {i} about topic {'abcdefghij'[i]}")
    await asyncio.sleep(0.01)
    await cache.lookup("t", chat("question number 0 about topic zero"))  # touch the oldest: now the freshest
    await store(cache, "one more question about topic zebra")
    assert await cache.store.count("t") == 10
    assert await cache.store.get("t", first.id) is not None
    assert (await cache.store.stats("t"))["evictions"] == 1


async def test_re_storing_the_same_prompt_replaces_the_entry(cache: SemanticCache) -> None:
    a = await store(cache, "same prompt")
    b = await store(cache, "same prompt")
    assert await cache.store.count("t") == 1
    assert await cache.store.get("t", a.id) is None
    assert (await cache.lookup("t", chat("same prompt"))).entry.id == b.id  # type: ignore[union-attr]


async def test_invalidate_by_tag(cache: SemanticCache) -> None:
    await cache.put("t", chat("pricing question"), RESP, Usage(), 5, tags=["pricing"])
    await cache.put("t", chat("shipping question"), RESP, Usage(), 5, tags=["shipping"])
    assert await cache.invalidate_tag("t", "pricing") == 1
    assert (await cache.lookup("t", chat("pricing question"))).hit is False
    assert (await cache.lookup("t", chat("shipping question"))).hit is True


# ── accounting ───────────────────────────────────────────────────────────────────────────────────────────────
async def test_hits_record_what_they_saved(cache: SemanticCache) -> None:
    e = await store(cache, "How do I reset my password?")
    # gpt-4o-mini: 100 in * 0.15 + 50 out * 0.60 = 45 micro-dollars
    assert e.cost_micro_usd == 45
    await cache.lookup("t", chat("How do I reset my password?"))
    await cache.lookup("t", chat("how can I reset my password"))
    await cache.lookup("t", chat("unrelated geography question"))
    s = await cache.store.stats("t")
    assert (s["hits_exact"], s["hits_semantic"], s["misses"], s["stores"]) == (1, 1, 1, 1)
    assert s["cost_saved_micro"] == 90 and s["tokens_saved_in"] == 200 and s["tokens_saved_out"] == 100
    assert s["latency_saved_ms"] == 2400 and s["cost_spent_micro"] == 45
    got = await cache.store.get("t", e.id)
    assert got and got.hits == 2 and got.last_hit_at


async def test_per_minute_series(cache: SemanticCache) -> None:
    await store(cache, "series question")
    await cache.lookup("t", chat("series question"))
    pts = await cache.store.series(["t"], 3)
    assert len(pts) == 3 and pts[-1]["hits"] == 1 and pts[-1]["cost_saved_micro"] == 45


# ── explain ──────────────────────────────────────────────────────────────────────────────────────────────────
async def test_explain_lists_neighbours_with_verdicts(cache: SemanticCache) -> None:
    await store(cache, "How do I reset my password?")
    await store(cache, "What is the capital of France?")
    await store(cache, "How do I reset my password?", system="Other system")
    ns = await cache.explain("t", chat("how can I reset my password"))
    best = ns[0]
    assert best.would_hit and best.in_scope and best.similarity > 0.8
    assert any(not n.in_scope for n in ns), "out-of-scope neighbours are shown but never hit"
    assert all(not n.would_hit for n in ns if not n.in_scope)


# ── multi-replica sync ───────────────────────────────────────────────────────────────────────────────────────
async def test_another_replica_sees_adds_and_deletes_incrementally(cache: SemanticCache) -> None:
    other = SemanticCache(cache.store.r, cache.embedder, prefix=cache.store.prefix)
    assert (await other.lookup("t", chat("replica question"), record=False)).hit is False
    e = await store(cache, "replica question")
    assert (await other.lookup("t", chat("replica questions"), record=False)).hit is True
    full_reloads = other._index("t").version
    await cache.store.delete("t", e.id)
    assert (await other.lookup("t", chat("replica questions"), record=False)).hit is False
    assert other._index("t").version > full_reloads


async def test_flush_forces_other_replicas_to_reload(cache: SemanticCache) -> None:
    other = SemanticCache(cache.store.r, cache.embedder, prefix=cache.store.prefix)
    await store(cache, "to be flushed")
    assert (await other.lookup("t", chat("to be flushed!"), record=False)).hit
    await cache.store.flush("t")
    assert (await other.lookup("t", chat("to be flushed!"), record=False)).hit is False


async def test_trimmed_log_falls_back_to_a_full_reload(cache: SemanticCache) -> None:
    other = SemanticCache(cache.store.r, cache.embedder, prefix=cache.store.prefix)
    await other.lookup("t", chat("warm up"), record=False)
    await cache.store.r.set(cache.store.k("t", "ver"), 5000)  # simulate many missed changes
    await store(cache, "after the gap")
    assert (await other.lookup("t", chat("after the gap!"), record=False)).hit is True


# ── stampede protection ──────────────────────────────────────────────────────────────────────────────────────
async def test_single_flight_collapses_concurrent_identical_calls() -> None:
    sf = SingleFlight()
    calls = 0

    async def slow() -> int:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return 42

    results = await asyncio.gather(*(sf.run("k", slow) for _ in range(20)))
    assert calls == 1
    assert [r for r, _ in results] == [42] * 20
    assert sum(1 for _, shared in results if shared) == 19
    assert (await sf.run("k", slow))[1] is False and calls == 2  # a later call starts fresh


async def test_single_flight_propagates_errors_to_every_waiter_and_recovers() -> None:
    sf = SingleFlight()

    async def boom() -> int:
        await asyncio.sleep(0.05)
        raise RuntimeError("upstream down")

    results = await asyncio.gather(*(sf.run("k", boom) for _ in range(5)), return_exceptions=True)
    assert all(isinstance(r, RuntimeError) for r in results)

    async def ok() -> int:
        return 1

    assert (await sf.run("k", ok))[0] == 1


# ── export / import ──────────────────────────────────────────────────────────────────────────────────────────
async def test_import_entry_restores_into_another_namespace_and_still_matches(cache: SemanticCache) -> None:
    original = await store(cache, "How do I reset my password?", ns="src")
    restored = await cache.import_entry("dst", original)
    assert restored and restored.id != original.id and restored.namespace == "dst" and restored.hits == 0
    assert (await cache.lookup("dst", chat("How do I reset my password?"))).match == MatchType.EXACT
    assert (await cache.lookup("dst", chat("how can I reset my password"))).hit is True
    assert (await cache.lookup("dst", chat("how can I reset my password", system="other"))).hit is False


async def test_import_entry_skips_expired_and_keeps_remaining_ttl(cache: SemanticCache) -> None:
    e = await cache.put("src", chat("ttl question"), RESP, Usage(), 5, ttl_s=100)
    expired = e.model_copy(update={"expires_at": 1})
    assert await cache.import_entry("dst", expired) is None
    restored = await cache.import_entry("dst", e)
    assert restored
    ttl = await cache.store.r.ttl(cache.store.k("dst", f"e:{restored.id}"))
    assert 90 <= ttl <= 100


async def test_coalesced_requests_count_as_savings(cache: SemanticCache) -> None:
    e = await store(cache, "coalesce me")
    await cache.record_coalesced("t", e)
    s = await cache.store.stats("t")
    assert s["coalesced"] == 1 and s["cost_saved_micro"] == e.cost_micro_usd


async def test_explain_reports_a_guard_only_for_candidates_that_were_near_enough(
    cache: SemanticCache,
) -> None:
    """Regression: unrelated prompts were labelled 'blocked: numbers differ' although they never came close."""
    await store(cache, LONG.format("region 4"))
    await store(cache, "What is the capital of France?")
    ns = await cache.explain("t", chat(LONG.format("region 5")))
    near = next(n for n in ns if "region 4" in n.prompt)
    far = next(n for n in ns if "france" in n.prompt)
    assert near.guard == "numbers differ" and not near.would_hit
    assert far.similarity < 0.85 and far.guard is None and not far.would_hit
