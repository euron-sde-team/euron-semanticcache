# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-12

### Added

- **Core** (`packages/core`): scoped exact and semantic matching, deterministic guards (numbers, identifiers, negation),
  a dependency-free hashing embedder and an OpenAI-compatible one, an in-memory vector index synced across replicas by a
  Redis change log, atomic Lua mutations with LRU eviction, and cost accounting to the micro-dollar.
- **API** (`apps/api`): an OpenAI-compatible caching proxy with streaming replay, per-request cache modes, stampede
  protection, cache management, namespaces, stats, scoped and namespace-bound API keys, S3 snapshot export and import,
  Prometheus metrics and OpenAPI.
- **Console** (`apps/console`): overview, playground, similarity lab, entries, namespaces and API keys, with dark and
  light themes.
- **Mock provider** (`apps/mock-llm`), **infrastructure** (nine Terraform modules, three environments, Compose with two
  API replicas and a Floci overlay) and **documentation** (HLD, LLD, security, six ADRs, guides).
- **Tests**: 131 Python, 39 console, 59 full-stack, 57 chaos and 25 Chromium browser checks.

### Fixed during development

- A disabled namespace still served exact hits.
- `/v1/cache/*` ignored `X-SC-Namespace`; "two" and "2" matched in the guard but not in the embedder.
- Stale pooled Redis connections after a restart surfaced as 500s.
- A check-then-act race paid the provider twice for one question under concurrency.
- `make up` failed offline because `terraform init` re-queried the registry every time.
- The console showed "No namespaces yet" for a revoked key and scrolled sideways on a long unbroken token.
- The similarity lab labelled unrelated prompts "blocked: numbers differ".
