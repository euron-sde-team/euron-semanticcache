# Low-level design

## The safety scope

`ChatRequest.scope_key()` hashes: model; every message *before* the final user turn (role and normalised text,
so system prompts and history); anything after it; `response_format`; `tools`; `max_tokens`. Two requests share
cached answers only if this hash is identical. The final user question itself is **not** part of it: that is what
similarity is computed over.

Consequence: a multi-turn conversation hits only when the prior turns are identical. That is deliberate. "And its
speed?" means different things after "Tell me about Python" and "Tell me about Rust".

## Guards (`text.py`)

A candidate that clears the threshold must also pass, on normalised text:

| Guard | Rule | Example it stops |
| --- | --- | --- |
| numbers | the same set of numbers; `1,000` = `1000`; `two` = `2` | "report for region 4" vs "region 5" |
| identifiers | the same tokens mixing letters and digits (`e404`, `gpt4`, `sku-12a`) | "error E404" vs "error E500" |
| negation | both or neither contain a negation (`not`, `n't`, `never`, `without`) | "do cats like milk" vs "don't cats like milk" |

Spelled-out numbers (zero to twenty) are digits before embedding, so the embedder and the guard agree.

## Embedders

`HashingEmbedder` (default): signed feature hashing of word unigrams and bigrams plus character trigrams, 512
float32 dims, L2-normalised. Deterministic, no download, no network. It measures **wording** overlap: stop-words
are dropped and light stemming applied, so "how can I reset my password" equals "How do I reset my password?"
(similarity 1.0) while "password reset steps please" scores about 0.6.

`OpenAICompatEmbedder`: `POST {base}/embeddings` (OpenAI, Azure, vLLM, Ollama, LiteLLM). Real paraphrase
matching. Entries embedded by a different model are skipped by the index (dimension mismatch) until re-imported.

## Redis layout

Keys under `{prefix}:{namespace}` (default prefix `sc`):

| Key | Type | Contents |
| --- | --- | --- |
| `:e:{id}` | hash | `json` (the entry), `vec` (float32 bytes), `scope`, `pn` (normalised prompt), `xk`, `hits`, `last_hit` |
| `:ids` | zset | id to last access (ms): the LRU order |
| `:x:{hash}` | string | exact key (scope + normalised prompt) to id; same TTL as the entry |
| `:ver` | string | monotonically increasing version |
| `:log` | zset | version to `a:{id}` / `d:{id}` / `f`; the last 1000 changes |
| `:cfg`, `:stats` | string, hash | namespace settings; lifetime counters |
| `m:{ns}:{minute}` | hash | per-minute counters for the traffic chart (TTL 2 h) |
| `:namespaces`, `apikeys*` | set, hashes | namespace registry; API key metadata, HMAC digests, last use |

### Atomic mutations

`put`, `delete`, `flush` and `touch` are Lua scripts (`scripts.py`). `put` writes the entry, replaces any entry
with the same exact key, adds to the LRU set, bumps the version and **evicts the least recently used entries while
over `max_entries`**, all in one step. Entries expire with Redis `EXPIRE`; the index notices lazily.

### Replica sync

Each API process keeps a `NamespaceIndex` (a dense float32 matrix, swap-remove deletes). Before a semantic lookup it
compares its version with Redis:

- equal: nothing to do;
- the log holds every change since: apply the adds and deletes incrementally;
- the log was trimmed, a flush happened, or there is a gap: reload the namespace.

Entries that expired are detected on read (`get` returns nothing), dropped from the local index, and pruned from the
LRU set on the next reload.

## The proxy (`routers/proxy.py`)

```
mode = X-SC-Cache  (bypass | refresh | no-store | only-if-cached)
if bypass / namespace disabled / n > 1:           forward, count bypass
prepare(req)                                      scope, exact hash, embedding
if mode != refresh: lookup()  ->  hit?            answer from cache (JSON or SSE replay)
if only-if-cached:                                504
flight(ns:exact_hash):                            one leader per key per process
    leader: lookup() again   <- double-check      the answer may have been stored a moment ago
            forward to the provider
            store if complete text (not tool call, not truncated, not empty)
followers share the leader's result               counted as `coalesced` savings
```

The double-check closes a check-then-act race: request B can miss, request A can store its answer and finish its
flight, and B would then start a new flight and pay again. Found by the chaos suite as 21 provider calls for 20
questions; after the fix, 0 extra calls in 15 runs of 400 concurrent requests.

## Accounting

Cost is integer micro-dollars, and with prices per million tokens, `tokens x price` is already micro-dollars.
Each entry stores what its own answer cost. Every hit adds that to `cost_saved_micro`, plus tokens and the latency
the provider took, so savings are exact and need no rate assumptions at read time.

`savings_pct = saved / (saved + spent)`: the share of what the same traffic would have cost without a cache.

## Authentication

API keys look like `sc_<prefix>_<secret>`; only an HMAC-SHA256 digest (keyed with `SC_API_KEY_PEPPER`) is stored.
A key has scopes and may be **bound to one namespace**: it then cannot read, write, flush, export or even name any
other namespace. `resolve_namespace` is the single place that enforces this for every endpoint.

## Console

Next.js App Router, client components behind a connection gate, TanStack Query polling every few seconds.
Filters and the selected namespace live in the URL. The playground measures latency in the browser, so the
cache-versus-provider comparison is what the caller actually experienced.
