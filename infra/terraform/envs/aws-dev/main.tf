provider "aws" {
  region = var.region
  default_tags {
    tags = local.tags
  }
}

locals {
  name = "${var.project}-${var.environment}"
  tags = { Project = var.project, Environment = var.environment, ManagedBy = "terraform" }
}

data "aws_caller_identity" "current" {}

module "network" {
  source             = "../../modules/network"
  name               = local.name
  single_nat_gateway = true
}

module "ecr" {
  source       = "../../modules/ecr"
  name         = local.name
  force_delete = true
}

module "storage" {
  source         = "../../modules/storage"
  name           = "${local.name}-${data.aws_caller_identity.current.account_id}"
  force_destroy  = true
  retention_days = 30
}

module "secrets" {
  source                  = "../../modules/secrets"
  name                    = local.name
  recovery_window_in_days = 0
  upstream_api_key        = var.upstream_api_key
  embedding_api_key       = var.embedding_api_key
}

module "notifications" {
  source      = "../../modules/notifications"
  name        = local.name
  alert_email = var.alert_email
}

resource "aws_ecs_cluster" "this" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Both tiers share one security group: reachable only from the load balancer.
resource "aws_security_group" "tasks" {
  name_prefix = "${local.name}-tasks-"
  description = "SemanticCache ECS tasks"
  vpc_id      = module.network.vpc_id
  tags        = { Name = "${local.name}-tasks" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_egress_rule" "tasks_all" {
  security_group_id = aws_security_group.tasks.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Redis, the LLM provider, AWS APIs (via NAT) and image pulls"
}

module "alb" {
  source            = "../../modules/alb"
  name              = local.name
  vpc_id            = module.network.vpc_id
  vpc_cidr          = "10.40.0.0/16"
  public_subnet_ids = module.network.public_subnet_ids
  certificate_arn   = var.certificate_arn
  ingress_cidr      = var.ingress_cidr
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  for_each                     = { api = 8180, console = 3100 }
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = module.alb.security_group_id
  from_port                    = each.value
  to_port                      = each.value
  ip_protocol                  = "tcp"
  description                  = "ALB to ${each.key}"
}

module "redis" {
  source                         = "../../modules/redis"
  name                           = local.name
  vpc_id                         = module.network.vpc_id
  subnet_ids                     = module.network.private_subnet_ids
  allowed_security_group_ids     = [aws_security_group.tasks.id]
  node_type                      = var.redis_node_type
  num_cache_clusters             = var.redis_nodes
  apply_immediately              = true
  secret_recovery_window_in_days = 0
}

data "aws_iam_policy_document" "api_task" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [module.secrets.secret_arn]
  }
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${module.storage.bucket_arn}/exports/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [module.storage.bucket_arn]
  }
}

locals {
  scheme   = var.certificate_arn == null ? "http" : "https"
  base_url = "${local.scheme}://${module.alb.dns_name}"
}

# The API embeds prompts and searches vectors in memory, so it is sized for CPU and RAM, not for connections.
module "api" {
  source               = "../../modules/ecs-service"
  name                 = "${local.name}-api"
  cluster_arn          = aws_ecs_cluster.this.arn
  image                = "${module.ecr.repository_urls["api"]}:${var.image_tag}"
  port                 = 8180
  cpu                  = 512
  memory               = 1024
  desired_count        = var.api_count
  min_count            = var.api_count
  max_count            = var.api_max_count
  subnet_ids           = module.network.private_subnet_ids
  security_group_ids   = [aws_security_group.tasks.id]
  target_group_arn     = module.alb.api_target_group_arn
  health_check_command = "python -c \"import urllib.request as u; u.urlopen('http://localhost:8180/healthz')\""
  task_policy_json     = data.aws_iam_policy_document.api_task.json
  environment = {
    SC_SECRETS_ARN        = module.secrets.secret_arn
    SC_CORS_ORIGINS       = local.base_url
    SC_ENVIRONMENT        = var.environment
    SC_UPSTREAM_BASE_URL  = var.upstream_base_url
    SC_EXPORT_BUCKET      = module.storage.bucket
    SC_EMBEDDER           = var.embedder
    SC_EMBEDDING_BASE_URL = var.upstream_base_url
    AWS_REGION            = var.region
  }
  secrets = { SC_REDIS_URL = module.redis.url_secret_arn }
}

module "console" {
  source             = "../../modules/ecs-service"
  name               = "${local.name}-console"
  cluster_arn        = aws_ecs_cluster.this.arn
  image              = "${module.ecr.repository_urls["console"]}:${var.image_tag}"
  port               = 3100
  desired_count      = 1
  subnet_ids         = module.network.private_subnet_ids
  security_group_ids = [aws_security_group.tasks.id]
  target_group_arn   = module.alb.console_target_group_arn
}

module "observability" {
  source                     = "../../modules/observability"
  name                       = local.name
  alarm_topic_arn            = module.notifications.topic_arn
  alb_arn_suffix             = module.alb.arn_suffix
  cluster_name               = aws_ecs_cluster.this.name
  api_service_name           = module.api.service_name
  redis_replication_group_id = module.redis.replication_group_id
}
