# Integrate your application

SemanticCache is OpenAI-compatible. Create a key (Console, Settings, or `make key`), then change two settings.

## Python

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8180/v1", api_key="sc_...")   # the only change

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "system", "content": "You are a support agent."},
              {"role": "user", "content": "How do I reset my password?"}],
)
print(resp.choices[0].message.content)
print(resp.semantic_cache)        # {"hit": True, "type": "semantic", "similarity": 0.93, "saved_usd": 0.0004, ...}
```

Per-request control with `extra_headers`:

```python
client.chat.completions.create(..., extra_headers={"X-SC-Namespace": "acme", "X-SC-TTL": "3600", "X-SC-Tags": "pricing"})
```

## Node

```js
import OpenAI from "openai";
const client = new OpenAI({ baseURL: "http://localhost:8180/v1", apiKey: "sc_..." });
```

## curl

```bash
curl http://localhost:8180/v1/chat/completions -H "Authorization: Bearer sc_..." -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

## Headers you send

| Header | Values | Effect |
| --- | --- | --- |
| `X-SC-Namespace` | a name | Which tenant's cache. A namespace-bound key may only use its own |
| `X-SC-Cache` | `bypass` | Skip the cache entirely (nothing read, nothing stored) |
| | `refresh` | Skip the read, ask the provider, replace the entry |
| | `no-store` | Serve hits, but never save the answer |
| | `only-if-cached` | Never call the provider: a miss is a `504` |
| `X-SC-TTL` | seconds | Lifetime of the entry this request creates |
| `X-SC-Tags` | `a,b` | Tags for `POST /v1/cache/invalidate` |
| `X-Upstream-Api-Key` | key | Use this provider key for this request instead of the server's |

## Headers you get back

| Header | Meaning |
| --- | --- |
| `X-SemanticCache` | `HIT`, `MISS`, `COALESCED` (shared another request's provider call) or `BYPASS` |
| `X-SemanticCache-Type` | `exact` or `semantic` |
| `X-SemanticCache-Similarity` | cosine similarity of the match |
| `X-SemanticCache-Id` | the entry that answered |
| `X-SemanticCache-Saved-Usd` | what this hit saved |

The JSON body also carries `semantic_cache`, with the same information plus `saved_tokens` and `saved_ms`, and
`rejected_reason` when a near match was refused (for example `numbers differ`).

## Streaming

`stream: true` works. A hit is replayed as an event stream. A miss is fetched whole from the provider, cached, then
replayed as a stream, so the first streamed token on a miss waits for the whole answer.

## What is and is not cached

Cached: complete plain-text answers (`finish_reason: stop`). Never cached: tool calls, answers truncated by
`max_tokens`, errors, empty answers, and requests with `n > 1`. Provider errors pass through with their status.

## Good practice

- One **namespace per tenant**, and a namespace-bound key per tenant.
- `X-SC-Cache: bypass` for personalised, time-sensitive or sensitive prompts.
- Keep the system prompt stable: it is part of the cache scope.
- Check **Similarity lab** before lowering a threshold.
