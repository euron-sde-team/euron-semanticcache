"""API keys: ``sc_<prefix>_<secret>``, stored as a peppered HMAC with explicit scopes.

A key may be bound to one namespace (one tenant): it can then only read, write and invalidate inside it.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from semanticcache_core.models import NAMESPACE_PATTERN

ALL_SCOPES = (
    "proxy:use", "cache:read", "cache:write", "stats:read", "namespaces:write", "keys:admin",
)  # fmt: skip
import re  # noqa: E402

_NS_RE = re.compile(NAMESPACE_PATTERN)


class ApiKeyRecord(BaseModel):
    prefix: str
    name: str
    scopes: list[str]
    namespace: str | None = None
    created_at: int
    last_used_at: int | None = None
    revoked: bool = False


class ApiKeyCreated(ApiKeyRecord):
    key: str = Field(description="Shown once. Store it safely.")


class Principal(BaseModel):
    prefix: str
    name: str
    scopes: list[str]
    namespace: str | None = None

    def can(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes


class ApiKeyStore:
    """Hashes keyed by key prefix: metadata (JSON), HMAC digest, and last-used time."""

    def __init__(self, redis: Redis, prefix: str, pepper: str) -> None:
        self._r = redis
        self._meta = f"{prefix}:apikeys"
        self._digests = f"{prefix}:apikeys:digest"
        self._used = f"{prefix}:apikeys:used"
        self._pepper = pepper.encode()

    def _digest(self, key: str) -> str:
        return hmac.new(self._pepper, key.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def prefix_of(key: str) -> str:
        parts = key.split("_", 2)
        if len(parts) == 3 and parts[0] == "sc":
            return parts[1]
        return hashlib.sha256(key.encode()).hexdigest()[:8]

    async def create(
        self, name: str, scopes: list[str], *, namespace: str | None = None, key: str | None = None
    ) -> ApiKeyCreated:
        for s in scopes:
            if s != "*" and s not in ALL_SCOPES:
                raise ValueError(f"unknown scope {s!r}")
        if namespace is not None and not _NS_RE.match(namespace):
            raise ValueError(f"invalid namespace {namespace!r}")
        full = key or f"sc_{secrets.token_hex(4)}_{secrets.token_urlsafe(24)}"
        prefix = self.prefix_of(full)
        rec = ApiKeyRecord(
            prefix=prefix, name=name, scopes=scopes, namespace=namespace, created_at=int(time.time() * 1000)
        )
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.hset(self._meta, prefix, rec.model_dump_json())
            pipe.hset(self._digests, prefix, self._digest(full))
            await pipe.execute()
        return ApiKeyCreated(**rec.model_dump(), key=full)

    async def verify(self, key: str) -> Principal | None:
        prefix = self.prefix_of(key)
        digest = await self._r.hget(self._digests, prefix)
        if not digest or not hmac.compare_digest(_s(digest), self._digest(key)):
            return None
        raw = await self._r.hget(self._meta, prefix)
        if not raw:
            return None
        rec = ApiKeyRecord.model_validate_json(raw)
        if rec.revoked:
            return None
        return Principal(prefix=rec.prefix, name=rec.name, scopes=rec.scopes, namespace=rec.namespace)

    async def touch(self, prefix: str) -> None:
        await self._r.hset(self._used, prefix, int(time.time() * 1000))

    async def list(self) -> list[ApiKeyRecord]:
        rows = await self._r.hgetall(self._meta)
        used = await self._r.hgetall(self._used)
        recs: list[ApiKeyRecord] = []
        for prefix, raw in rows.items():
            rec = ApiKeyRecord.model_validate_json(raw)
            if prefix in used:
                rec.last_used_at = int(used[prefix])
            recs.append(rec)
        return sorted(recs, key=lambda r: r.created_at)

    async def revoke(self, prefix: str) -> bool:
        raw = await self._r.hget(self._meta, prefix)
        if not raw:
            return False
        rec = ApiKeyRecord.model_validate_json(raw)
        rec.revoked = True
        await self._r.hset(self._meta, prefix, rec.model_dump_json())
        return True


def _s(v: bytes | str) -> str:
    return v.decode() if isinstance(v, bytes) else v


def _extract_key(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def authenticate(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Principal:
    key = _extract_key(authorization, x_api_key)
    if not key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing API key (X-API-Key or Bearer)")
    store: ApiKeyStore = request.app.state.keys
    principal = await store.verify(key)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked API key")
    request.state.principal = principal
    await store.touch(principal.prefix)
    return principal


def require(scope: str):  # type: ignore[no-untyped-def]
    async def dep(principal: Annotated[Principal, Depends(authenticate)]) -> Principal:
        if not principal.can(scope):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing scope {scope!r}")
        return principal

    return dep


def resolve_namespace(principal: Principal, requested: str | None, default: str) -> str:
    """A namespace-bound key can only ever use its own namespace; other keys pick one (or the default)."""
    if principal.namespace:
        if requested and requested != principal.namespace:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"this key is bound to namespace {principal.namespace!r}"
            )
        return principal.namespace
    ns = requested or default
    if not _NS_RE.match(ns):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid namespace {ns!r}")
    return ns


async def requested_namespace(
    namespace: Annotated[
        str | None, Query(description="Defaults to the key's namespace, then 'default'")
    ] = None,
    x_sc_namespace: Annotated[
        str | None, Header(description="Same as the `namespace` query parameter")
    ] = None,
) -> str | None:
    """Cache endpoints take the namespace from ``?namespace=`` or from ``X-SC-Namespace``, like the proxy does."""
    return namespace or x_sc_namespace
