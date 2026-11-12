variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups (the API tasks) allowed to reach Redis."
  type        = list(string)
}

variable "node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "engine_version" {
  type    = string
  default = "7.1"
}

variable "num_cache_clusters" {
  description = "1 = single node; 2+ = primary with replicas and automatic failover."
  type        = number
  default     = 1
}

variable "snapshot_retention_days" {
  type    = number
  default = 1
}

variable "apply_immediately" {
  type    = bool
  default = false
}

variable "secret_recovery_window_in_days" {
  type    = number
  default = 7
}

variable "tags" {
  type    = map(string)
  default = {}
}
