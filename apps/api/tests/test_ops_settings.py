from __future__ import annotations

import json
from typing import Any

import pytest
from semanticcache_api.settings import ApiSettings, apply_aws_secrets, resolve_region
from semanticcache_api.testing import Stack

pytestmark = pytest.mark.integration


async def test_health_ready_metrics_and_request_id(stack: Stack) -> None:
    anon = {"X-API-Key": ""}
    assert (await stack.api.get("/healthz", headers=anon)).json() == {"status": "ok"}
    ready = await stack.api.get("/readyz", headers=anon)
    assert ready.status_code == 200 and ready.json()["status"] == "ready"
    await stack.ask("metrics question")
    await stack.ask("metrics question")
    m = (await stack.api.get("/metrics", headers=anon)).text
    assert 'semanticcache_entries{namespace="default"} 1.0' in m
    assert 'semanticcache_lookups_total{namespace="default",result="exact"} 1.0' in m
    assert (
        "semanticcache_cost_saved_usd_total" in m
        and 'semanticcache_proxy_requests_total{namespace="default",result="hit_exact"} 1.0' in m
    )
    assert (await stack.api.get("/healthz", headers={**anon, "X-Request-ID": "abc123"})).headers[
        "x-request-id"
    ] == "abc123"


async def test_openapi_and_docs(stack: Stack) -> None:
    spec = (await stack.api.get("/openapi.json")).json()
    assert spec["info"]["title"] == "Euron SemanticCache API"
    assert {
        "/v1/chat/completions",
        "/v1/cache/entries",
        "/v1/cache/explain",
        "/v1/namespaces",
        "/v1/stats/overview",
    } <= set(spec["paths"])
    assert (await stack.api.get("/docs")).status_code == 200


async def test_cors_allows_the_console_and_exposes_cache_headers(stack: Stack) -> None:
    r = await stack.api.options(
        "/v1/chat/completions",
        headers={
            "Origin": "http://localhost:3100",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,x-sc-namespace,x-sc-cache",
        },
    )
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:3100"
    hit = await stack.ask("cors question", headers={"Origin": "http://localhost:3100"})
    assert "x-semanticcache" in hit.headers["access-control-expose-headers"].lower()
    evil = await stack.api.options(
        "/v1/chat/completions",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in evil.headers


# ── settings ─────────────────────────────────────────────────────────────────────────────────────────────────
class FakeSecrets:
    def __init__(self, secret: dict[str, Any]) -> None:
        self.secret, self.requested = secret, []  # type: ignore[var-annotated]

    def get_secret_value(self, SecretId: str) -> dict[str, str]:
        self.requested.append(SecretId)
        return {"SecretString": json.dumps(self.secret)}


def test_secrets_override_the_environment() -> None:
    fake = FakeSecrets(
        {
            "api_key_pepper": "from-secret-xyz",
            "bootstrap_api_key": "sc_boot0001_abc",
            "upstream_api_key": "sk-up",
        }
    )
    s = apply_aws_secrets(ApiSettings(secrets_arn="arn:x", api_key_pepper="env-pepper-1"), client=fake)
    assert (s.api_key_pepper, s.bootstrap_api_key, s.upstream_api_key) == (
        "from-secret-xyz",
        "sc_boot0001_abc",
        "sk-up",
    )
    kept = apply_aws_secrets(
        ApiSettings(secrets_arn="arn", api_key_pepper="env-pepper-1"), client=FakeSecrets({})
    )
    assert kept.api_key_pepper == "env-pepper-1"
    untouched = ApiSettings(api_key_pepper="env-pepper-1")
    assert apply_aws_secrets(untouched, client=fake) is untouched


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://a.test, http://b.test", ["http://a.test", "http://b.test"]),
        ('["http://c.test"]', ["http://c.test"]),
    ],
)
def test_cors_origins_accept_csv_and_json(raw: str, expected: list[str]) -> None:
    assert ApiSettings(cors_origins=raw).cors_origins == expected


def test_list_settings_parse_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SC_CORS_ORIGINS", "http://a.test,http://b.test")
    assert ApiSettings().cors_origins == ["http://a.test", "http://b.test"]


def test_region_resolution_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """boto3 ignores AWS_REGION on its own, which breaks ECS and Compose."""
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert resolve_region(None) is None
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    assert resolve_region(None) == "eu-west-1"
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    assert resolve_region(None) == "ap-south-1" and resolve_region("us-west-2") == "us-west-2"
