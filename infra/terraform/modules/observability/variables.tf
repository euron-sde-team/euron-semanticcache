variable "name" {
  type = string
}

variable "alarm_topic_arn" {
  description = "SNS topic that receives alarm notifications."
  type        = string
}

variable "alb_arn_suffix" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "api_service_name" {
  type = string
}

variable "redis_replication_group_id" {
  type = string
}
