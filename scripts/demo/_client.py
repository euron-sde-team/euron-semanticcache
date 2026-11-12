"""Tiny stdlib HTTP client shared by the demo scripts (no third-party dependencies)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    f = ROOT / "deploy/compose/.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v
    return env


class Reply:
    def __init__(self, status: int, body: Any, headers: dict[str, str], elapsed_ms: float) -> None:
        self.status, self.body, self.headers, self.ms = status, body, headers, elapsed_ms

    @property
    def result(self) -> str:
        return self.headers.get("x-semanticcache", "")

    @property
    def text(self) -> str:
        try:
            return str(self.body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            return ""


class Api:
    def __init__(self, base: str | None = None) -> None:
        env = load_env()
        self.base = base or os.environ.get("SC_API_URL", f"http://localhost:{env.get('SC_API_PORT', '8180')}")
        self.key = os.environ.get("SC_API_KEY", env.get("SC_BOOTSTRAP_API_KEY", ""))
        self.mock = os.environ.get("SC_MOCK_URL", f"http://localhost:{env.get('SC_MOCK_PORT', '8190')}")
        self.replica = os.environ.get(
            "SC_API_REPLICA_URL", f"http://localhost:{env.get('SC_API_REPLICA_PORT', '8181')}"
        )

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        key: str | None = None,
        headers: dict[str, str] | None = None,
        base: str | None = None,
        raw: bool = False,
    ) -> Reply:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request((base or self.base) + path, data=data, method=method)
        req.add_header("X-API-Key", self.key if key is None else key)
        if data:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                payload = r.read()
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                ms = (time.perf_counter() - start) * 1000
                if raw or "json" not in hdrs.get("content-type", ""):
                    return Reply(r.status, payload.decode(), hdrs, ms)
                return Reply(r.status, json.loads(payload), hdrs, ms)
        except urllib.error.HTTPError as e:
            payload = e.read()
            hdrs = {k.lower(): v for k, v in e.headers.items()}
            ms = (time.perf_counter() - start) * 1000
            try:
                return Reply(e.code, json.loads(payload), hdrs, ms)
            except ValueError:
                return Reply(e.code, payload.decode(), hdrs, ms)

    def ask(
        self,
        text: str,
        *,
        ns: str | None = None,
        model: str = "gpt-4o-mini",
        system: str | None = None,
        key: str | None = None,
        cache: str | None = None,
        base: str | None = None,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Reply:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": text}
        ]
        h = dict(headers or {})
        if ns:
            h["X-SC-Namespace"] = ns
        if cache:
            h["X-SC-Cache"] = cache
        return self.call(
            "POST",
            "/v1/chat/completions",
            {"model": model, "messages": messages, **(extra or {})},
            key=key,
            headers=h,
            base=base,
        )

    def provider_calls(self) -> int:
        return int(self.call("GET", "/stats", key="", base=self.mock).body["calls"])

    def provider_reset(self) -> None:
        self.call("POST", "/reset", {}, key="", base=self.mock)

    def wait_ready(self, base: str | None = None, timeout: float = 90) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.call("GET", "/readyz", key="", base=base).status == 200:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False
