# Deploy to AWS

The same Terraform that runs on Floci builds a real environment: VPC, ElastiCache Redis, ALB, ECS Fargate (API and
console) with CPU autoscaling, an S3 exports bucket, Secrets Manager, a CloudWatch dashboard and alarms.

```bash
cd infra/terraform/envs/aws-dev
cp backend.tf.example backend.tf && cp terraform.tfvars.example terraform.tfvars
export TF_VAR_upstream_api_key=sk-...           # your LLM provider key: stored in Secrets Manager
terraform init
terraform apply -target=module.ecr              # create the registries first
```

Build and push the two images (`infra/docker/api.Dockerfile`, `console.Dockerfile`) to the ECR URLs it prints,
tagged with `image_tag`. Pass the public URL to the console at build time:

```bash
docker build -f infra/docker/console.Dockerfile --build-arg NEXT_PUBLIC_SC_API_URL=https://cache.example.com .
```

Then `terraform apply`. The `url` output is the ALB; the console and API share it (API paths go to the API).

## First sign-in

```bash
aws secretsmanager get-secret-value --secret-id <app_secret_arn> --query SecretString --output text | jq -r .bootstrap_api_key
```

Open the console, paste the key, create one **namespace-bound key per tenant** under Settings, then stop using the
bootstrap key.

## Choosing the embedder

`embedder = "openai"` (and `upstream_base_url` pointing at a provider with `/embeddings`) enables real paraphrase
matching. The default `hashing` needs nothing but matches wording only.

## Sizing

The API embeds prompts and searches vectors in memory, so size it for CPU and RAM: a namespace of `N` entries uses about
`N x 512 x 4` bytes per API task (100k entries is roughly 200 MB). `max_entries` bounds it. Redis holds the same data once.

## Production differences (`aws-prod`)

| | dev | prod |
| --- | --- | --- |
| NAT gateways | 1 | one per AZ |
| Redis | 1 `cache.t4g.micro` | 2 `cache.r7g.large`, automatic failover, 7-day snapshots |
| API tasks | 1 to 4 (512 CPU, 1 GB) | 2 to 10 (1024 CPU, 2 GB) |
| HTTPS | optional | required (`certificate_arn`) |
| Secrets recovery window | 0 | 30 days |
| Exports bucket | force delete, 30 days | protected, 365 days |
| ALB | open | `ingress_cidr` required, deletion protection |

> The AWS environments pass `terraform validate` but have not been applied to a real account by this repository's
> tests. Review the plan before applying.
