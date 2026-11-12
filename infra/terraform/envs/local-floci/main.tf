# The SAME modules that build the AWS environments, applied to the Floci emulator.
# Floci covers S3 and Secrets Manager; Redis runs as a container in Docker Compose.

provider "aws" {
  region                      = var.region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true
  s3_use_path_style           = true

  endpoints {
    s3             = var.endpoint
    secretsmanager = var.endpoint
    sts            = var.endpoint
    iam            = var.endpoint
  }
}

locals {
  tags = { Project = "semanticcache", Environment = "local" }
}

module "storage" {
  source         = "../../modules/storage"
  name           = var.name
  force_destroy  = true
  versioning     = false
  retention_days = 7
  tags           = local.tags
}

module "secrets" {
  source                  = "../../modules/secrets"
  name                    = var.name
  recovery_window_in_days = 0
  bootstrap_api_key       = var.bootstrap_api_key
  tags                    = local.tags
}
