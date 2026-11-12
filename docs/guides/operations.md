# Operations and troubleshooting

## What to watch

| Signal | Where | Act when |
| --- | --- | --- |
| Hit rate | Overview, `semanticcache_lookups_total` | It is low: check the similarity lab, the threshold and that system prompts are stable |
| `semanticcache_cost_saved_usd_total` | `/metrics` | Your ROI, per namespace |
| `rejected_guard` ("Look-alikes blocked") | Overview | Rising means near matches are being refused: expected, but review the prompts |
| `evictions` | Overview | Constantly rising: raise `max_entries` or shorten the working set |
| Redis `DatabaseMemoryUsagePercentage` > 80 | CloudWatch alarm | Lower `max_entries` or scale up; with `noeviction` writes fail at 100% |
| API CPU | CloudWatch alarm | Embedding and search are CPU-bound: add tasks |

## Common problems

**Hit rate is near zero.** The scope differs between calls: a changing system prompt, a timestamp in it, a different
model name, or `n > 1`. Compare two requests in the similarity lab: out-of-scope neighbours are shown as "Different scope".

**A paraphrase misses.** The default embedder is lexical. Check its score in the lab; either lower the threshold or use
`SC_EMBEDDER=openai`.

**A wrong answer was served.** Look at `X-SemanticCache-Similarity` and the entry in the console. Raise the threshold,
keep guards on, invalidate the entry (`DELETE /v1/cache/entries/{id}` or the console), and send
`X-SC-Cache: bypass` for that kind of prompt.

**`502 upstream_unreachable`.** The provider is down or `SC_UPSTREAM_BASE_URL` is wrong. Cached answers keep being served.

**Console says "Cannot reach the API".** Check `NEXT_PUBLIC_SC_API_URL` (baked at build time) and `SC_CORS_ORIGINS`.

**`make up` fails at the terraform step.** `docker logs euron-semanticcache-terraform-1`. After the first run it works
offline from the plugin cache.

**Port already in use.** Set `SC_CONSOLE_PORT`, `SC_API_PORT`, `SC_REDIS_PORT`, `SC_FLOCI_PORT` or `SC_MOCK_PORT`.

## Replicas

Namespace settings take up to 2 seconds to reach every replica. Two replicas that miss the same new question at the
same instant may each call the provider once (single-flight is per process).

## Backups

Redis holds everything. Use ElastiCache snapshots, or AOF locally. **Snapshot to S3** (console or
`POST /v1/cache/export`) writes a portable JSON Lines copy of one namespace, without vectors; restore re-embeds, so it
also works after changing the embedder.
