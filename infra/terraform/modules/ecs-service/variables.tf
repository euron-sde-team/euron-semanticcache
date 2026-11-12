variable "name" {
  type = string
}

variable "cluster_arn" {
  type = string
}

variable "image" {
  type = string
}

variable "command" {
  type    = list(string)
  default = null
}

variable "port" {
  description = "Container port, or null for services that accept no traffic (none for this project)."
  type        = number
  default     = null
}

variable "cpu" {
  type    = number
  default = 256
}

variable "memory" {
  type    = number
  default = 512
}

variable "cpu_architecture" {
  type    = string
  default = "ARM64"
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "min_count" {
  type    = number
  default = 1
}

variable "max_count" {
  description = "Above min_count enables CPU target-tracking autoscaling."
  type        = number
  default     = 1
}

variable "cpu_target_percent" {
  type    = number
  default = 60
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "secrets" {
  description = "Container env var name => Secrets Manager ARN."
  type        = map(string)
  default     = {}
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "target_group_arn" {
  type    = string
  default = null
}

variable "health_check_command" {
  type    = string
  default = null
}

variable "task_policy_json" {
  description = "IAM policy JSON for the application's own AWS calls."
  type        = string
  default     = null
}

variable "stop_timeout" {
  description = "Seconds ECS waits after SIGTERM. Time to finish in-flight requests before the task is killed (max 120 on Fargate)."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
