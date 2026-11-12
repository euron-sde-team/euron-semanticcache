"""The real LLM provider: any OpenAI-compatible ``POST /chat/completions`` endpoint."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx


class UpstreamError(Exception):
    """The provider answered with an error (``status`` and ``body`` pass through) or was unreachable (502)."""

    def __init__(self, status: int, body: dict[str, Any] | str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass(slots=True)
class UpstreamResult:
    body: dict[str, Any]
    latency_ms: int


class UpstreamClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def chat(self, body: dict[str, Any], api_key: str | None = None) -> UpstreamResult:
        headers = {"Content-Type": "application/json"}
        key = api_key or self.api_key
        if key:
            headers["Authorization"] = f"Bearer {key}"
        start = time.perf_counter()
        try:
            resp = await self._client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamError(502, "", f"upstream unreachable: {exc.__class__.__name__}") from exc
        latency = round((time.perf_counter() - start) * 1000)
        try:
            data = resp.json()
        except ValueError:
            data = resp.text[:500]
        if resp.status_code >= 400:
            raise UpstreamError(resp.status_code, data, f"upstream returned {resp.status_code}")
        if not isinstance(data, dict):
            raise UpstreamError(502, "", "upstream returned a non-JSON-object body")
        return UpstreamResult(data, latency)

    async def aclose(self) -> None:
        await self._client.aclose()
