variable "name" {
  type = string
}

variable "recovery_window_in_days" {
  description = "0 deletes immediately (local and dev); use 7-30 in production."
  type        = number
  default     = 7
}

variable "kms_key_id" {
  type    = string
  default = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "bootstrap_api_key" {
  description = "Use this all-scopes key instead of generating one (local demos). Format: sc_<prefix>_<secret>."
  type        = string
  default     = null
  sensitive   = true
}

variable "upstream_api_key" {
  description = "API key for the LLM provider that cache misses are forwarded to. Empty when the provider needs none."
  type        = string
  default     = ""
  sensitive   = true
}

variable "embedding_api_key" {
  description = "API key for the embeddings endpoint (only when SC_EMBEDDER=openai)."
  type        = string
  default     = ""
  sensitive   = true
}
