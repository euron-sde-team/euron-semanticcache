## What and why

<!-- One paragraph: the problem, and how this change solves it. Link the issue. -->

## How it was verified

- [ ] `make lint && make typecheck && make test`
- [ ] `make test-integration` (if cache or API code changed)
- [ ] `make e2e` (if the cache path or infrastructure changed)
- [ ] `make tf-validate` (if Terraform changed)

## Checklist

- [ ] Docs updated (README, `docs/`, configuration reference) for any behaviour or config change
- [ ] Cache hits never cross a safety scope (model, system prompt, history)
- [ ] No secrets, account IDs or real hostnames
- [ ] Security-relevant change? Described the threat and mitigation above
