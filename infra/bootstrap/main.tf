# One-time setup, run once by a founder with the AWS account (D-062, D-063):
# the bucket where OpenTofu keeps its record ("state") of everything it has
# built. Everything else is built by infra/envs/*, which store their state
# here.
#
#   cd infra/bootstrap
#   tofu init
#   tofu apply
#
# This folder's own state stays on the founder's machine: it is one bucket,
# and it cannot keep its record in the bucket it is creating.

terraform {
  required_version = "~> 1.12.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67.0"
    }
  }
}

provider "aws" {
  region = "ap-south-1" # Mumbai (D-062)
  default_tags {
    tags = { project = "nicheconnect", managed_by = "opentofu", part = "bootstrap" }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "state" {
  # The account id makes the name unique worldwide without guessing.
  bucket = "nicheconnect-tofu-state-${data.aws_caller_identity.current.account_id}"

  # State describes every resource, including generated passwords: it must
  # never be deleted by a stray `tofu destroy`.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled" # a bad change to state can be rolled back
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  # Refuse any request that is not over TLS.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

output "state_bucket" {
  value       = aws_s3_bucket.state.bucket
  description = "Put this name in infra/envs/*/backend.tf"
}
