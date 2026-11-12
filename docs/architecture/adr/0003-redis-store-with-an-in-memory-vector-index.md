# ADR-0003: Redis store with an in-memory vector index

- **Status:** Accepted

## Context

A response cache needs fast exact lookup, similarity search, TTLs, LRU bounds, persistence and multi-replica
coherence. A vector database is another service to run; Redis Stack's vector search is not in the standard
ElastiCache engine.

## Decision

Store entries and vectors in plain Redis hashes. Each API process keeps a dense float32 matrix per namespace and
searches it exactly with one matrix-vector product. Every mutation is an atomic Lua script that bumps a version and
appends to a capped change log; processes apply the log, or reload when it cannot be applied.

## Consequences

- One stateful dependency, available on ElastiCache. Search is exact (no approximation to tune).
- Memory per process is about `entries x dims x 4` bytes (100k x 512 is roughly 200 MB), which is why `max_entries` is
  per namespace and LRU-enforced. Past that scale, shard by namespace across deployments.
- Scripts touch several keys derived from an id, so Redis Cluster is not supported.
