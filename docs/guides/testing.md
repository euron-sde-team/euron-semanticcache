# Testing

Nothing here needs a cloud account or an LLM key. Claude Code wrote and ran every layer.

| Layer | Command | Needs | Proves |
| --- | --- | --- | --- |
| Core (58) | `pytest packages/core` | Redis | Text guards, embedders, scoped matching, **isolation across namespace, model, system prompt, history and output format**, TTL, LRU eviction, change-log sync between replicas, import, accounting to the micro-dollar |
| API (65) | `pytest apps/api` | Redis | The proxy with the provider-call count as proof, per-request cache modes, streaming replay, single-flight, the check-then-act race, **tenant isolation with namespace-bound keys**, S3 export and import (fake S3), recovery from stale Redis connections, settings |
| Mock provider (8) | `pytest apps/mock-llm` | none | The deterministic provider the other layers rely on |
| Console (39) | `make test-console` | none | Formatters, API client (including header parsing), connection storage, components |
| Terraform | `make tf-validate` | Docker | All three environments validate |
| Full stack (59) | `make e2e` | running stack | Real containers: the provider is called exactly once for three requests, a hit is 10x faster, two replicas share one cache, tenants cannot see each other, S3 round trip on Floci, **the API really read its secrets from Secrets Manager** |
| Chaos (57) | `make e2e-chaos` | running stack | 400 concurrent requests make one provider call per distinct question, a downed provider, SIGKILL, Redis restart, eviction and flush under load, a 5-tenant leak fuzz, hostile input |
| Browser (25) | `make e2e-browser` | running stack | Chromium: connect, playground, similarity lab, entries, namespaces, snapshots, keys, theme, mobile layout, XSS, a real API outage and recovery, a read-only key, a namespace-bound key |

`make test` starts a throwaway Redis on port 6391 (`sc-test-redis`) and uses database 15 (`SC_TEST_REDIS_URL`
overrides it). Every test uses its own random key prefix and cleans up.

```bash
make up && make demo
make e2e && make e2e-chaos && make e2e-browser
```

## Bugs these suites found

| Found by | Bug |
| --- | --- |
| Core tests | A disabled namespace still served exact hits |
| Full-stack e2e | `/v1/cache/*` ignored `X-SC-Namespace` (only `?namespace=` worked) |
| Full-stack e2e | "two" and "2" were equal to the guard but not to the embedder |
| Chaos | Stale pooled Redis connections after a restart became 500s (8 of 15 requests) |
| Chaos | A check-then-act race paid the provider twice for one question (2 of 15 runs) |
| Chaos | `make up` failed offline: `terraform init` re-queried the registry every time |
| Browser QA | A revoked key showed "No namespaces yet" instead of the auth error |
| Browser QA | A long unbroken token in an answer scrolled the page by thousands of pixels |
| Review | The similarity lab labelled unrelated prompts "blocked: numbers differ" |

## Writing tests

- A bug fix starts with a failing test. Each bug above has a regression test.
- Prefer the real Redis over mocks for anything touching a Lua script.
- Prove the cache's effect with the mock provider's call counter, not with response timing alone.
