"""Aggregates per-namespace counters into the figures the console and `/v1/stats/overview` show."""

from __future__ import annotations

from semanticcache_core import SemanticCache

from .schemas import NamespaceSummary, Overview, SeriesPoint, Totals


def _rate(hits: int, total: int) -> float:
    return round(hits / total, 4) if total else 0.0


async def namespace_summary(cache: SemanticCache, ns: str) -> NamespaceSummary:
    s = await cache.store.stats(ns)
    hits = s["hits_exact"] + s["hits_semantic"] + s["coalesced"]
    return NamespaceSummary(
        name=ns, config=await cache.config(ns), entries=await cache.store.count(ns),
        requests=hits + s["misses"], hits=hits, misses=s["misses"], hit_rate=_rate(hits, hits + s["misses"]),
        cost_saved_usd=round(s["cost_saved_micro"] / 1e6, 6), tokens_saved=s["tokens_saved_in"] + s["tokens_saved_out"],
    )  # fmt: skip


async def overview(cache: SemanticCache, namespaces: list[str], minutes: int) -> Overview:
    stats = {ns: await cache.store.stats(ns) for ns in namespaces}
    agg = (
        {k: sum(s[k] for s in stats.values()) for k in next(iter(stats.values()), {"x": 0})} if stats else {}
    )

    def g(key: str) -> int:
        return agg.get(key, 0)

    hits = g("hits_exact") + g("hits_semantic") + g("coalesced")
    requests = hits + g("misses")
    saved, spent = g("cost_saved_micro"), g("cost_spent_micro")
    entries = sum([await cache.store.count(ns) for ns in namespaces])
    totals = Totals(
        requests=requests, hits=hits, hits_exact=g("hits_exact"), hits_semantic=g("hits_semantic"),
        coalesced=g("coalesced"), misses=g("misses"), bypass=g("bypass"), hit_rate=_rate(hits, requests),
        tokens_saved=g("tokens_saved_in") + g("tokens_saved_out"), cost_saved_usd=round(saved / 1e6, 6),
        cost_spent_usd=round(spent / 1e6, 6),
        # Share of what the same traffic would have cost without a cache that the cache absorbed.
        savings_pct=round(saved / (saved + spent), 4) if saved + spent else 0.0,
        latency_saved_ms=g("latency_saved_ms"), avg_latency_saved_ms=round(g("latency_saved_ms") / hits) if hits else 0,
        entries=entries, rejected_guard=g("rejected_guard"), evictions=g("evictions"),
    )  # fmt: skip
    series = [
        SeriesPoint(
            minute=p["minute"], hits=p["hits"], misses=p["misses"],
            cost_saved_usd=round(p["cost_saved_micro"] / 1e6, 6), tokens_saved=p["tokens_saved"],
        )
        for p in await cache.store.series(namespaces, minutes)
    ]  # fmt: skip
    summaries = [await namespace_summary(cache, ns) for ns in namespaces]
    return Overview(totals=totals, namespaces=summaries, series=series)
