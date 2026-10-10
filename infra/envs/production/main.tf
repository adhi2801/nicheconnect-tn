# Production: real creators, real brands (D-062). Deletion protection on,
# two weeks of point-in-time backups, and two API containers so one can be
# replaced while the other serves. Deploys here only by a founder's hand.
#
#   cd infra/envs/production
#   tofu init -backend-config="bucket=<state bucket from infra/bootstrap>"
#   tofu plan -var "image_tag=<git commit>" -var "domain_name=<api name>"

terraform {
  required_version = "~> 1.12.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9.1"
    }
  }
  backend "s3" {
    key          = "production/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "ap-south-1" # Mumbai (D-062)
  default_tags {
    tags = { project = "nicheconnect", environment = "production", managed_by = "opentofu" }
  }
}

variable "image_tag" {
  type = string
}

variable "domain_name" {
  type = string
}

variable "cors_allowed_origins" {
  type    = string
  default = ""
}

variable "otp_sender" {
  type    = string
  default = "fake"
}

variable "msg91_whatsapp_number" {
  type    = string
  default = ""
}

variable "proof_reading_enabled" {
  type    = bool
  default = false
}

variable "sentry_dsn" {
  type    = string
  default = ""
}

module "app" {
  source = "../../modules/app"

  environment          = "production"
  domain_name          = var.domain_name
  image_tag            = var.image_tag
  cors_allowed_origins = var.cors_allowed_origins
  vpc_cidr             = "10.30.0.0/16"

  db_instance_class        = "db.t4g.small"
  db_backup_retention_days = 14
  db_deletion_protection   = true

  cache_node_type = "cache.t4g.micro"

  api_cpu           = 512
  api_memory        = 1024
  api_desired_count = 2

  otp_sender            = var.otp_sender
  msg91_whatsapp_number = var.msg91_whatsapp_number
  proof_reading_enabled = var.proof_reading_enabled
  sentry_dsn            = var.sentry_dsn
}

output "app" {
  value = module.app
}
