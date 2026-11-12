# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.x (latest minor) | Yes |
| Older minors | No |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository ("Security" tab, "Report a vulnerability").

Please include the affected component (`apps/api`, `packages/core`, `infra/terraform/...`) and version or commit,
a description of the impact, steps to reproduce, and any suggested mitigation.

| Stage | Target |
| ----- | ------ |
| Acknowledgement | within 3 business days |
| Initial assessment and severity | within 7 business days |
| Fix or mitigation for critical / high issues | within 30 days |
| Coordinated public disclosure | after a fix is released, credited to you unless you prefer otherwise |

## Scope

In scope: the code in this repository and the infrastructure it provisions with its default settings. Of particular
interest: any way a cached response could be served to a request it should not match (cross-namespace, cross-model,
cross-system-prompt or cross-conversation leakage).

Out of scope:

- **Semantic false positives within a safety scope.** Similarity matching is approximate by design. Tune the
  per-namespace threshold and use `cache: bypass` for requests that must never be cached.
- **Prompt content you choose to cache.** Prompts and responses are stored verbatim in Redis and exports.
- Findings that require a compromised host, AWS account, or leaked deployment secrets.
- Redis exposed to the public internet. Redis must be reachable only from the API.

## Hardening checklist for operators

- Put Redis in private subnets with TLS and AUTH (the `redis` Terraform module does this).
- Set a long random `SC_API_KEY_PEPPER` and keep it in Secrets Manager.
- Use one API key per application with the narrowest scopes, and one namespace per tenant.
- Never cache prompts containing secrets or personal data; use a short TTL or `cache: bypass`.
- Restrict `SC_CORS_ORIGINS` to your console origin.
