"""The OpenAI-compatible caching proxy: point any OpenAI SDK's ``base_url`` here."""

from __future__ import annotations

import copy
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from semanticcache_core import CacheEntry, ChatRequest, Lookup, Usage, estimate_tokens

from ..auth import Principal, require, resolve_namespace
from ..deps import Cache, Settings, Upstream
from ..upstream import UpstreamClient, UpstreamError

log = logging.getLogger("semanticcache.proxy")
router = APIRouter(tags=["proxy"])

CACHE_MODES = {"", "bypass", "refresh", "no-store", "only-if-cached"}


def usage_of(response: dict[str, Any], req: ChatRequest) -> Usage:
    u = response.get("usage") or {}
    if "prompt_tokens" in u and "completion_tokens" in u:
        return Usage(prompt_tokens=int(u["prompt_tokens"]), completion_tokens=int(u["completion_tokens"]))
    out = completion_text(response)
    return Usage(
        prompt_tokens=estimate_tokens(" ".join(m.text() for m in req.messages)),
        completion_tokens=estimate_tokens(out),
    )


def completion_text(response: dict[str, Any]) -> str:
    try:
        return str(response["choices"][0]["message"].get("content") or "")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def cacheable(response: dict[str, Any]) -> bool:
    """Only complete, plain-text answers are worth reusing: not truncated, not a tool call, not empty."""
    try:
        choice = response["choices"][0]
        msg = choice["message"]
    except (KeyError, IndexError, TypeError):
        return False
    return (
        choice.get("finish_reason") in ("stop", None)
        and not msg.get("tool_calls")
        and not msg.get("function_call")
        and bool(str(msg.get("content") or "").strip())
    )


def sse_stream(body: dict[str, Any], headers_note: str) -> AsyncIterator[bytes]:
    """Replays a finished completion as an OpenAI-style event stream."""
    cid, created, model = (
        body.get("id", "chatcmpl-sc"),
        body.get("created", int(time.time())),
        body.get("model", ""),
    )
    text = completion_text(body)
    words = text.split(" ")
    pieces = [
        " ".join(words[i : i + 3]) + (" " if i + 3 < len(words) else "") for i in range(0, len(words), 3)
    ]

    def chunk(delta: dict[str, Any], finish: str | None = None, extra: dict[str, Any] | None = None) -> bytes:
        payload = {
            "id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **(extra or {}),
        }  # fmt: skip
        return f"data: {json.dumps(payload)}\n\n".encode()

    async def gen() -> AsyncIterator[bytes]:
        yield chunk({"role": "assistant", "content": ""})
        for p in pieces:
            yield chunk({"content": p})
        yield chunk({}, "stop", {"usage": body.get("usage"), "semantic_cache": body.get("semantic_cache")})
        yield b"data: [DONE]\n\n"

    return gen()


def respond(
    body: dict[str, Any], stream: bool, headers: dict[str, str], status_code: int = 200
) -> JSONResponse | StreamingResponse:
    if stream:
        return StreamingResponse(
            sse_stream(body, headers.get("X-SemanticCache", "")), media_type="text/event-stream",
            headers={**headers, "Cache-Control": "no-cache"},
        )  # fmt: skip
    return JSONResponse(body, status_code=status_code, headers=headers)


def hit_body(entry: CacheEntry, lk: Lookup) -> tuple[dict[str, Any], dict[str, str]]:
    body = copy.deepcopy(entry.response)
    body["id"] = f"chatcmpl-sc-{entry.id}"
    body["created"] = int(time.time())
    info: dict[str, Any] = {
        "hit": True, "type": lk.match.value if lk.match else None, "similarity": round(lk.similarity, 4),
        "entry_id": entry.id, "saved_tokens": entry.usage.total,
        "saved_usd": round(entry.cost_micro_usd / 1e6, 6), "saved_ms": entry.latency_ms,
    }  # fmt: skip
    body["semantic_cache"] = info
    headers = {
        "X-SemanticCache": "HIT", "X-SemanticCache-Type": info["type"] or "", "X-SemanticCache-Similarity": str(info["similarity"]),
        "X-SemanticCache-Id": entry.id, "X-SemanticCache-Saved-Usd": f"{entry.cost_micro_usd / 1e6:.6f}",
    }  # fmt: skip
    return body, headers


@router.post(
    "/v1/chat/completions",
    response_model=None,
    summary="OpenAI-compatible chat completion, served from cache when possible",
)
async def chat_completions(
    request: Request,
    cache: Cache,
    upstream: Upstream,
    settings: Settings,
    principal: Annotated[Principal, Depends(require("proxy:use"))],
    x_sc_namespace: Annotated[str | None, Header()] = None,
    x_sc_cache: Annotated[
        str | None, Header(description="bypass | refresh | no-store | only-if-cached")
    ] = None,
    x_sc_ttl: Annotated[int | None, Header(description="TTL in seconds for this entry")] = None,
    x_sc_tags: Annotated[str | None, Header(description="Comma-separated tags for invalidation")] = None,
    x_upstream_api_key: Annotated[str | None, Header()] = None,
) -> JSONResponse | StreamingResponse:
    """Drop-in for `POST /v1/chat/completions`. Set the SDK `base_url` to this API and use a SemanticCache key.

    A hit never calls the provider. A miss is forwarded, and complete text answers are cached. Per-request control
    through headers: `X-SC-Namespace`, `X-SC-Cache` (`bypass`, `refresh`, `no-store`, `only-if-cached`), `X-SC-TTL`
    and `X-SC-Tags`. Streaming is supported: cached answers are replayed as an event stream.
    """
    ns = resolve_namespace(principal, x_sc_namespace, settings.default_namespace)
    mode = (x_sc_cache or "").strip().lower()
    if mode not in CACHE_MODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"X-SC-Cache must be one of {sorted(CACHE_MODES - {''})}"
        )
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("body must be a JSON object")
        req = ChatRequest.model_validate(body)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid chat request: {str(exc)[:200]}"
        ) from exc

    stream = bool(body.get("stream"))
    fwd = {k: v for k, v in body.items() if k not in ("stream", "stream_options")}
    metrics = request.app.state.metrics

    def done(result: str) -> None:
        metrics.proxy.labels(namespace=ns, result=result).inc()

    cfg = await cache.config(ns)
    if mode == "bypass" or not cfg.enabled or (body.get("n") or 1) > 1:
        await cache.store.incr(ns, {"bypass": 1})
        res = await forward(upstream, fwd, x_upstream_api_key)
        res["semantic_cache"] = {"hit": False, "stored": False, "bypass": True}
        done("bypass")
        return respond(res, stream, {"X-SemanticCache": "BYPASS"})

    prep = await cache.prepare(req, embed=cfg.semantic)
    lk: Lookup | None = None
    if mode != "refresh":
        lk = await cache.lookup(ns, req, prep, record=False)
        if lk.hit and lk.entry:
            await cache.record_lookup(ns, lk)
            out, headers = hit_body(lk.entry, lk)
            done(f"hit_{lk.match.value}" if lk.match else "hit")
            return respond(out, stream, headers)
    if mode == "only-if-cached":
        await cache.record_lookup(ns, lk or Lookup(hit=False))
        done("miss")
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "not in cache (X-SC-Cache: only-if-cached)")

    tags = [t.strip() for t in (x_sc_tags or "").split(",") if t.strip()]

    async def fetch() -> tuple[dict[str, Any], CacheEntry | None]:
        result = await forward(upstream, fwd, x_upstream_api_key, with_latency=True)
        response, latency = result["body"], result["latency_ms"]
        entry = None
        if mode != "no-store" and cacheable(response):
            entry = await cache.put(
                ns, req, response, usage_of(response, req), latency, prep, ttl_s=x_sc_ttl, tags=tags
            )
        return response, entry

    (response, entry), shared = await cache.flights.run(f"{ns}:{prep.exact_hash}", fetch)
    response = copy.deepcopy(response)
    if shared and entry:
        await cache.record_coalesced(ns, entry)
    else:
        await cache.record_lookup(ns, lk or Lookup(hit=False))
    info: dict[str, Any] = {"hit": False, "stored": entry is not None, "coalesced": shared}
    if entry:
        info["entry_id"] = entry.id
    if lk and lk.rejected_reason:
        info.update(rejected_reason=lk.rejected_reason, rejected_similarity=lk.rejected_similarity)
    response["semantic_cache"] = info
    done("coalesced" if shared else "miss")
    return respond(response, stream, {"X-SemanticCache": "COALESCED" if shared else "MISS"})


async def forward(
    upstream: UpstreamClient, body: dict[str, Any], api_key: str | None, *, with_latency: bool = False
) -> dict[str, Any]:
    try:
        result = await upstream.chat(body, api_key)
    except UpstreamError as exc:
        if exc.status == 502:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        log.warning("upstream error %s", exc.status)
        raise HTTPException(exc.status, _upstream_message(exc)) from exc
    return {"body": result.body, "latency_ms": result.latency_ms} if with_latency else result.body


def _upstream_message(exc: UpstreamError) -> str:
    body = exc.body
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return f"upstream: {err['message']}"
    return f"upstream returned {exc.status}"
