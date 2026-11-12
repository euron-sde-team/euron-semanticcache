"""Embedders: turn a prompt into a unit vector. Cosine similarity is then a dot product.

``HashingEmbedder`` needs no model download and no network, so the stack runs on a laptop and in CI. It combines
word unigrams, bigrams and character trigrams with signed feature hashing (a stable, well understood technique),
which captures wording overlap well but not deep paraphrase. ``OpenAICompatEmbedder`` calls any
``/embeddings`` endpoint (OpenAI, Azure, vLLM, Ollama, LiteLLM) for true semantic matching.
"""

from __future__ import annotations

import hashlib
import itertools
from typing import Protocol

import httpx
import numpy as np
from numpy.typing import NDArray

from .text import content_tokens, normalize

Vector = NDArray[np.float32]


class Embedder(Protocol):
    name: str
    dim: int

    async def embed(self, texts: list[str]) -> list[Vector]: ...


def _h(feature: str) -> int:
    return int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")


def _stem(tok: str) -> str:
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
            return tok[: -len(suffix)]
    return tok


class HashingEmbedder:
    """Deterministic feature-hashing embedder. Same text, same vector, on every machine."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _features(self, text: str) -> dict[str, float]:
        words = [_stem(t) for t in content_tokens(text)]
        feats: dict[str, float] = {}
        for w in words:
            feats[f"w:{w}"] = feats.get(f"w:{w}", 0.0) + 1.0
        for a, b in itertools.pairwise(words):
            feats[f"b:{a} {b}"] = feats.get(f"b:{a} {b}", 0.0) + 1.0
        joined = f" {' '.join(words)} "
        for i in range(len(joined) - 2):
            g = f"c:{joined[i : i + 3]}"
            feats[g] = feats.get(g, 0.0) + 0.35
        return feats

    def _vector(self, text: str) -> Vector:
        v = np.zeros(self.dim, dtype=np.float32)
        for feat, weight in self._features(text).items():
            h = _h(feat)
            v[h % self.dim] += (1.0 if (h >> 63) & 1 else -1.0) * (
                1.0 + np.log(weight) if weight > 1 else weight
            )
        norm = float(np.linalg.norm(v))
        if norm == 0.0:
            v[0] = 1.0  # empty prompt: a fixed point, never similar to real text
            return v
        return v / norm

    async def embed(self, texts: list[str]) -> list[Vector]:
        return [self._vector(t) for t in texts]


class OpenAICompatEmbedder:
    """Calls ``POST {base_url}/embeddings``. Batches inputs and L2-normalises the result."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        dim: int = 1536,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.dim = dim
        self.name = f"openai-compat:{model}"
        self._client = client or httpx.AsyncClient(timeout=30)

    async def embed(self, texts: list[str]) -> list[Vector]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = await self._client.post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": [normalize(t) or " " for t in texts]},
            headers=headers,
        )
        resp.raise_for_status()
        rows = sorted(resp.json()["data"], key=lambda r: r["index"])
        out: list[Vector] = []
        for row in rows:
            v = np.asarray(row["embedding"], dtype=np.float32)
            n = float(np.linalg.norm(v))
            out.append((v / n if n else v).astype(np.float32))
        if out:
            self.dim = int(out[0].shape[0])
        return out


def build_embedder(kind: str, **kw: object) -> Embedder:
    if kind == "hashing":
        return HashingEmbedder(int(kw.get("dim", 512)))  # type: ignore[call-overload]
    if kind == "openai":
        return OpenAICompatEmbedder(
            base_url=str(kw["base_url"]),
            model=str(kw.get("model", "text-embedding-3-small")),
            api_key=str(kw["api_key"]) if kw.get("api_key") else None,
        )
    raise ValueError(f"unknown embedder {kind!r}; use 'hashing' or 'openai'")
