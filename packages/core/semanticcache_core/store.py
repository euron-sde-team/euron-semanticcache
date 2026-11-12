"""Redis persistence for entries, namespace configuration and statistics.

The Redis client MUST be created with ``decode_responses=False``: embeddings are stored as raw float32 bytes.
"""

from __future__ import annotations

import json
import time
from typing import Any, cast

import numpy as np
from redis.asyncio import Redis

from .embedding import Vector
from .models import CacheEntry, NamespaceConfig
from .scripts import Scripts

STAT_FIELDS = (
    "hits_exact", "hits_semantic", "misses", "bypass", "stores", "errors",
    "tokens_saved_in", "tokens_saved_out", "cost_saved_micro", "latency_saved_ms",
    "cost_spent_micro", "evictions", "rejected_guard",
)  # fmt: skip


def now_ms() -> int:
    return int(time.time() * 1000)


def _s(v: Any) -> str | None:
    if v is None:
        return None
    return v.decode() if isinstance(v, bytes) else v


class RedisStore:
    def __init__(self, redis: Redis, prefix: str = "sc") -> None:
        self.r = redis
        self.prefix = prefix
        self._scripts = Scripts(redis)

    def k(self, ns: str, suffix: str) -> str:
        return f"{self.prefix}:{ns}:{suffix}"

    # ── entries ──────────────────────────────────────────────────────────────
    async def put(
        self, entry: CacheEntry, vec: Vector, prompt_norm: str, exact_hash: str, max_entries: int, ttl_s: int
    ) -> int:
        evicted = await self._scripts.put(
            args=[
                self.prefix, entry.namespace, entry.id, entry.model_dump_json(), vec.astype(np.float32).tobytes(),
                entry.scope, prompt_norm, ttl_s, now_ms(), exact_hash, max_entries,
            ]
        )  # fmt: skip
        return int(evicted)

    async def get(self, ns: str, entry_id: str) -> CacheEntry | None:
        row = await self.r.hmget(self.k(ns, f"e:{entry_id}"), ["json", "hits", "last_hit"])
        if not row or row[0] is None:
            return None
        entry = CacheEntry.model_validate_json(row[0])
        entry.hits = int(row[1] or 0)
        entry.last_hit_at = int(row[2]) if row[2] else None
        return entry

    async def find_exact(self, ns: str, exact_hash: str) -> str | None:
        return _s(await self.r.get(self.k(ns, f"x:{exact_hash}")))

    async def touch(self, ns: str, entry_id: str) -> None:
        await self._scripts.touch(args=[self.prefix, ns, entry_id, now_ms()])

    async def delete(self, ns: str, entry_id: str) -> bool:
        return bool(await self._scripts.delete(args=[self.prefix, ns, entry_id]))

    async def flush(self, ns: str) -> int:
        return int(await self._scripts.flush(args=[self.prefix, ns]))

    async def count(self, ns: str) -> int:
        return int(await self.r.zcard(self.k(ns, "ids")))

    async def list_entries(
        self, ns: str, offset: int = 0, limit: int = 50, q: str | None = None
    ) -> tuple[list[CacheEntry], int]:
        """Most recently used first. With ``q`` the match is a substring of the prompt (case-insensitive)."""
        ids = [_s(i) or "" for i in cast(list[bytes], await self.r.zrevrange(self.k(ns, "ids"), 0, -1))]
        if q:
            needle = q.lower()
            rows = await self._rows(ns, ids, ["pn"])
            ids = [
                i for i, r in zip(ids, rows, strict=True) if r[0] is not None and needle in (_s(r[0]) or "")
            ]
        total = len(ids)
        page = ids[offset : offset + limit]
        entries = [e for e in [await self.get(ns, i) for i in page] if e]
        return entries, total

    async def _rows(self, ns: str, ids: list[str], fields: list[str]) -> list[list[Any]]:
        if not ids:
            return []
        async with self.r.pipeline(transaction=False) as pipe:
            for i in ids:
                pipe.hmget(self.k(ns, f"e:{i}"), fields)
            return cast(list[list[Any]], await pipe.execute())

    # ── index sync ───────────────────────────────────────────────────────────
    async def version(self, ns: str) -> int:
        return int(await self.r.get(self.k(ns, "ver")) or 0)

    async def changes_since(self, ns: str, version: int) -> tuple[int, list[str] | None]:
        """Returns (current version, ops since ``version``) or (version, None) when a full reload is needed
        (log trimmed, a flush, or a gap)."""
        current = await self.version(ns)
        if current == version:
            return current, []
        log = cast(
            list[tuple[bytes, float]],
            await self.r.zrangebyscore(self.k(ns, "log"), version + 1, current, withscores=True),
        )
        ops = [_s(m) or "" for m, _ in log]
        if len(ops) != current - version or "f" in ops:
            return current, None
        return current, ops

    async def all_ids(self, ns: str) -> list[str]:
        return [_s(i) or "" for i in cast(list[bytes], await self.r.zrange(self.k(ns, "ids"), 0, -1))]

    async def load_vectors(self, ns: str, ids: list[str]) -> list[tuple[str, Vector, str, str] | None]:
        """For each id: (id, vector, scope, normalised prompt), or None when the entry has expired."""
        rows = await self._rows(ns, ids, ["vec", "scope", "pn"])
        out: list[tuple[str, Vector, str, str] | None] = []
        for i, (vec, scope, pn) in zip(ids, rows, strict=True):
            if vec is None:
                out.append(None)
            else:
                out.append((i, np.frombuffer(vec, dtype=np.float32), _s(scope) or "", _s(pn) or ""))
        return out

    async def prune(self, ns: str, ids: list[str]) -> None:
        if ids:
            await self.r.zrem(self.k(ns, "ids"), *ids)

    # ── namespaces ───────────────────────────────────────────────────────────
    async def get_config(self, ns: str) -> NamespaceConfig:
        raw = await self.r.get(self.k(ns, "cfg"))
        return NamespaceConfig.model_validate_json(raw) if raw else NamespaceConfig()

    async def set_config(self, ns: str, cfg: NamespaceConfig) -> None:
        async with self.r.pipeline(transaction=True) as pipe:
            pipe.set(self.k(ns, "cfg"), cfg.model_dump_json())
            pipe.sadd(f"{self.prefix}:namespaces", ns)
            await pipe.execute()

    async def register_namespace(self, ns: str) -> None:
        await self.r.sadd(f"{self.prefix}:namespaces", ns)

    async def namespaces(self) -> list[str]:
        members = cast(set[bytes], await self.r.smembers(f"{self.prefix}:namespaces"))
        return sorted(_s(n) or "" for n in members)

    async def drop_namespace(self, ns: str) -> None:
        await self.flush(ns)
        await self.r.delete(self.k(ns, "cfg"), self.k(ns, "stats"), self.k(ns, "ver"), self.k(ns, "log"))
        await self.r.srem(f"{self.prefix}:namespaces", ns)

    # ── statistics ───────────────────────────────────────────────────────────
    async def incr(self, ns: str, fields: dict[str, int]) -> None:
        minute = int(time.time() // 60)
        mk = f"{self.prefix}:m:{ns}:{minute}"
        async with self.r.pipeline(transaction=False) as pipe:
            for f, n in fields.items():
                if n:
                    pipe.hincrby(self.k(ns, "stats"), f, n)
                    pipe.hincrby(mk, f, n)
            pipe.expire(mk, 7200)
            await pipe.execute()

    async def stats(self, ns: str) -> dict[str, int]:
        raw = cast(dict[bytes, bytes], await self.r.hgetall(self.k(ns, "stats")))
        out = dict.fromkeys(STAT_FIELDS, 0)
        for f, v in raw.items():
            out[_s(f) or ""] = int(v)
        return out

    async def series(self, namespaces: list[str], minutes: int) -> list[dict[str, int]]:
        now_min = int(time.time() // 60)
        async with self.r.pipeline(transaction=False) as pipe:
            for off in range(minutes - 1, -1, -1):
                for ns in namespaces:
                    pipe.hgetall(f"{self.prefix}:m:{ns}:{now_min - off}")
            rows = await pipe.execute()
        out: list[dict[str, int]] = []
        idx = 0
        for off in range(minutes - 1, -1, -1):
            point = {
                "minute": now_min - off,
                "hits": 0,
                "misses": 0,
                "cost_saved_micro": 0,
                "tokens_saved": 0,
            }
            for _ in namespaces:
                row = {(_s(k) or ""): int(v) for k, v in cast(dict[bytes, bytes], rows[idx]).items()}
                idx += 1
                point["hits"] += row.get("hits_exact", 0) + row.get("hits_semantic", 0)
                point["misses"] += row.get("misses", 0)
                point["cost_saved_micro"] += row.get("cost_saved_micro", 0)
                point["tokens_saved"] += row.get("tokens_saved_in", 0) + row.get("tokens_saved_out", 0)
            out.append(point)
        return out

    async def ping(self) -> bool:
        return bool(await self.r.ping())

    def dump_config(self, cfg: NamespaceConfig) -> str:
        return json.dumps(cfg.model_dump())
