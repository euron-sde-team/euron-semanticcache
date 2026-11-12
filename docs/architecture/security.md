# Security

## Threat model in one paragraph

A semantic cache's worst failure is not downtime but **serving someone else's answer**. The design therefore puts
isolation first: every cached answer lives in one namespace and one scope, and nothing matches across them. Anyone
who can reach the API with a valid key can read and write the namespaces that key allows, so the API key is the trust
boundary, and one namespace per tenant with a namespace-bound key is the intended model.

## Controls

| Area | Control |
| --- | --- |
| Tenant isolation | Namespace-bound keys can use only their namespace across every endpoint (cache, proxy, stats, export, import). Tests fuzz 5 tenants asking identical questions and assert zero cross-tenant answers, and that spoofing another namespace is refused every time |
| Scope isolation | Matching happens only inside a scope: model, system prompt, conversation history, output format. Tested for each dimension |
| Authentication | `X-API-Key` or `Authorization: Bearer` (so OpenAI SDKs work unchanged) |
| Key storage | Only an HMAC-SHA256 digest, keyed with a pepper; constant-time comparison. A test proves no plaintext key reaches Redis |
| Authorization | Six scopes (`proxy:use`, `cache:read`, `cache:write`, `stats:read`, `namespaces:write`, `keys:admin`). A key cannot grant scopes it lacks, cannot grant `*` unless it holds it, cannot revoke itself, and a bound key can only mint keys bound to the same namespace |
| Secrets | Pepper, bootstrap key and provider keys can live in Secrets Manager (`SC_SECRETS_ARN`); the task role may read that one secret. The e2e verifies the API used it by recomputing the stored HMAC with the secret's pepper |
| What is cached | Only complete text answers. Tool calls, truncated answers, errors and empty answers are never stored |
| Input | Pydantic validation; namespace and queue names are pattern-restricted; hostile input (100 KB prompts, null bytes, RTL text, nested JSON) is a tested 2xx or 4xx, never a 5xx |
| Console | All cached text is rendered as text, never HTML (XSS tested with `<img onerror>` and `<script>` payloads) |
| Transport | CORS allow-list from `SC_CORS_ORIGINS`; TLS terminates at the ALB |
| Redis | Private subnets, security group admits only the API, TLS in transit, AUTH token, encryption at rest, `noeviction` so keys and settings are never evicted |
| Containers | Non-root users; ECR scan on push |
| Errors | Unhandled exceptions return a generic 500 with a request id; details go to logs only |

## Operator guidance

- **One namespace and one bound key per tenant.** Do not share a namespace between customers.
- **Do not cache what must not be reused.** Use `X-SC-Cache: bypass` for personalised or time-sensitive prompts, and
  a short `X-SC-TTL` for anything volatile. Prompts and answers are stored verbatim in Redis and in S3 snapshots.
- **Do not put secrets or personal data in cached prompts.** Encrypt snapshots with `kms_key_arn` on the storage module.
- **Tune with evidence.** Use the similarity lab before lowering a threshold; keep guards on.
- Replace the bootstrap key with scoped keys, then rotate or remove it.
- Do not set `NEXT_PUBLIC_SC_DEFAULT_API_KEY` outside local demos: it is compiled into the browser bundle.
- `/metrics` is unauthenticated, as Prometheus scrapers expect; it is not routed by the ALB. Scrape it inside the VPC.

## Reporting

See [SECURITY.md](../../SECURITY.md).
