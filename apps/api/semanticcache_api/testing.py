"""Helpers shared by the API's test suites and the full-stack scripts (not used at runtime)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI

ROOT_KEY = "sc_root0001_test-root-secret"


@dataclass
class Stack:
    """An in-process API wired to an in-process mock provider."""

    api: httpx.AsyncClient
    mock: httpx.AsyncClient
    app: FastAPI

    async def provider_calls(self) -> int:
        return int((await self.mock.get("/stats")).json()["calls"])

    async def ask(self, text: str, headers: dict[str, str] | None = None, **extra: Any) -> httpx.Response:
        body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": text}], **extra}
        return await self.api.post("/v1/chat/completions", json=body, headers=headers or {})
