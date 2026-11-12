"""Direct cache access: look up, explain, warm, browse, invalidate, export and import."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from semanticcache_core import CacheEntry, ChatRequest, Lookup

from ..auth import Principal, requested_namespace, require, resolve_namespace
from ..deps import Cache, Settings
from ..schemas import (
    Deleted,
    EntryPage,
    ExplainBody,
    ExplainResponse,
    ExportBody,
    ExportResult,
    ImportBody,
    ImportResult,
    InvalidateBody,
    LookupBody,
    PutBody,
)
from ..settings import aws_client
from .proxy import usage_of

router = APIRouter(prefix="/v1/cache", tags=["cache"])
Namespace = Annotated[str | None, Depends(requested_namespace)]


def to_request(body: LookupBody) -> ChatRequest:
    return ChatRequest.model_validate(body.model_dump())


@router.post("/lookup", summary="Would this request hit? (never calls the provider, never counted)")
async def lookup(
    body: LookupBody, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:read"))], namespace: Namespace,
) -> Lookup:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    return await cache.lookup(ns, to_request(body), record=False)


@router.post("/explain", summary="Nearest cached prompts, with the verdict and reason for each")
async def explain(
    body: ExplainBody, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:read"))], namespace: Namespace,
) -> ExplainResponse:  # fmt: skip
    """Shows why something did or did not hit: similarity, whether the candidate shares the safety scope
    (model, system prompt, history), and which guard (numbers, identifiers, negation) rejected it."""
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    cfg = await cache.config(ns)
    neighbors = await cache.explain(ns, to_request(body), body.k)
    return ExplainResponse(threshold=cfg.threshold, guards=cfg.guards, neighbors=neighbors)


@router.post("/entries", status_code=status.HTTP_201_CREATED, summary="Warm the cache with a known answer")
async def put_entry(
    body: PutBody, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:write"))], namespace: Namespace,
) -> CacheEntry:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    req = to_request(body)
    usage = body.usage or usage_of(body.response, req)
    return await cache.put(
        ns, req, body.response, usage, body.latency_ms, ttl_s=body.ttl_seconds, tags=body.tags
    )


@router.get("/entries", summary="Browse entries, most recently used first")
async def list_entries(
    cache: Cache, settings: Settings, principal: Annotated[Principal, Depends(require("cache:read"))],
    namespace: Namespace,
    q: Annotated[str | None, Query(description="Substring of the prompt")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> EntryPage:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    items, total = await cache.store.list_entries(ns, offset, limit, q)
    return EntryPage(items=items, total=total, offset=offset, limit=limit)


@router.get("/entries/{entry_id}", summary="One entry")
async def get_entry(
    entry_id: str, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:read"))], namespace: Namespace,
) -> CacheEntry:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    entry = await cache.store.get(ns, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"entry {entry_id} not found in namespace {ns}")
    return entry


@router.delete("/entries/{entry_id}", summary="Invalidate one entry")
async def delete_entry(
    entry_id: str, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:write"))], namespace: Namespace,
) -> Deleted:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    if not await cache.store.delete(ns, entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"entry {entry_id} not found in namespace {ns}")
    return Deleted(deleted=1)


@router.delete("/entries", summary="Flush every entry in a namespace")
async def flush(
    cache: Cache, settings: Settings, principal: Annotated[Principal, Depends(require("cache:write"))],
    namespace: Namespace,
) -> Deleted:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    return Deleted(deleted=await cache.store.flush(ns))


@router.post("/invalidate", summary="Invalidate every entry carrying a tag")
async def invalidate(
    body: InvalidateBody, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:write"))], namespace: Namespace,
) -> Deleted:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    return Deleted(deleted=await cache.invalidate_tag(ns, body.tag))


# ── export / import (S3) ─────────────────────────────────────────────────────────────────────────────────────
def _bucket(settings: Settings) -> str:
    if not settings.export_bucket:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, "export is not configured (set SC_EXPORT_BUCKET)"
        )
    return settings.export_bucket


@router.post("/export", summary="Snapshot a namespace to S3 as JSON Lines (vectors are not exported)")
async def export(
    body: ExportBody, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:read"))],
) -> ExportResult:  # fmt: skip
    ns = resolve_namespace(principal, body.namespace, settings.default_namespace)
    bucket = _bucket(settings)
    entries, _ = await cache.store.list_entries(ns, 0, 1_000_000)
    lines = "\n".join(e.model_dump_json() for e in entries)
    key = f"exports/{ns}/{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.jsonl"
    s3 = aws_client("s3", settings)
    await asyncio.to_thread(
        s3.put_object, Bucket=bucket, Key=key, Body=lines.encode(), ContentType="application/x-ndjson"
    )
    return ExportResult(bucket=bucket, key=key, entries=len(entries))


@router.get("/exports", summary="List snapshots of a namespace")
async def list_exports(
    cache: Cache, settings: Settings, principal: Annotated[Principal, Depends(require("cache:read"))],
    namespace: Namespace,
) -> list[dict[str, Any]]:  # fmt: skip
    ns = resolve_namespace(principal, namespace, settings.default_namespace)
    s3 = aws_client("s3", settings)
    resp = await asyncio.to_thread(s3.list_objects_v2, Bucket=_bucket(settings), Prefix=f"exports/{ns}/")
    return [
        {"key": o["Key"], "size": o["Size"], "modified": o["LastModified"].isoformat()}
        for o in sorted(resp.get("Contents", []), key=lambda o: o["Key"], reverse=True)
    ]


@router.post("/import", summary="Restore a snapshot from S3 (entries are embedded again)")
async def import_(
    body: ImportBody, request: Request, cache: Cache, settings: Settings,
    principal: Annotated[Principal, Depends(require("cache:write"))],
) -> ImportResult:  # fmt: skip
    parts = body.key.split("/")
    if len(parts) < 3 or parts[0] != "exports" or ".." in parts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "key must look like exports/<namespace>/<file>.jsonl"
        )
    ns = resolve_namespace(principal, body.namespace, parts[1])
    if principal.namespace and parts[1] != principal.namespace:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this key can only import its own namespace's exports")
    s3 = aws_client("s3", settings)
    try:
        obj = await asyncio.to_thread(s3.get_object, Bucket=_bucket(settings), Key=body.key)
    except Exception as exc:  # botocore ClientError: NoSuchKey and friends
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"export {body.key} not found") from exc
    raw = await asyncio.to_thread(obj["Body"].read)
    imported = skipped = 0
    for line in raw.decode().splitlines():
        if not line.strip():
            continue
        try:
            entry = CacheEntry.model_validate(json.loads(line))
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"corrupt export line: {str(exc)[:120]}"
            ) from exc
        if await cache.import_entry(ns, entry):
            imported += 1
        else:
            skipped += 1
    return ImportResult(imported=imported, skipped_expired=skipped, namespace=ns)
