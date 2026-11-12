output "security_group_id" {
  value = aws_security_group.redis.id
}

output "url_secret_arn" {
  description = "Secrets Manager secret holding the rediss:// URL."
  value       = aws_secretsmanager_secret.url.arn
}

output "replication_group_id" {
  value = aws_elasticache_replication_group.this.id
}

output "primary_endpoint" {
  value = aws_elasticache_replication_group.this.primary_endpoint_address
}
