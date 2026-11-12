variable "name" {
  description = "Name prefix, e.g. semanticcache-prod. The bucket is named <name>-exports."
  type        = string
}

variable "retention_days" {
  description = "Days before exported snapshots expire."
  type        = number
  default     = 90
}

variable "versioning" {
  description = "Keep object versions."
  type        = bool
  default     = true
}

variable "force_destroy" {
  description = "Allow terraform destroy to delete a non-empty bucket (never in production)."
  type        = bool
  default     = false
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key for SSE-KMS. Null uses S3-managed AES256."
  type        = string
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
