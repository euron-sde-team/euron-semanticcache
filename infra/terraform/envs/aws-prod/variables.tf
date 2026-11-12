variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "semanticcache"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "image_tag" {
  description = "Tag of the api and console images in ECR."
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate for HTTPS. Required in production."
  type        = string
}

variable "alert_email" {
  type    = string
  default = null
}

variable "ingress_cidr" {
  description = "CIDR allowed to reach the console and API. Restrict it: the console is an operator tool."
  type        = string
}

variable "upstream_base_url" {
  description = "OpenAI-compatible endpoint that cache misses are forwarded to."
  type        = string
  default     = "https://api.openai.com/v1"
}

variable "upstream_api_key" {
  description = "Provider API key. Stored in Secrets Manager, never in task definitions."
  type        = string
  default     = ""
  sensitive   = true
}

variable "embedder" {
  description = "hashing (no dependencies, lexical) or openai (true semantic matching via the upstream's /embeddings)."
  type        = string
  default     = "hashing"
}

variable "embedding_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "api_count" {
  type    = number
  default = 2
}

variable "api_max_count" {
  type    = number
  default = 10
}

variable "redis_node_type" {
  type    = string
  default = "cache.r7g.large"
}

variable "redis_nodes" {
  type    = number
  default = 2
}
