"""Prometheus metrics: cache counters are computed from Redis at scrape time; HTTP metrics are in-process."""

from __future__ import annotations

from collections.abc import Iterable

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from semanticcache_core import SemanticCache


class ApiMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "semanticcache_http_requests_total",
            "HTTP requests",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "semanticcache_http_request_seconds",
            "HTTP request latency",
            ["method", "route"],
            registry=self.registry,
        )
        self.proxy = Counter(
            "semanticcache_proxy_requests_total", "Proxy requests by outcome", ["namespace", "result"],
            registry=self.registry,
        )  # fmt: skip

    async def render(self, cache: SemanticCache) -> bytes:
        entries = GaugeMetricFamily("semanticcache_entries", "Cached entries", labels=["namespace"])
        results = CounterMetricFamily(
            "semanticcache_lookups", "Lifetime lookup outcomes", labels=["namespace", "result"]
        )
        saved_usd = CounterMetricFamily(
            "semanticcache_cost_saved_usd", "Lifetime USD saved", labels=["namespace"]
        )
        spent_usd = CounterMetricFamily(
            "semanticcache_cost_spent_usd", "Lifetime USD spent filling the cache", labels=["namespace"]
        )
        tokens = CounterMetricFamily(
            "semanticcache_tokens_saved", "Lifetime tokens saved", labels=["namespace", "direction"]
        )
        for ns in await cache.store.namespaces():
            s = await cache.store.stats(ns)
            entries.add_metric([ns], await cache.store.count(ns))
            for r in ("hits_exact", "hits_semantic", "misses", "bypass", "coalesced"):
                results.add_metric([ns, r.removeprefix("hits_")], s[r])
            saved_usd.add_metric([ns], s["cost_saved_micro"] / 1e6)
            spent_usd.add_metric([ns], s["cost_spent_micro"] / 1e6)
            tokens.add_metric([ns, "input"], s["tokens_saved_in"])
            tokens.add_metric([ns, "output"], s["tokens_saved_out"])

        class _Snapshot:
            def collect(self) -> Iterable[object]:
                return [entries, results, saved_usd, spent_usd, tokens]

        reg = CollectorRegistry()
        reg.register(_Snapshot())  # type: ignore[arg-type]
        return generate_latest(self.registry) + generate_latest(reg)
