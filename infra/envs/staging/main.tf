# Staging: where designers and founders try things (D-062). Same module as
# production, sized down, and cheap to switch off. Deletion protection is
# off here so it can be torn down and rebuilt; its data is never real.
#
#   cd infra/envs/staging
#   tofu init -backend-config="bucket=<state bucket from infra/bootstrap>"
#   tofu plan -var "image_tag=<git commit>" -var "domain_name=<api staging name>"

terraform {
  required_version = "~> 1.12.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9.1"
    }
  }
  backend "s3" {
    key          = "staging/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true # two people applying at once cannot corrupt state
  }
}

provider "aws" {
  region = "ap-south-1" # Mumbai (D-062)
  default_tags {
    tags = { project = "nicheconnect", environment = "staging", managed_by = "opentofu" }
  }
}

variable "image_tag" {
  type = string
}

variable "domain_name" {
  type = string
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

  environment = "staging"
  domain_name = var.domain_name
  image_tag   = var.image_tag
  vpc_cidr    = "10.20.0.0/16"

  db_instance_class        = "db.t4g.micro"
  db_backup_retention_days = 1
  db_deletion_protection   = false

  cache_node_type = "cache.t4g.micro"

  api_cpu           = 512
  api_memory        = 1024
  api_desired_count = 1

  otp_sender            = var.otp_sender
  msg91_whatsapp_number = var.msg91_whatsapp_number
  proof_reading_enabled = var.proof_reading_enabled
  sentry_dsn            = var.sentry_dsn
}

output "app" {
  value = module.app
}
