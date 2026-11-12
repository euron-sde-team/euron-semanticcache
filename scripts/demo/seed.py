"""Sends a realistic mix of repeated, paraphrased and look-alike questions through the running stack.

Three tenants with different traffic shapes, so the console has something worth looking at:
  acme-support   a support bot: a few FAQs asked over and over, in many wordings
  docs-assistant a docs helper: broader questions, fewer repeats
  playground     left almost empty for the demo sequence in the console
"""

from __future__ import annotations

import random
import sys
from concurrent.futures import ThreadPoolExecutor

from _client import Api

api = Api()
if not api.wait_ready(timeout=10):
    sys.exit("API not ready. Run `make up` first.")

rng = random.Random(7)

SUPPORT = [
    [
        "How do I reset my password?",
        "how can I reset my password",
        "I forgot my password, how do I reset it",
        "reset password steps",
    ],
    [
        "How do I cancel my subscription?",
        "how to cancel my subscription",
        "I want to cancel my subscription",
        "cancel subscription please",
    ],
    ["What is your refund policy?", "Summarize the refund policy", "refund policy details"],
    ["How long does shipping take?", "what is the shipping time", "shipping time estimate"],
    ["What is the capital of France?", "capital of france"],
    ["What is the capital of Germany?", "capital of germany"],
    ["How much does the plan cost for 5 seats?", "plan cost for 5 seats please"],
    ["How much does the plan cost for 10 seats?", "plan cost for 10 seats please"],
]
DOCS = [
    ["How do I configure rate limiting for the gateway?", "configure gateway rate limiting"],
    ["Explain how retries with exponential backoff work", "how does retry with exponential backoff work"],
    ["What is the difference between a mutex and a semaphore?"],
    ["How do I rotate an API key without downtime?", "rotate api key with zero downtime"],
    ["Write a short summary of the deployment checklist"],
    ["Why does my build fail with error E404 on install?"],
    ["Why does my build fail with error E500 on install?"],
    ["Summarize the quarterly roadmap for region 4 including key metrics"],
    ["Summarize the quarterly roadmap for region 5 including key metrics"],
]


def traffic(pool: list[list[str]], n: int) -> list[str]:
    """Zipf-like: the first FAQs are asked far more often than the last."""
    weights = [1 / (i + 1) for i in range(len(pool))]
    out = []
    for _ in range(n):
        group = rng.choices(pool, weights)[0]
        out.append(rng.choice(group))
    return out


jobs: list[tuple[str, str, str]] = []
for ns, pool, n, model in [
    ("acme-support", SUPPORT, 90, "gpt-4o-mini"),
    ("docs-assistant", DOCS, 45, "gpt-4o"),
]:
    for q in traffic(pool, n):
        jobs.append((ns, q, model))
# Ask each distinct question once first, so the repeats that follow are real cache traffic rather than a stampede.
seen: set[tuple[str, str]] = set()
first, rest = [], []
for j in jobs:
    (rest if (j[0], j[1]) in seen else first).append(j)
    seen.add((j[0], j[1]))

print(f"seeding {len(jobs)} requests ({len(first)} distinct) ...")
with ThreadPoolExecutor(8) as pool_:
    list(pool_.map(lambda j: api.ask(j[1], ns=j[0], model=j[2]), first))
    results = list(pool_.map(lambda j: api.ask(j[1], ns=j[0], model=j[2]), rest))

hits = sum(r.result == "HIT" for r in results)
print(f"done: {hits}/{len(results)} of the repeat traffic served from cache. open http://localhost:3100")
