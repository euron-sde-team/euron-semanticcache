"""SemanticCache: exact and semantic lookup inside a safety scope, storage, explanation and accounting."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from redis.asyncio import Redis

from .embedding import Embedder, Vector
from .ids import new_id
from .index import NamespaceIndex
from .models import (
    CacheEntry,
    ChatRequest,
    Lookup,
    MatchType,
    NamespaceConfig,
    Neighbor,
    Usage,
)
from .pricing import Pricing
from .store import RedisStore, now_ms
from .text import guard_failure, normalize

T = TypeVar("T")
CONFIG_TTL_S = 2.0
MAX_CANDIDATES = 5


@dataclass(slots=True)
class Prepared:
    """Everything derived from a request once, then reused for lookup and store."""

    query: str
    norm: str
    scope: str
    exact_hash: str
    vector: Vector | None


class SingleFlight:
    """Collapses concurrent identical misses (a stampede) into one upstream call, per process."""

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future[Any]] = {}

    async def run(self, key: str, fn: Callable[[], Awaitable[T]]) -> tuple[T, bool]:
        """Returns (result, shared): shared is True when this caller reused another caller's work."""
        existing = self._inflight.get(key)
        if existing is not None:
            return await asyncio.shield(existing), True
        fut: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            result = await fn()
            fut.set_result(result)
            return result, False
        except BaseException as exc:
            fut.set_exception(exc)
            fut.exception()  # mark retrieved so an unshared failure does not log "never retrieved"
            raise
        finally:
            self._inflight.pop(key, None)


class SemanticCache:
    def __init__(
        self,
        redis: Redis,
        embedder: Embedder,
        *,
        prefix: str = "sc",
        pricing: Pricing | None = None,
    ) -> None:
        self.store = RedisStore(redis, prefix)
        self.embedder = embedder
        self.pricing = pricing or Pricing()
        self.flights = SingleFlight()
        self._indexes: dict[str, NamespaceIndex] = {}
        self._cfg: dict[str, tuple[float, NamespaceConfig]] = {}

    # ── configuration ────────────────────────────────────────────────────────
    async def config(self, ns: str) -> NamespaceConfig:
        cached = self._cfg.get(ns)
        if cached and time.monotonic() - cached[0] < CONFIG_TTL_S:
            return cached[1]
        cfg = await self.store.get_config(ns)
        self._cfg[ns] = (time.monotonic(), cfg)
        return cfg

    async def set_config(self, ns: str, cfg: NamespaceConfig) -> None:
        await self.store.set_config(ns, cfg)
        self._cfg.pop(ns, None)

    def _index(self, ns: str) -> NamespaceIndex:
        idx = self._indexes.get(ns)
        if idx is None:
            idx = self._indexes[ns] = NamespaceIndex(ns)
        return idx

    # ── preparation ──────────────────────────────────────────────────────────
    async def prepare(self, req: ChatRequest, *, embed: bool = True) -> Prepared:
        query = req.query_text()
        norm = normalize(query)
        scope = req.scope_key()
        exact = hashlib.sha256(f"{scope}\x00{norm}".encode()).hexdigest()[:32]
        vec = (await self.embedder.embed([query]))[0] if embed else None
        return Prepared(query, norm, scope, exact, vec)

    # ── lookup ───────────────────────────────────────────────────────────────
    async def lookup(
        self, ns: str, req: ChatRequest, prepared: Prepared | None = None, *, record: bool = True
    ) -> Lookup:
        cfg = await self.config(ns)
        prep = prepared or await self.prepare(req, embed=cfg.semantic)
        result = await self._find(ns, cfg, prep)
        if record:
            await self._record_lookup(ns, result)
        return result

    async def _find(self, ns: str, cfg: NamespaceConfig, prep: Prepared) -> Lookup:
        if not cfg.enabled:
            return Lookup(hit=False)
        exact_id = await self.store.find_exact(ns, prep.exact_hash)
        if exact_id:
            entry = await self.store.get(ns, exact_id)
            if entry:
                return Lookup(hit=True, match=MatchType.EXACT, similarity=1.0, entry=entry)
        if not cfg.semantic:
            return Lookup(hit=False)
        if prep.vector is None:
            prep.vector = (await self.embedder.embed([prep.query]))[0]
        idx = self._index(ns)
        await idx.sync(self.store)
        rejected: tuple[float, str, str] | None = None
        for cand in idx.search(prep.vector, prep.scope, MAX_CANDIDATES):
            if cand.similarity < cfg.threshold:
                if rejected is None:
                    rejected = (cand.similarity, "below threshold", cand.prompt_norm)
                break
            reason = guard_failure(prep.norm, cand.prompt_norm) if cfg.guards else None
            if reason:
                if rejected is None or cand.similarity > rejected[0]:
                    rejected = (cand.similarity, reason, cand.prompt_norm)
                continue
            entry = await self.store.get(ns, cand.id)
            if entry is None:  # expired since the index was built
                idx.discard(cand.id)
                continue
            return Lookup(hit=True, match=MatchType.SEMANTIC, similarity=cand.similarity, entry=entry)
        out = Lookup(hit=False)
        if rejected:
            out.rejected_similarity, out.rejected_reason, out.rejected_prompt = (
                round(rejected[0], 4),
                rejected[1],
                rejected[2],
            )
        return out

    async def _record_lookup(self, ns: str, result: Lookup) -> None:
        if not result.hit or result.entry is None or result.match is None:
            await self.store.incr(
                ns,
                {"misses": 1, "rejected_guard": int(result.rejected_reason not in (None, "below threshold"))},
            )
            return
        e = result.entry
        await self.store.touch(ns, e.id)
        await self.store.incr(
            ns,
            {
                f"hits_{result.match.value}": 1,
                "tokens_saved_in": e.usage.prompt_tokens,
                "tokens_saved_out": e.usage.completion_tokens,
                "cost_saved_micro": e.cost_micro_usd,
                "latency_saved_ms": e.latency_ms,
            },
        )

    # ── store ────────────────────────────────────────────────────────────────
    async def put(
        self,
        ns: str,
        req: ChatRequest,
        response: dict[str, Any],
        usage: Usage,
        latency_ms: int,
        prepared: Prepared | None = None,
        *,
        ttl_s: int | None = None,
        tags: list[str] | None = None,
    ) -> CacheEntry:
        cfg = await self.config(ns)
        prep = prepared or await self.prepare(req)
        if prep.vector is None:
            prep.vector = (await self.embedder.embed([prep.query]))[0]
        ttl = min(ttl_s or cfg.ttl_seconds, 31_536_000)
        now = now_ms()
        cost = self.pricing.cost_micro(req.model, usage)
        entry = CacheEntry(
            id=new_id(), namespace=ns, model=req.model, prompt=prep.query, scope=prep.scope, response=response,
            usage=usage, cost_micro_usd=cost, latency_ms=latency_ms, created_at=now, expires_at=now + ttl * 1000,
            tags=sorted(set(tags or [])),
        )  # fmt: skip
        await self.store.register_namespace(ns)
        evicted = await self.store.put(entry, prep.vector, prep.norm, prep.exact_hash, cfg.max_entries, ttl)
        await self.store.incr(ns, {"stores": 1, "cost_spent_micro": cost, "evictions": evicted})
        return entry

    async def import_entry(self, ns: str, entry: CacheEntry) -> CacheEntry | None:
        """Restores an exported entry (embedding it again, so a changed embedder still works).
        Returns None when it has already expired."""
        now = now_ms()
        if entry.expires_at is not None and entry.expires_at <= now:
            return None
        cfg = await self.config(ns)
        norm = normalize(entry.prompt)
        exact = hashlib.sha256(f"{entry.scope}\x00{norm}".encode()).hexdigest()[:32]
        vec = (await self.embedder.embed([entry.prompt]))[0]
        ttl = max(1, ((entry.expires_at or now + cfg.ttl_seconds * 1000) - now) // 1000)
        restored = entry.model_copy(update={"namespace": ns, "id": new_id(), "hits": 0, "last_hit_at": None})
        await self.store.register_namespace(ns)
        await self.store.put(restored, vec, norm, exact, cfg.max_entries, ttl)
        return restored

    async def record_coalesced(self, ns: str, entry: CacheEntry) -> None:
        """A concurrent identical miss that shared another request's upstream call also saved money."""
        await self.store.incr(
            ns,
            {
                "coalesced": 1, "tokens_saved_in": entry.usage.prompt_tokens,
                "tokens_saved_out": entry.usage.completion_tokens, "cost_saved_micro": entry.cost_micro_usd,
                "latency_saved_ms": entry.latency_ms,
            },
        )  # fmt: skip

    # ── explain ──────────────────────────────────────────────────────────────
    async def explain(self, ns: str, req: ChatRequest, k: int = 8) -> list[Neighbor]:
        """Nearest cached prompts, with whether each shares the scope and why it would or would not be a hit."""
        cfg = await self.config(ns)
        prep = await self.prepare(req)
        idx = self._index(ns)
        await idx.sync(self.store)
        assert prep.vector is not None
        out: list[Neighbor] = []
        for cand in idx.search(prep.vector, prep.scope, k, include_out_of_scope=True):
            guard = guard_failure(prep.norm, cand.prompt_norm) if cfg.guards else None
            hit = cand.in_scope and cand.similarity >= cfg.threshold and guard is None
            out.append(
                Neighbor(
                    id=cand.id, prompt=cand.prompt_norm, similarity=round(cand.similarity, 4),
                    in_scope=cand.in_scope, guard=guard, would_hit=hit,
                )
            )  # fmt: skip
        return out

    # ── invalidation ─────────────────────────────────────────────────────────
    async def invalidate_tag(self, ns: str, tag: str) -> int:
        removed = 0
        for entry in (await self.store.list_entries(ns, 0, 100_000))[0]:
            if tag in entry.tags and await self.store.delete(ns, entry.id):
                removed += 1
        return removed
