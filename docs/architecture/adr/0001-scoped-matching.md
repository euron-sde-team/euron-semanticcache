# ADR-0001: Match only inside a safety scope

- **Status:** Accepted

## Context

An LLM answer depends on more than the last question: the model, the system prompt, the earlier turns, the output
format. A cache keyed on the question alone returns a pirate-persona answer to a formal-persona app and "its speed"
about Rust to someone who asked about Python.

## Decision

Derive a *scope* hash from everything except the final user question (model, system prompts, prior turns, trailing
messages, `response_format`, `tools`, `max_tokens`). Exact and semantic lookups both happen only within one scope.
Similarity is computed over the final user question alone.

## Consequences

- No cross-model, cross-persona or cross-conversation leakage, by construction, with a test for each dimension.
- Multi-turn conversations hit only when the earlier turns are identical, which lowers the hit rate for long chats.
  That is the safe side of the trade-off.
- Changing a system prompt cold-starts the cache for that prompt. That is also correct.
