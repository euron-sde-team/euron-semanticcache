# Tuning the threshold

The threshold is the minimum cosine similarity for a semantic hit. Too high and you miss legitimate paraphrases;
too low and similar-looking questions with different answers get a cached answer.

## How to choose

1. Put real traffic through a namespace (or `make demo`).
2. Open **Similarity lab**, paste questions you expect to match and questions you expect not to.
3. Read the bars: each shows similarity against the threshold marker, whether it shares your scope, and the verdict.
4. Move the threshold on the **Namespaces** page until the paraphrases are above it and the look-alikes below.
5. Watch **Look-alikes blocked** on the overview: it counts near matches the guards refused.

## Defaults and ranges

| Embedder | Good starting threshold | Notes |
| --- | --- | --- |
| `hashing` (default) | 0.85 | Lexical. Same content words give 1.0. A loose paraphrase scores 0.5 to 0.7, so it is a miss by design |
| `openai` (`text-embedding-3-small`) | 0.88 to 0.92 | Real paraphrase matching. Higher thresholds suit factual domains |

`1.00` means exact (or identical-content) matches only. Turn **Semantic matching** off to be strict.

## Guards

Keep them on. They stop numbers, identifiers and negation from being ignored. Turn them off only for a namespace of
prompts where those never change the answer (for example casual chat).

## When not to cache

Personalised answers ("my order"), time-sensitive ones ("today's price"), and anything where a slightly stale
answer is harmful. Send `X-SC-Cache: bypass`, or give the entry a short `X-SC-TTL`.
