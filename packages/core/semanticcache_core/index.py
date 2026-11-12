"""In-memory vector index for one namespace: a float32 matrix searched by dot product.

Brute-force search is exact and fast at the sizes a response cache holds (a few thousand to ~100k entries; 100k x 512
float32 is ~200 MB and a query is a single matrix-vector product). Every replica keeps its own copy and syncs from the
Redis change log, so adds and deletes made by one replica reach the others without a full reload.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np

from .embedding import Vector
from .store import RedisStore


def _scope_int(scope: str) -> int:
    return int(scope[:15], 16) if scope else 0


@dataclass(slots=True)
class Candidate:
    id: str
    similarity: float
    prompt_norm: str
    in_scope: bool


class NamespaceIndex:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.version = -1
        self._lock = asyncio.Lock()
        self._dim = 0
        self._m: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self._n = 0
        self._ids: list[str] = []
        self._scopes = np.zeros(0, dtype=np.int64)
        self._prompts: list[str] = []
        self._row: dict[str, int] = {}

    def __len__(self) -> int:
        return self._n

    # ── mutation (always under the lock) ─────────────────────────────────────
    def _reset(self, dim: int) -> None:
        self._dim = dim
        self._m = np.zeros((64, dim), dtype=np.float32)
        self._scopes = np.zeros(64, dtype=np.int64)
        self._n = 0
        self._ids, self._prompts, self._row = [], [], {}

    def _add(self, id_: str, vec: Vector, scope: str, prompt_norm: str) -> None:
        if self._dim == 0:
            self._reset(int(vec.shape[0]))
        if vec.shape[0] != self._dim:
            return  # produced by a different embedder: unusable here until re-embedded
        if id_ in self._row:
            self._remove(id_)
        if self._n == self._m.shape[0]:
            self._m = np.vstack([self._m, np.zeros_like(self._m)])
            self._scopes = np.concatenate([self._scopes, np.zeros_like(self._scopes)])
        self._m[self._n] = vec
        self._scopes[self._n] = _scope_int(scope)
        self._ids.append(id_)
        self._prompts.append(prompt_norm)
        self._row[id_] = self._n
        self._n += 1

    def _remove(self, id_: str) -> None:
        row = self._row.pop(id_, None)
        if row is None:
            return
        last = self._n - 1
        if row != last:  # swap-remove keeps the matrix dense
            self._m[row] = self._m[last]
            self._scopes[row] = self._scopes[last]
            moved = self._ids[last]
            self._ids[row], self._prompts[row] = moved, self._prompts[last]
            self._row[moved] = row
        self._ids.pop()
        self._prompts.pop()
        self._n -= 1

    def discard(self, id_: str) -> None:
        """Drop an entry noticed to have expired (no version bump: other replicas notice on their own)."""
        self._remove(id_)

    # ── sync with Redis ──────────────────────────────────────────────────────
    async def sync(self, store: RedisStore) -> None:
        async with self._lock:
            current, ops = await store.changes_since(self.namespace, self.version)
            if ops == []:
                return
            if ops is None:
                await self._reload(store)
                self.version = current
                return
            for op in ops:
                kind, _, id_ = op.partition(":")
                if kind == "d":
                    self._remove(id_)
                elif kind == "a":
                    row = (await store.load_vectors(self.namespace, [id_]))[0]
                    if row is not None:
                        self._add(*row)
            self.version = current

    async def _reload(self, store: RedisStore) -> None:
        self._dim = 0
        self._n = 0
        self._ids, self._prompts, self._row = [], [], {}
        ids = await store.all_ids(self.namespace)
        dead: list[str] = []
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            for id_, row in zip(chunk, await store.load_vectors(self.namespace, chunk), strict=True):
                if row is None:
                    dead.append(id_)
                else:
                    self._add(*row)
        await store.prune(self.namespace, dead)

    # ── search ───────────────────────────────────────────────────────────────
    def search(
        self, query: Vector, scope: str, k: int = 5, *, include_out_of_scope: bool = False
    ) -> list[Candidate]:
        """Top-k by cosine similarity. By default only entries inside ``scope`` are returned."""
        if self._n == 0 or query.shape[0] != self._dim:
            return []
        sims = self._m[: self._n] @ query
        in_scope = self._scopes[: self._n] == _scope_int(scope)
        order_pool = np.arange(self._n) if include_out_of_scope else np.flatnonzero(in_scope)
        if order_pool.size == 0:
            return []
        top = order_pool[np.argsort(-sims[order_pool])[:k]]
        return [Candidate(self._ids[i], float(sims[i]), self._prompts[i], bool(in_scope[i])) for i in top]
