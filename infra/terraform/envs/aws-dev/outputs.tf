output "url" {
  description = "Console and API entry point."
  value       = local.base_url
}

output "ecr_repositories" {
  value = module.ecr.repository_urls
}

output "redis_url_secret_arn" {
  value = module.redis.url_secret_arn
}

output "app_secret_arn" {
  description = "Holds the bootstrap API key: aws secretsmanager get-secret-value --secret-id <arn>"
  value       = module.secrets.secret_arn
}

output "export_bucket" {
  value = module.storage.bucket
}
