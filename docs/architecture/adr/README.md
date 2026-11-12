# Architecture decision records

| ADR | Decision |
| --- | --- |
| [0001](0001-scoped-matching.md) | Match only inside a safety scope: model, system prompt, history, output format |
| [0002](0002-deterministic-guards-on-top-of-similarity.md) | Deterministic guards for numbers, identifiers and negation on top of vector similarity |
| [0003](0003-redis-store-with-an-in-memory-vector-index.md) | Redis as the store, an in-memory brute-force index per process, a change log for sync |
| [0004](0004-pluggable-embedders-lexical-by-default.md) | A dependency-free lexical embedder by default, OpenAI-compatible embeddings when you want meaning |
| [0005](0005-namespaces-are-tenants.md) | Namespaces are tenants; keys can be bound to one |
| [0006](0006-floci-for-local-aws.md) | Floci to run the same Terraform locally |
