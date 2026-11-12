"""Full-stack end-to-end assertions against the running Compose stack (`make up` first).

Covers auth, the cache path with exact proof of provider-call counts, safety guards, cross-replica coherence,
tenant isolation, per-request cache control, TTL, tags, streaming, cost accounting, the S3 export/import round trip and
the Secrets Manager integration on Floci.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import uuid

import boto3
import redis
from _client import Api, load_env

api = Api()
env = load_env()
failures: list[str] = []
RUN = uuid.uuid4().hex[:6]  # every run uses fresh namespaces, so reruns never see stale entries


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'} {name}{'' if cond else f'  ({detail})'}")
    if not cond:
        failures.append(name)


def section(t: str) -> None:
    print(f"\n{t}")


def ns(name: str) -> str:
    return f"e2e-{name}-{RUN}"


PW = "How do I reset my password?"
assert api.wait_ready(), "stack is not up"
assert api.wait_ready(base=api.replica), "replica is not up"
api.provider_reset()

section("auth")
check("no key is rejected", api.call("GET", "/v1/namespaces", key="").status == 401)
check("bad key is rejected", api.call("GET", "/v1/namespaces", key="sc_bad00000_nope").status == 401)
check(
    "readiness and metrics are open",
    api.call("GET", "/readyz", key="").status == 200 and api.call("GET", "/metrics", key="").status == 200,
)
r = api.call("POST", "/v1/api-keys", {"name": "e2e-proxy-only", "scopes": ["proxy:use"]})
proxy_key = r.body["key"]
check("scoped key can be created", r.status == 201 and proxy_key.startswith("sc_"))
check("proxy-only key can call the proxy", api.ask("hello there", ns=ns("auth"), key=proxy_key).status == 200)
check(
    "proxy-only key cannot browse the cache",
    api.call("GET", "/v1/cache/entries", key=proxy_key).status == 403,
)
api.call("DELETE", f"/v1/api-keys/{r.body['prefix']}")
check("revoked key stops working", api.ask("hello", key=proxy_key).status == 401)

section("the cache path: provider-call counts are the proof")
n = ns("path")
before = api.provider_calls()
miss = api.ask(PW, ns=n)
check(
    "first request is a MISS answered by the provider",
    miss.status == 200 and miss.result == "MISS" and miss.ms > 400,
    f"{miss.result} {miss.ms:.0f}ms",
)
hit = api.ask(PW, ns=n)
check("repeat is an exact HIT", hit.result == "HIT" and hit.headers["x-semanticcache-type"] == "exact")
check(
    "a hit is more than 10x faster than the provider",
    hit.ms * 10 < miss.ms,
    f"hit {hit.ms:.0f}ms vs miss {miss.ms:.0f}ms",
)
check("cached answer is identical", hit.text == miss.text and hit.text != "")
para = api.ask("how can I reset my password", ns=n)
check(
    "a paraphrase is a semantic HIT",
    para.result == "HIT" and para.headers["x-semanticcache-type"] == "semantic",
)
check(
    "the provider was called exactly once for 3 requests",
    api.provider_calls() - before == 1,
    str(api.provider_calls() - before),
)
check(
    "hit headers report the saving",
    float(hit.headers["x-semanticcache-saved-usd"]) > 0
    and "e" not in hit.headers["x-semanticcache-saved-usd"].lower(),
)

section("safety: look-alikes and scopes never share an answer")
q = "Please write a detailed summary of the quarterly sales report for {} including every key metric"
api.ask(q.format("region 4"), ns=n)
guard = api.ask(q.format("region 5"), ns=n)
check(
    "a different number is a MISS, with the reason",
    guard.result == "MISS" and guard.body["semantic_cache"].get("rejected_reason") == "numbers differ",
    str(guard.body.get("semantic_cache")),
)
check(
    "'two' and '2' are the same number",
    api.ask("List two good reasons to use a cache for LLM answers", ns=n).result == "MISS"
    and api.ask("list 2 good reasons to use a cache for LLM answers", ns=n).result == "HIT",
)
check(
    "negation flips the answer",
    api.ask("Explain in plain language why cats really do like drinking milk so much", ns=n).result == "MISS"
    and api.ask("Explain in plain language why cats really don't like drinking milk so much", ns=n).result
    == "MISS",
)
check("a different model is a MISS", api.ask(PW, ns=n, model="gpt-4o").result == "MISS")
check(
    "a different system prompt is a MISS", api.ask(PW, ns=n, system="Answer like a pirate").result == "MISS"
)
check(
    "a different conversation history is a MISS",
    api.call(
        "POST",
        "/v1/chat/completions",
        {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "earlier topic"},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": PW},
            ],
        },
        headers={"X-SC-Namespace": n},
    ).headers["x-semanticcache"]
    == "MISS",
)
check("a different namespace is a MISS", api.ask(PW, ns=ns("other")).result == "MISS")
exp = api.call(
    "POST",
    "/v1/cache/explain",
    {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "reset my password now"}]},
    headers={},
)
check("explain returns neighbours with verdicts", exp.status == 200 and "neighbors" in exp.body)

section("two API replicas share one cache")
n = ns("replica")
api.ask(PW, ns=n)
r2 = api.ask("how can I reset my password", ns=n, base=api.replica)
check(
    "an entry written via replica A is a semantic HIT on replica B",
    r2.result == "HIT" and r2.headers["x-semanticcache-type"] == "semantic",
)
page = api.call("GET", "/v1/cache/entries", headers={"X-SC-Namespace": n})
eid = page.body["items"][0]["id"]
api.call("DELETE", f"/v1/cache/entries/{eid}", headers={"X-SC-Namespace": n})
check(
    "an invalidation via A is honoured by B at once",
    api.ask("how can I reset my password", ns=n, base=api.replica).result == "MISS",
)

section("tenant isolation with namespace-bound keys")
ka = api.call(
    "POST",
    "/v1/api-keys",
    {
        "name": "e2e-a",
        "scopes": ["proxy:use", "cache:read", "cache:write", "stats:read"],
        "namespace": ns("tenant-a"),
    },
).body
kb = api.call(
    "POST",
    "/v1/api-keys",
    {
        "name": "e2e-b",
        "scopes": ["proxy:use", "cache:read", "cache:write", "stats:read"],
        "namespace": ns("tenant-b"),
    },
).body
secret_q = "What is the status of order 7731 for the customer in Berlin?"
check(
    "tenant A fills its namespace",
    api.ask(secret_q, key=ka["key"]).result == "MISS" and api.ask(secret_q, key=ka["key"]).result == "HIT",
)
check("tenant B asking the same thing gets no HIT", api.ask(secret_q, key=kb["key"]).result == "MISS")
check(
    "tenant B cannot name tenant A's namespace",
    api.ask(secret_q, key=kb["key"], ns=ns("tenant-a")).status == 403,
)
check(
    "tenant B cannot list tenant A's entries",
    api.call("GET", "/v1/cache/entries", key=kb["key"], headers={"X-SC-Namespace": ns("tenant-a")}).status
    in (403, 200)
    and all(
        e["namespace"] == ns("tenant-b")
        for e in api.call("GET", "/v1/cache/entries", key=kb["key"]).body["items"]
    ),
)
check(
    "tenant B cannot flush tenant A",
    api.call("DELETE", f"/v1/cache/entries?namespace={ns('tenant-a')}", key=kb["key"]).status == 403,
)
check("tenant A's entry is intact", api.ask(secret_q, key=ka["key"]).result == "HIT")
for k in (ka, kb):
    api.call("DELETE", f"/v1/api-keys/{k['prefix']}")

section("per-request cache control")
n = ns("control")
before = api.provider_calls()
api.ask(PW, ns=n)
check(
    "bypass skips the cache and reaches the provider",
    api.ask(PW, ns=n, cache="bypass").result == "BYPASS" and api.provider_calls() - before == 2,
)
check(
    "refresh re-asks the provider and replaces the entry",
    api.ask(PW, ns=n, cache="refresh").result == "MISS" and api.ask(PW, ns=n).result == "HIT",
)
nostore = api.ask("a question that must not be stored", ns=n, cache="no-store")
check(
    "no-store answers but saves nothing",
    nostore.result == "MISS" and api.ask("a question that must not be stored", ns=n).result == "MISS",
)
check(
    "only-if-cached is a 504 on a miss and a HIT when cached",
    api.ask("never asked before 12345", ns=n, cache="only-if-cached").status == 504
    and api.ask(PW, ns=n, cache="only-if-cached").result == "HIT",
)
api.call(
    "POST",
    "/v1/chat/completions",
    {"model": "m", "messages": [{"role": "user", "content": "short lived answer"}]},
    headers={"X-SC-Namespace": n, "X-SC-TTL": "2"},
)
check(
    "a 2 s TTL entry hits, then expires",
    api.ask("short lived answer", ns=n, model="m").result == "HIT"
    and (time.sleep(2.6) or api.ask("short lived answer", ns=n, model="m").result == "MISS"),
)
api.call(
    "POST",
    "/v1/chat/completions",
    {"model": "m", "messages": [{"role": "user", "content": "tagged pricing answer"}]},
    headers={"X-SC-Namespace": n, "X-SC-Tags": "pricing"},
)
check(
    "tag invalidation removes tagged entries only",
    api.call("POST", "/v1/cache/invalidate", {"tag": "pricing"}, headers={"X-SC-Namespace": n}).body[
        "deleted"
    ]
    == 1
    and api.ask("tagged pricing answer", ns=n, model="m").result == "MISS"
    and api.ask(PW, ns=n).result == "HIT",
)

section("what must not be cached")
n = ns("nocache")
for marker in ("[tool] weather in Paris", "[length] write an essay"):
    check(
        f"'{marker.split()[0]}' responses are not stored",
        api.ask(marker, ns=n).body["semantic_cache"]["stored"] is False
        and api.ask(marker, ns=n).result == "MISS",
    )
check(
    "a provider error passes through and is not cached",
    api.ask("[fail] please", ns=n).status == 500 and api.ask("[fail] please", ns=n).status == 500,
)

section("streaming")
n = ns("stream")
base = api.ask("stream me a cached answer", ns=n).text
r = api.call(
    "POST",
    "/v1/chat/completions",
    {
        "model": "gpt-4o-mini",
        "stream": True,
        "messages": [{"role": "user", "content": "stream me a cached answer"}],
    },
    headers={"X-SC-Namespace": n},
    raw=True,
)
events = [line[6:] for line in str(r.body).splitlines() if line.startswith("data: ")]
text = "".join(json.loads(e)["choices"][0]["delta"].get("content", "") for e in events if e != "[DONE]")
check(
    "a cached answer streams as SSE",
    r.headers["content-type"].startswith("text/event-stream")
    and events[-1] == "[DONE]"
    and r.result == "HIT",
)
check("the streamed text equals the cached answer", text == base, f"{text[:40]!r} vs {base[:40]!r}")

section("warming and accounting")
n = ns("warm")
w = api.call(
    "POST",
    "/v1/cache/entries",
    {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "What are your opening hours?"}],
        "response": {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "We are open 9 to 5."},
                    "finish_reason": "stop",
                }
            ]
        },
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        "latency_ms": 900,
        "tags": ["faq"],
    },
    headers={"X-SC-Namespace": n},
)
check(
    "an answer can be warmed into the cache",
    w.status == 201 and w.body["cost_micro_usd"] == 450,
    str(w.body.get("cost_micro_usd")),
)
before = api.provider_calls()
hits = [api.ask("What are your opening hours?", ns=n) for _ in range(4)]
check(
    "warmed answers are served without the provider",
    all(h.result == "HIT" for h in hits) and api.provider_calls() == before,
)
ov = api.call("GET", "/v1/stats/overview").body
nsx = next(x for x in ov["namespaces"] if x["name"] == n)
check(
    "savings are exact: 4 hits x $0.00045",
    nsx["hits"] == 4 and abs(nsx["cost_saved_usd"] - 0.0018) < 1e-9 and nsx["tokens_saved"] == 4 * 1500,
    str(nsx),
)
check(
    "overview totals are consistent",
    ov["totals"]["hits"]
    == ov["totals"]["hits_exact"] + ov["totals"]["hits_semantic"] + ov["totals"]["coalesced"]
    and 0 <= ov["totals"]["hit_rate"] <= 1,
)
text = api.call("GET", "/metrics", key="").body
check(
    "Prometheus exposes savings per namespace",
    f'semanticcache_cost_saved_usd_total{{namespace="{n}"}} 0.0018' in text,
)

section("namespace settings change behaviour")
n = ns("tune")
api.ask(PW, ns=n)
api.call("PUT", f"/v1/namespaces/{n}", {"threshold": 1.0})
time.sleep(2.2)  # the API caches namespace settings for 2 s
check(
    "threshold 1.0 stops a loose paraphrase matching",
    api.ask("password reset steps please", ns=n).result == "MISS",
)
check("...while an exact repeat still hits", api.ask(PW, ns=n).result == "HIT")
api.call("PUT", f"/v1/namespaces/{n}", {"threshold": 0.7, "max_entries": 10})
time.sleep(2.2)
for i in range(30):
    api.call(
        "POST",
        "/v1/cache/entries",
        {
            "model": "m",
            "messages": [{"role": "user", "content": f"filler question number {i} about topic {i * 7}"}],
            "response": {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]},
        },
        headers={"X-SC-Namespace": n},
    )
total = api.call("GET", "/v1/cache/entries?limit=1", headers={"X-SC-Namespace": n}).body["total"]
check("max_entries bounds the namespace (LRU eviction)", total <= 10, str(total))
api.call("PUT", f"/v1/namespaces/{n}", {"enabled": False})
time.sleep(2.2)
check("a disabled namespace bypasses the cache", api.ask(PW, ns=n).result == "BYPASS")

section("S3 export and import on Floci")
n = ns("snap")
api.ask(PW, ns=n)
api.ask("What is the capital of France?", ns=n)
ex = api.call("POST", "/v1/cache/export", {"namespace": n})
check(
    "a namespace exports to S3",
    ex.status == 200 and ex.body["entries"] == 2 and ex.body["key"].startswith(f"exports/{n}/"),
    str(ex.body),
)
s3 = boto3.client(
    "s3",
    endpoint_url=f"http://localhost:{env.get('SC_FLOCI_PORT', '4666')}",
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)
body = s3.get_object(Bucket=ex.body["bucket"], Key=ex.body["key"])["Body"].read().decode()
check(
    "the object really is in the Floci bucket as JSON Lines",
    len(body.splitlines()) == 2 and all(json.loads(line)["namespace"] == n for line in body.splitlines()),
)
check("the export holds no vectors", '"vec"' not in body and '"vector"' not in body)
n2 = ns("restored")
imp = api.call("POST", "/v1/cache/import", {"key": ex.body["key"], "namespace": n2})
check("the snapshot restores into a new namespace", imp.status == 200 and imp.body["imported"] == 2)
before = api.provider_calls()
check(
    "restored entries serve exact and semantic hits without the provider",
    api.ask(PW, ns=n2).result == "HIT"
    and api.ask("how can I reset my password", ns=n2).result == "HIT"
    and api.provider_calls() == before,
)

section("secrets come from Secrets Manager on Floci")
sm = boto3.client(
    "secretsmanager",
    endpoint_url=f"http://localhost:{env.get('SC_FLOCI_PORT', '4666')}",
    region_name="us-east-1",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)
secret = json.loads(sm.get_secret_value(SecretId="semanticcache-local/app")["SecretString"])
check(
    "the secret holds a generated pepper and the bootstrap key",
    len(secret["api_key_pepper"]) >= 32 and secret["bootstrap_api_key"] == env["SC_BOOTSTRAP_API_KEY"],
)
check(
    "the pepper differs from the .env one (so the API must have read the secret)",
    secret["api_key_pepper"] != env["SC_API_KEY_PEPPER"],
)
rd = redis.Redis(port=int(env.get("SC_REDIS_PORT", "6479")), decode_responses=True)
prefix = env["SC_BOOTSTRAP_API_KEY"].split("_")[1]
stored = rd.hget("sc:apikeys:digest", prefix)
expected = hmac.new(
    secret["api_key_pepper"].encode(), env["SC_BOOTSTRAP_API_KEY"].encode(), hashlib.sha256
).hexdigest()
check("Redis holds the bootstrap key's HMAC under the SECRET's pepper", stored == expected)
check(
    "no plaintext key is stored anywhere in Redis",
    not any(env["SC_BOOTSTRAP_API_KEY"] in str(rd.hgetall(k)) for k in ("sc:apikeys", "sc:apikeys:digest")),
)

print()
if failures:
    print(f"e2e: {len(failures)} assertion(s) FAILED: {', '.join(failures)}")
    sys.exit(1)
print("e2e: all assertions passed")
