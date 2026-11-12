# ADR-0006: Floci to run the same Terraform locally

- **Status:** Accepted

## Decision

`make up` starts [Floci](https://github.com/floci-io/floci), an MIT-licensed AWS emulator, and applies
`infra/terraform/envs/local-floci` to it. That environment reuses the `storage` and `secrets` modules the AWS
environments use. The API then reads its secrets from Secrets Manager and writes snapshots to S3 with the real SDK.

## Consequences

- The code path tested locally is the code path deployed, with no AWS account.
- ElastiCache, ECS and ALB are not emulated; they are validated with `terraform validate`. Redis runs as a container.
- `terraform init` installs providers from a local plugin cache first, so `make up` works offline after the first run.
