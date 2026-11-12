"""Application factory."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from semanticcache_core import Pricing, SemanticCache, build_embedder
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .auth import ApiKeyStore
from .logging_config import configure_logging
from .metrics import ApiMetrics
from .routers import api_keys, cache, namespaces, proxy, stats
from .settings import ApiSettings, apply_aws_secrets, get_settings
from .upstream import UpstreamClient

log = logging.getLogger("semanticcache.api")

DESCRIPTION = """
**Euron SemanticCache** is an intelligent response cache for LLM applications. Point an OpenAI SDK at
`/v1/chat/completions` and repeated or similar questions are answered from cache: no tokens, no provider latency.
Authenticate with `X-API-Key: <key>` or `Authorization: Bearer <key>`.
"""

TAGS = [
    {"name": "proxy", "description": "OpenAI-compatible chat completions with caching"},
    {"name": "cache", "description": "Look up, explain, warm, browse, invalidate, export and import"},
    {
        "name": "namespaces",
        "description": "Tenants: isolation, similarity threshold, TTL and size per namespace",
    },
    {"name": "stats", "description": "Savings and hit-rate metrics"},
    {"name": "api-keys", "description": "Scoped, optionally namespace-bound API keys"},
    {"name": "ops", "description": "Health and Prometheus metrics"},
]


def _error(status_code: int, code: str, message: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", None)}},
    )  # fmt: skip


def create_app(
    settings: ApiSettings | None = None, redis: Redis | None = None, upstream: UpstreamClient | None = None
) -> FastAPI:
    settings = apply_aws_secrets(settings or get_settings())
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = redis or Redis.from_url(settings.redis_url, decode_responses=False)
        embedder = build_embedder(
            settings.embedder, dim=settings.embedding_dim, base_url=settings.embedding_base_url,
            model=settings.embedding_model, api_key=settings.embedding_api_key,
        )  # fmt: skip
        pricing = Pricing.from_file(settings.pricing_file) if settings.pricing_file else Pricing()
        app.state.settings = settings
        app.state.redis = client
        app.state.cache = SemanticCache(client, embedder, prefix=settings.prefix, pricing=pricing)
        app.state.keys = ApiKeyStore(client, settings.prefix, settings.api_key_pepper)
        app.state.metrics = ApiMetrics()
        app.state.upstream = upstream or UpstreamClient(
            settings.upstream_base_url, settings.upstream_api_key, settings.upstream_timeout_s
        )
        if settings.bootstrap_api_key:
            await app.state.keys.create("bootstrap", ["*"], key=settings.bootstrap_api_key)
            log.info("bootstrap API key installed")
        log.info("embedder=%s upstream=%s", embedder.name, settings.upstream_base_url)
        yield
        if upstream is None:
            await app.state.upstream.aclose()
        if redis is None:
            await client.aclose()

    app = FastAPI(
        title="Euron SemanticCache API", version=__version__, description=DESCRIPTION, openapi_tags=TAGS,
        lifespan=lifespan, license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    )  # fmt: skip
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization", "Content-Type", "X-API-Key", "X-Request-ID", "X-SC-Namespace", "X-SC-Cache", "X-SC-TTL",
            "X-SC-Tags", "X-Upstream-Api-Key",
        ],
        expose_headers=[
            "X-Request-ID", "X-SemanticCache", "X-SemanticCache-Type", "X-SemanticCache-Similarity",
            "X-SemanticCache-Id", "X-SemanticCache-Saved-Usd",
        ],
    )  # fmt: skip

    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route = getattr(request.scope.get("route"), "path", request.url.path)
        metrics: ApiMetrics | None = getattr(request.app.state, "metrics", None)
        quiet = route in ("/metrics", "/healthz", "/readyz")
        if metrics and not quiet:
            metrics.requests.labels(request.method, route, str(response.status_code)).inc()
            metrics.latency.labels(request.method, route).observe(elapsed)
        response.headers["X-Request-ID"] = request.state.request_id
        if not quiet:
            log.info(
                "%s %s -> %s", request.method, request.url.path, response.status_code,
                extra={"request_id": request.state.request_id, "method": request.method, "path": request.url.path,
                       "status": response.status_code, "duration_ms": round(elapsed * 1000, 1)},
            )  # fmt: skip
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict",
                 422: "invalid", 429: "rate_limited", 502: "upstream_unreachable", 504: "not_cached"}  # fmt: skip
        return _error(exc.status_code, codes.get(exc.status_code, "error"), str(exc.detail), request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return _error(422, "invalid", f"{loc}: {first.get('msg', 'invalid request')}", request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"request_id": getattr(request.state, "request_id", None)})
        return _error(500, "internal", "internal server error", request)

    for module in (proxy, cache, namespaces, stats, api_keys):
        app.include_router(module.router)

    @app.get("/healthz", tags=["ops"], summary="Liveness")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"], summary="Readiness: Redis reachable")
    async def readyz(request: Request) -> dict[str, str]:
        try:
            await request.app.state.redis.ping()
        except Exception as exc:
            raise HTTPException(503, "redis unavailable") from exc
        return {"status": "ready", "version": __version__}

    @app.get("/metrics", tags=["ops"], summary="Prometheus metrics")
    async def metrics_endpoint(request: Request) -> Response:
        body = await request.app.state.metrics.render(request.app.state.cache)
        return Response(body, media_type="text/plain; version=0.0.4")

    return app
