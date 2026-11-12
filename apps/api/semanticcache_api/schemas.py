"""Request and response bodies specific to the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from semanticcache_core import CacheEntry, ChatMessage, NamespaceConfig, Neighbor, Usage


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class LookupBody(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None


class ExplainBody(LookupBody):
    k: int = Field(default=8, ge=1, le=50)


class ExplainResponse(BaseModel):
    threshold: float
    guards: bool
    neighbors: list[Neighbor]


class PutBody(LookupBody):
    response: dict[str, Any]
    usage: Usage | None = None
    latency_ms: int = Field(default=0, ge=0)
    ttl_seconds: int | None = Field(default=None, ge=1, le=31_536_000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class EntryPage(BaseModel):
    items: list[CacheEntry]
    total: int
    offset: int
    limit: int


class InvalidateBody(BaseModel):
    tag: str = Field(min_length=1, max_length=80)


class Deleted(BaseModel):
    deleted: int


class ActionResult(BaseModel):
    ok: bool = True
    result: str | None = None


class NamespaceSummary(BaseModel):
    name: str
    config: NamespaceConfig
    entries: int
    requests: int
    hits: int
    misses: int
    hit_rate: float
    cost_saved_usd: float
    tokens_saved: int


class SeriesPoint(BaseModel):
    minute: int
    hits: int
    misses: int
    cost_saved_usd: float
    tokens_saved: int


class Totals(BaseModel):
    requests: int
    hits: int
    hits_exact: int
    hits_semantic: int
    coalesced: int
    misses: int
    bypass: int
    hit_rate: float
    tokens_saved: int
    cost_saved_usd: float
    cost_spent_usd: float
    savings_pct: float
    latency_saved_ms: int
    avg_latency_saved_ms: int
    entries: int
    rejected_guard: int
    evictions: int


class Overview(BaseModel):
    totals: Totals
    namespaces: list[NamespaceSummary]
    series: list[SeriesPoint]


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(default_factory=lambda: ["proxy:use"], min_length=1)
    namespace: str | None = Field(default=None, description="Bind the key to one namespace (tenant)")


class ExportBody(BaseModel):
    namespace: str | None = None


class ExportResult(BaseModel):
    bucket: str
    key: str
    entries: int


class ImportBody(BaseModel):
    key: str = Field(min_length=1, max_length=512)
    namespace: str | None = Field(
        default=None, description="Restore into this namespace (default: the export's own)"
    )


class ImportResult(BaseModel):
    imported: int
    skipped_expired: int
    namespace: str
