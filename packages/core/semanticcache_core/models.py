"""Models shared by the cache, the API and the exports."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .text import normalize

NAMESPACE_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$"


class MatchType(StrEnum):
    EXACT = "exact"
    SEMANTIC = "semantic"


class ChatMessage(BaseModel):
    role: str
    content: str | list[Any] | None = None
    name: str | None = None

    def text(self) -> str:
        """Plain text of the message (multimodal parts reduce to their text parts)."""
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        return " ".join(
            str(p.get("text", "")) for p in self.content if isinstance(p, dict) and p.get("type") == "text"
        )


class ChatRequest(BaseModel):
    """The subset of an OpenAI chat-completions request that decides whether two requests may share an answer."""

    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None

    def query_text(self) -> str:
        """What gets embedded: the final user message."""
        for m in reversed(self.messages):
            if m.role == "user":
                return m.text()
        return self.messages[-1].text()

    def _final_user_index(self) -> int:
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == "user":
                return i
        return len(self.messages) - 1

    def scope_key(self) -> str:
        """Everything that must be IDENTICAL for a cached answer to be reusable:
        model, system prompts, the conversation before the final question, output format, tools and
        sampling that changes the answer's shape. A semantic match is only ever searched inside one scope."""
        i = self._final_user_index()
        payload = {
            "model": self.model,
            "history": [(m.role, normalize(m.text())) for m in self.messages[:i]],
            "after": [(m.role, normalize(m.text())) for m in self.messages[i + 1 :]],
            "rf": self.response_format,
            "tools": self.tools,
            "max_tokens": self.max_tokens,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class CacheEntry(BaseModel):
    id: str
    namespace: str
    model: str
    prompt: str
    scope: str
    response: dict[str, Any]
    usage: Usage = Field(default_factory=Usage)
    cost_micro_usd: int = 0
    latency_ms: int = 0
    created_at: int
    expires_at: int | None = None
    hits: int = 0
    last_hit_at: int | None = None
    tags: list[str] = Field(default_factory=list)


class Lookup(BaseModel):
    hit: bool
    match: MatchType | None = None
    similarity: float = 0.0
    entry: CacheEntry | None = None
    # Closest candidate that was REJECTED, and why (used for explainability and tuning).
    rejected_similarity: float | None = None
    rejected_reason: str | None = None
    rejected_prompt: str | None = None


class NamespaceConfig(BaseModel):
    threshold: float = Field(
        default=0.85, ge=0.5, le=1.0, description="Minimum cosine similarity for a semantic hit"
    )
    ttl_seconds: int = Field(default=86_400, ge=1, le=31_536_000)
    max_entries: int = Field(default=5_000, ge=10, le=200_000)
    enabled: bool = True
    semantic: bool = True
    guards: bool = True


class Neighbor(BaseModel):
    id: str
    prompt: str
    similarity: float
    in_scope: bool
    guard: str | None = None
    would_hit: bool
