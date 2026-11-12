from __future__ import annotations

import pytest
from semanticcache_api.testing import Stack

pytestmark = pytest.mark.integration
PW = "How do I reset my password?"


async def test_namespace_settings_change_matching(stack: Stack) -> None:
    await stack.ask(PW)
    strict = {
        "threshold": 1.0,
        "ttl_seconds": 600,
        "max_entries": 100,
        "enabled": True,
        "semantic": True,
        "guards": True,
    }
    r = await stack.api.put("/v1/namespaces/default", json=strict)
    assert r.status_code == 200 and r.json()["config"]["threshold"] == 1.0 and r.json()["entries"] == 1
    stack.app.state.cache._cfg.clear()
    assert (await stack.ask("password reset steps please")).headers["x-semanticcache"] == "MISS"
    await stack.api.put("/v1/namespaces/default", json={**strict, "threshold": 0.5})
    stack.app.state.cache._cfg.clear()
    assert (await stack.ask("password reset steps please")).headers["x-semanticcache"] == "HIT"


async def test_disabling_a_namespace_bypasses_the_cache(stack: Stack) -> None:
    await stack.ask(PW)
    await stack.api.put("/v1/namespaces/default", json={"enabled": False})
    stack.app.state.cache._cfg.clear()
    assert (await stack.ask(PW)).headers["x-semanticcache"] == "BYPASS"


@pytest.mark.parametrize(
    "bad", [{"threshold": 0.1}, {"threshold": 1.5}, {"ttl_seconds": 0}, {"max_entries": 1}]
)
async def test_namespace_settings_are_validated(stack: Stack, bad: dict[str, float]) -> None:
    assert (await stack.api.put("/v1/namespaces/x", json=bad)).status_code == 422
    assert (await stack.api.put("/v1/namespaces/bad name", json={})).status_code == 422


async def test_delete_namespace_removes_entries_config_and_stats(stack: Stack) -> None:
    await stack.ask(PW, headers={"X-SC-Namespace": "doomed"})
    await stack.api.put("/v1/namespaces/doomed", json={"threshold": 0.9})
    assert (await stack.api.delete("/v1/namespaces/doomed")).status_code == 200
    assert "doomed" not in {n["name"] for n in (await stack.api.get("/v1/namespaces")).json()}
    assert (await stack.api.delete("/v1/namespaces/doomed")).status_code == 404
    assert (await stack.ask(PW, headers={"X-SC-Namespace": "doomed"})).headers["x-semanticcache"] == "MISS"


async def test_overview_adds_up(stack: Stack) -> None:
    first = await stack.ask(PW)  # miss: fills the cache, costs money
    for q in (PW, "how can I reset my password", PW):  # 2 exact + 1 semantic hit
        assert (await stack.ask(q)).headers["x-semanticcache"] == "HIT"
    await stack.ask("an unrelated geography question about rivers")  # second miss
    await stack.ask("x", headers={"X-SC-Cache": "bypass"})
    saved_each = first.json()["usage"]
    t = (await stack.api.get("/v1/stats/overview")).json()
    totals = t["totals"]
    assert (
        totals["hits"],
        totals["hits_exact"],
        totals["hits_semantic"],
        totals["misses"],
        totals["bypass"],
    ) == (3, 2, 1, 2, 1)
    assert totals["requests"] == 5 and totals["hit_rate"] == 0.6
    assert totals["tokens_saved"] == 3 * (saved_each["prompt_tokens"] + saved_each["completion_tokens"])
    assert totals["cost_saved_usd"] > 0 and totals["cost_spent_usd"] > totals["cost_saved_usd"] / 3
    assert 0 < totals["savings_pct"] < 1 and totals["entries"] == 2
    assert (
        len(t["series"]) == 30
        and sum(p["hits"] for p in t["series"]) == 3
        and sum(p["misses"] for p in t["series"]) == 2
    )
    ns = t["namespaces"][0]
    assert ns["name"] == "default" and ns["hits"] == 3 and ns["requests"] == 5 and ns["entries"] == 2


async def test_overview_is_zeroed_on_an_empty_cache_and_validates_minutes(stack: Stack) -> None:
    t = (await stack.api.get("/v1/stats/overview", params={"minutes": 10})).json()
    assert (
        t["totals"]["requests"] == 0
        and t["totals"]["hit_rate"] == 0
        and len(t["series"]) == 10
        and t["namespaces"] == []
    )
    assert (await stack.api.get("/v1/stats/overview", params={"minutes": 1})).status_code == 422
