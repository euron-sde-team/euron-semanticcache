# Quickstart: run everything locally

You need Docker with Compose v2 and GNU make. No AWS account and no LLM key.

```bash
git clone https://github.com/euron-sde-team/euron-semanticcache.git
cd euron-semanticcache
make up      # Floci + Terraform + Redis + mock LLM + 2 API replicas + console
make demo    # three tenants' worth of repeated, paraphrased and look-alike questions
```

Open <http://localhost:3100>. The console signs itself in with the local demo key.

## What `make up` does

1. `make env` writes `deploy/compose/.env` with random, local-only secrets.
2. Starts **Floci** (an AWS emulator) and applies `infra/terraform/envs/local-floci` to it: an S3 exports bucket and a
   Secrets Manager secret holding the API key pepper and bootstrap key.
3. Starts **Redis** (AOF on, `noeviction`) and a **mock LLM provider** that answers after ~700 ms and counts its calls.
4. Starts **two API replicas** (the second on :8181) that share one cache, and the **console**.

The first run builds three images and takes a few minutes. Later runs work offline.

## Ports

| Service | URL |
| --- | --- |
| Console | <http://localhost:3100> |
| API · docs · metrics | <http://localhost:8180> (`/docs`, `/metrics`) · replica on :8181 |
| Mock LLM | <http://localhost:8190> (`/stats` shows how many calls reached it) |
| Floci | <http://localhost:4666> |

Override with `SC_CONSOLE_PORT`, `SC_API_PORT`, `SC_REDIS_PORT`, `SC_FLOCI_PORT`, `SC_MOCK_PORT`.

## Watch it work

```bash
KEY=$(grep SC_BOOTSTRAP_API_KEY deploy/compose/.env | cut -d= -f2)
ask() { curl -s -D- -o /dev/null -X POST localhost:8180/v1/chat/completions -H "X-API-Key: $KEY" \
  -H 'Content-Type: application/json' -d "{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}]}" \
  -w 'time=%{time_total}s\n' | grep -i -E 'x-semanticcache(:|-type|-similarity)|time='; }

ask "How do I reset my password?"      # MISS        time=0.73s   the mock provider answered
ask "How do I reset my password?"      # HIT exact   time=0.01s
ask "how can I reset my password"      # HIT semantic
curl -s localhost:8190/stats           # {"calls":1,...}  three requests, one provider call
```

Then try the **Playground** and the **Similarity lab** in the console.

## Use a real provider

```bash
# deploy/compose/.env
SC_UPSTREAM_BASE_URL=https://api.openai.com/v1
SC_UPSTREAM_API_KEY=sk-...
SC_EMBEDDER=openai          # true paraphrase matching through the provider's /embeddings
```

then `make down && make up`.

## Everyday commands

| Command | Does |
| --- | --- |
| `make up` / `make down` | Start / stop (`down` deletes volumes) |
| `make logs SERVICE=api` | Tail one service |
| `make key NAMESPACE=acme` | Create an all-scopes key, optionally bound to one tenant |
| `make demo` | Seed realistic traffic |
| `make test` · `make test-console` | Python and console tests |
| `make e2e` · `make e2e-chaos` · `make e2e-browser` | Full-stack assertions · failure injection · Chromium QA |
| `make screenshots` | Regenerate the README images |
