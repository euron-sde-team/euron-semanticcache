from __future__ import annotations

import httpx
import pytest
from mock_llm.main import answer_for, create_app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(latency_ms=0)), base_url="http://mock"
    )


def msg(text: str) -> dict[str, object]:
    return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": text}]}


async def test_answers_are_deterministic_and_report_usage(client: httpx.AsyncClient) -> None:
    a = (await client.post("/v1/chat/completions", json=msg("How do I reset my password?"))).json()
    b = (await client.post("/v1/chat/completions", json=msg("How do I reset my password?"))).json()
    assert a["choices"][0]["message"]["content"] == b["choices"][0]["message"]["content"]
    assert "Settings" in a["choices"][0]["message"]["content"]
    u = a["usage"]
    assert (
        u["prompt_tokens"] > 0
        and u["completion_tokens"] > 0
        and u["total_tokens"] == u["prompt_tokens"] + u["completion_tokens"]
    )


def test_paraphrases_get_the_same_faq_answer() -> None:
    assert answer_for("How do I reset my password?") == answer_for("how can I reset my password")
    assert answer_for("What is the capital of France?") != answer_for("What is the capital of Germany?")


async def test_it_counts_calls_per_prompt_and_can_reset(client: httpx.AsyncClient) -> None:
    for _ in range(3):
        await client.post("/v1/chat/completions", json=msg("alpha"))
    await client.post("/v1/chat/completions", json=msg("beta"))
    s = (await client.get("/stats")).json()
    assert s["calls"] == 4 and s["by_prompt"] == {"alpha": 3, "beta": 1}
    await client.post("/reset")
    assert (await client.get("/stats")).json()["calls"] == 0


@pytest.mark.parametrize(
    ("prompt", "finish"), [("[tool] weather", "tool_calls"), ("[length] long", "length"), ("plain", "stop")]
)
async def test_failure_shapes(client: httpx.AsyncClient, prompt: str, finish: str) -> None:
    r = (await client.post("/v1/chat/completions", json=msg(prompt))).json()
    assert r["choices"][0]["finish_reason"] == finish


async def test_fail_marker_returns_500_but_is_still_counted(client: httpx.AsyncClient) -> None:
    assert (await client.post("/v1/chat/completions", json=msg("[fail] please"))).status_code == 500
    assert (await client.get("/stats")).json()["calls"] == 1


async def test_embeddings_endpoint(client: httpx.AsyncClient) -> None:
    r = (await client.post("/v1/embeddings", json={"input": ["a b c", "d e f"]})).json()
    assert [d["index"] for d in r["data"]] == [0, 1] and len(r["data"][0]["embedding"]) == 256
