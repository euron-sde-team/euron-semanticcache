# Configuration reference

Everything is an environment variable with the `SC_` prefix (a `.env` in the working directory is also read).

## API

| Variable | Default | Meaning |
| --- | --- | --- |
| `SC_REDIS_URL` | `redis://localhost:6379/0` | Use `rediss://` with a password for ElastiCache |
| `SC_PREFIX` | `sc` | Key prefix; lets several deployments share one Redis |
| `SC_HOST`, `SC_PORT` | `0.0.0.0`, `8180` | |
| `SC_API_KEY_PEPPER` | dev placeholder | HMAC key for API keys. **Set a long random value** |
| `SC_BOOTSTRAP_API_KEY` | unset | Installed as an all-scopes key at startup (`sc_<prefix>_<secret>`) |
| `SC_CORS_ORIGINS` | `http://localhost:3100` | Comma-separated list or a JSON array |
| `SC_DEFAULT_NAMESPACE` | `default` | Used when a request names none |
| `SC_UPSTREAM_BASE_URL` | `http://localhost:8190/v1` | Any OpenAI-compatible provider; misses are forwarded here |
| `SC_UPSTREAM_API_KEY` | unset | Provider key (or send `X-Upstream-Api-Key` per request) |
| `SC_UPSTREAM_TIMEOUT_S` | `60` | |
| `SC_EMBEDDER` | `hashing` | `hashing` or `openai` |
| `SC_EMBEDDING_DIM` | `512` | Dimensions of the hashing embedder |
| `SC_EMBEDDING_BASE_URL`, `SC_EMBEDDING_MODEL`, `SC_EMBEDDING_API_KEY` | unset, `text-embedding-3-small`, unset | For `SC_EMBEDDER=openai` |
| `SC_PRICING_FILE` | unset | JSON `{"model-prefix": [input_usd_per_1m, output_usd_per_1m]}` merged over the built-in prices |
| `SC_SECRETS_ARN` | unset | Secrets Manager secret with `api_key_pepper`, `bootstrap_api_key`, `upstream_api_key`, `embedding_api_key`; overrides the above |
| `SC_EXPORT_BUCKET` | unset | Enables snapshot export and import |
| `SC_AWS_ENDPOINT_URL` | unset | Set to Floci for local runs |
| `SC_LOG_LEVEL` | `INFO` | |

## Console (build time)

| Variable | Meaning |
| --- | --- |
| `NEXT_PUBLIC_SC_API_URL` | API base URL as seen from the browser |
| `NEXT_PUBLIC_SC_DEFAULT_API_KEY` | **Local demos only.** Compiled into the bundle |

## Namespace settings (per tenant, `PUT /v1/namespaces/{name}`)

| Field | Default | Range | Meaning |
| --- | --- | --- | --- |
| `threshold` | `0.85` | 0.5 to 1.0 | Minimum similarity for a semantic hit |
| `ttl_seconds` | `86400` | 1 to 1 year | Lifetime of new entries |
| `max_entries` | `5000` | 10 to 200,000 | LRU-evicted beyond this |
| `enabled` | `true` | | Off bypasses the cache entirely |
| `semantic` | `true` | | Off allows exact matches only |
| `guards` | `true` | | Numbers, identifiers and negation must agree |

Changes take effect within about 2 seconds on every replica.

## Built-in prices (USD per 1M tokens, input and output)

`gpt-4o-mini` 0.15 / 0.60 · `gpt-4o` 2.50 / 10.00 · `gpt-4.1` 2.00 / 8.00 · `claude-sonnet` 3.00 / 15.00 ·
`claude-haiku` 0.80 / 4.00 · `claude-opus` 15.00 / 75.00 · `gemini-1.5-flash` 0.075 / 0.30. Longest matching prefix
wins; unknown models use 1.00 / 3.00. These are approximate list prices: override them with `SC_PRICING_FILE`.
