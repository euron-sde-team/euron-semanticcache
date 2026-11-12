# ADR-0005: Namespaces are tenants

- **Status:** Accepted

## Decision

Every entry belongs to one namespace, with its own threshold, TTL, size, and switches for semantic matching and guards.
An API key can be bound to a namespace; the API then refuses any other. A request that names a namespace the key is
not bound to is a 403, not a silent redirect.

## Consequences

- Multi-tenancy is a data-layer property, not a convention: a tenant's key cannot read, flush, export or import another
  tenant's data. A fuzz test asserts it.
- Settings are per tenant, so a strict tenant and a loose one can share one deployment.
