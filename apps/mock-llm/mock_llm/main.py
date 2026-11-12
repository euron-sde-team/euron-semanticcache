"""A deterministic stand-in for an LLM provider.

It answers ``POST /v1/chat/completions`` after a configurable delay, reports ``usage``, serves
``POST /v1/embeddings``, and counts every call (``GET /stats``) so tests and demos can prove the cache kept
requests away from the provider. Special prompts exercise failure paths: ``[fail]`` returns HTTP 500,
``[tool]`` returns a tool call, ``[length]`` returns a truncated answer, ``[slow]`` sleeps 3 s.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from semanticcache_core import HashingEmbedder, estimate_tokens
from semanticcache_core.text import content_tokens

FAQ: dict[tuple[str, ...], str] = {
    (
        "reset",
        "password",
    ): "To reset your password, open Settings, choose Security, then select Reset password. "
    "We will email you a link that stays valid for 30 minutes. If it does not arrive, check your spam folder.",
    (
        "cancel",
        "subscription",
    ): "You can cancel your subscription any time from Billing. Your plan stays active "
    "until the end of the current billing period, and you will not be charged again after that.",
    (
        "refund",
        "polic",
    ): "We offer a full refund within 14 days of purchase, no questions asked. After that, refunds "
    "are issued as account credit. Contact support with your order number to start a refund.",
    ("capital", "franc"): "The capital of France is Paris.",
    ("capital", "germany"): "The capital of Germany is Berlin.",
    (
        "shipping",
        "time",
    ): "Standard shipping takes 3 to 5 business days. Express shipping arrives in 1 to 2 business "
    "days. You will receive a tracking number by email as soon as your order leaves the warehouse.",
}


def answer_for(prompt: str) -> str:
    toks = " ".join(content_tokens(prompt))
    for keys, text in FAQ.items():
        if all(k in toks for k in keys):
            return text
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    sentences = [
        f"Here is a concise answer about {' '.join(content_tokens(prompt)[:4]) or 'your question'}.",
        "First, the key point is to start from the requirement and work backwards to the simplest design.",
        "Second, measure before optimising, because the bottleneck is rarely where intuition says it is.",
        "Finally, write down the decision and the trade-offs so the next person can revisit them.",
        f"(reference {digest[:8]})",
    ]
    return " ".join(sentences[: 3 + int(digest[8], 16) % 3])


def create_app(latency_ms: int | None = None) -> FastAPI:
    delay = (latency_ms if latency_ms is not None else int(os.environ.get("MOCK_LATENCY_MS", "700"))) / 1000
    app = FastAPI(title="Mock LLM", version="0.1.0")
    state: dict[str, Any] = {"calls": 0, "by_prompt": {}, "embedding_calls": 0, "started": time.time()}
    embedder = HashingEmbedder(256)

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> dict[str, Any]:
        body = await request.json()
        messages = body.get("messages") or []
        if not messages:
            raise HTTPException(400, "messages required")
        prompt = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "") or ""
        if not isinstance(prompt, str):
            prompt = " ".join(p.get("text", "") for p in prompt if isinstance(p, dict))
        state["calls"] += 1
        state["by_prompt"][prompt] = state["by_prompt"].get(prompt, 0) + 1
        if "[fail]" in prompt or body.get("model") == "mock-error":
            raise HTTPException(500, "the mock provider failed on purpose")
        await asyncio.sleep(3.0 if "[slow]" in prompt else delay)

        message: dict[str, Any] = {"role": "assistant", "content": answer_for(prompt)}
        finish = "stop"
        if "[tool]" in prompt:
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]}  # fmt: skip
            finish = "tool_calls"
        elif "[length]" in prompt:
            message["content"] = message["content"][:40]
            finish = "length"
        text_in = " ".join(str(m.get("content") or "") for m in messages)
        pt, ct = (
            estimate_tokens(text_in),
            estimate_tokens(str(message.get("content") or "")) + (12 if finish == "tool_calls" else 0),
        )
        return {
            "id": f"chatcmpl-mock-{state['calls']}", "object": "chat.completion", "created": int(time.time()),
            "model": body.get("model", "mock"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
        }  # fmt: skip

    @app.post("/v1/embeddings")
    async def embeddings(request: Request) -> dict[str, Any]:
        body = await request.json()
        texts = body.get("input") or []
        texts = [texts] if isinstance(texts, str) else texts
        state["embedding_calls"] += 1
        vecs = await embedder.embed(texts)
        return {
            "object": "list", "model": body.get("model", "mock-embed"),
            "data": [{"object": "embedding", "index": i, "embedding": v.tolist()} for i, v in enumerate(vecs)],
        }  # fmt: skip

    @app.get("/stats")
    async def stats() -> dict[str, Any]:
        return {
            "calls": state["calls"],
            "embedding_calls": state["embedding_calls"],
            "by_prompt": state["by_prompt"],
        }

    @app.post("/reset")
    async def reset() -> dict[str, bool]:
        state.update(calls=0, by_prompt={}, embedding_calls=0)
        return {"ok": True}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def serve() -> None:
    uvicorn.run(
        "mock_llm.main:create_app", factory=True, host="0.0.0.0",  # noqa: S104
        port=int(os.environ.get("MOCK_PORT", "8190")),
    )  # fmt: skip


if __name__ == "__main__":
    serve()
