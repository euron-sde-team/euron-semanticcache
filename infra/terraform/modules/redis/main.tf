# ElastiCache for Redis: private, TLS in transit, AUTH token, encrypted at rest.
# SemanticCache needs a non-cluster-mode replication group: its Lua scripts touch several keys at once.

resource "random_password" "auth" {
  length  = 40
  special = false
}

resource "aws_security_group" "redis" {
  name_prefix = "${var.name}-redis-"
  description = "SemanticCache Redis: only the API tier may connect"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-redis" })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "from_app" {
  for_each                     = toset(var.allowed_security_group_ids)
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = each.value
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  description                  = "Redis from application tasks"
}

resource "aws_elasticache_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = var.name
  description                = "SemanticCache entries, vectors and statistics"
  engine                     = "redis"
  engine_version             = var.engine_version
  node_type                  = var.node_type
  port                       = 6379
  num_cache_clusters         = var.num_cache_clusters
  automatic_failover_enabled = var.num_cache_clusters > 1
  multi_az_enabled           = var.num_cache_clusters > 1
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.auth.result
  snapshot_retention_limit   = var.snapshot_retention_days
  apply_immediately          = var.apply_immediately
  parameter_group_name       = aws_elasticache_parameter_group.this.name
  tags                       = var.tags
}

# noeviction: the cache bounds itself (max_entries per namespace, LRU). Redis evicting on its own could drop
# API keys, namespace settings or statistics, so it must fail writes loudly instead.
resource "aws_elasticache_parameter_group" "this" {
  name   = var.name
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "noeviction"
  }
}

resource "aws_secretsmanager_secret" "url" {
  name                    = "${var.name}/redis-url"
  description             = "SC_REDIS_URL for the API"
  recovery_window_in_days = var.secret_recovery_window_in_days
  tags                    = var.tags
}

resource "aws_secretsmanager_secret_version" "url" {
  secret_id     = aws_secretsmanager_secret.url.id
  secret_string = "rediss://:${random_password.auth.result}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
}
