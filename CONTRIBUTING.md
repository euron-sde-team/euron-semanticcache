# Contributing

Thanks for helping improve Euron SemanticCache. This guide covers the workflow, the bar a change has to
clear, and the conventions the codebase follows.

## Ground rules

- **Open an issue first** for anything larger than a bug fix or a docs tweak.
- **One concern per pull request.** A refactor and a feature are two PRs.
- **Security issues go through private reporting**, never a public issue. See [SECURITY.md](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE).

## Development setup

Requirements: Python 3.12+, Node 22+ with pnpm 10 (`corepack enable`), Docker and GNU make.

```bash
make install    # virtualenv + editable installs + console dependencies
make up         # Redis + Floci + Terraform + mock LLM + API + console
make test       # unit and integration tests
```

## Before you open a pull request

```bash
make lint
make typecheck
make test
make e2e                  # when the cache path or infrastructure changed
make tf-validate          # when you touched infra/terraform
```

## Conventions

- **Python**: 3.12, fully typed, formatted and linted by `ruff`, checked by `mypy --strict`.
- **Safety first**: a cache hit must never cross a scope (namespace, model, system prompt, conversation history).
  Any change to matching needs a test that proves no leakage.
- **API layering**: routers (HTTP only) -> services -> the core library.
- **TypeScript**: strict mode; UI components are small, accessible and themable through CSS variables.
- **Commits**: small and focused, imperative mood, conventional prefix (`feat:`, `fix:`, `docs:`, `test:`,
  `chore:`, `infra:`, `refactor:`).
- **Tests come with the change.** A bug fix starts with a failing test.
- **Docs come with the change.** Update the README, `docs/` and the configuration reference.
