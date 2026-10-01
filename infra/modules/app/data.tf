# The database, the cache and the file store (D-062).

# --- PostgreSQL 18 ----------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "random_password" "database" {
  length  = 40
  special = false # it goes inside a connection URL
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  db_name  = "nicheconnect"
  username = "nicheconnect"
  password = random_password.database.result
  # The password lives in the app's secret (secrets.tf) as part of its
  # DATABASE_URL, and in this state, which is encrypted (bootstrap).

  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = var.db_max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  # Point-in-time restore to any second within the window. A restore is
  # tested before the first real user (D-062 point 5).
  backup_retention_period = var.db_backup_retention_days
  backup_window           = "20:00-21:00" # 01:30-02:30 in Tamil Nadu
  maintenance_window      = "sun:21:30-sun:22:30"
  copy_tags_to_snapshot   = true

  auto_minor_version_upgrade  = true # security fixes without waiting (D-047)
  allow_major_version_upgrade = false
  deletion_protection         = var.db_deletion_protection
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${local.name}-final"

  performance_insights_enabled    = true
  enabled_cloudwatch_logs_exports = ["postgresql"]
}

# --- Valkey ---------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "random_password" "cache" {
  length  = 48
  special = false
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = local.name
  description          = "Rate limits and idempotency (D-048)"
  engine               = "valkey"
  engine_version       = var.cache_engine_version
  node_type            = var.cache_node_type
  num_cache_clusters   = 1 + var.cache_replicas
  port                 = 6379

  automatic_failover_enabled = var.cache_replicas > 0
  multi_az_enabled           = var.cache_replicas > 0

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.cache.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.cache.result

  maintenance_window       = "sun:22:30-sun:23:30"
  snapshot_retention_limit = 1
}

# --- uploaded files -------------------------------------------------------------------

resource "aws_s3_bucket" "uploads" {
  # Photos, logos, proof screenshots, media-kit images. Private: files are
  # uploaded and read through short-lived signed links, never a public URL.
  bucket_prefix = "${local.name}-uploads-"
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  versioning_configuration {
    status = "Enabled" # an overwritten or deleted file can be recovered
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    id     = "tidy"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 2 # an upload abandoned on a bad connection
    }
    noncurrent_version_expiration {
      noncurrent_days = 30 # old versions kept a month, then gone
    }
  }
  # Proof originals, as the phone sent them, location data and all (D-065).
  # Where two rules overlap S3 applies the shorter, so these beat "tidy".
  rule {
    id     = "proof-originals"
    status = "Enabled"
    filter {
      prefix = "proof-files/incoming/"
    }
    expiration {
      days = 1 # an upload asked for and never submitted
    }
    noncurrent_version_expiration {
      # The cleaner deletes each original once its clean copy exists. With
      # versioning on, that delete only hides it; without this rule it could
      # still be recovered for a month. One day is the least S3 allows.
      noncurrent_days = 1
    }
  }
}

# The website uploads proof straight to the bucket (D-062), so the browser
# must be allowed to. The phone apps need no rule. None until the dashboard
# has an address, like the API's own list (D-044).
resource "aws_s3_bucket_cors_configuration" "uploads" {
  count  = length(local.browser_origins) > 0 ? 1 : 0
  bucket = aws_s3_bucket.uploads.id
  cors_rule {
    allowed_methods = ["POST", "GET"] # the signed upload form, and a signed view link
    allowed_origins = local.browser_origins
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}

locals {
  browser_origins = compact([for origin in split(",", var.cors_allowed_origins) : trimspace(origin)])
}

resource "aws_s3_bucket_policy" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.uploads.arn, "${aws_s3_bucket.uploads.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
