# Secrets (security.md section 5): generated here, stored in Secrets Manager,
# handed to the app's containers at start. They never appear in a file, an
# image or a log.

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "otp_hash_key" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/app"
  description             = "The app's connection strings and signing keys"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    # sslmode=require: RDS offers TLS; this makes the app insist on it.
    DATABASE_URL = "postgresql+psycopg://${aws_db_instance.main.username}:${random_password.database.result}@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}?sslmode=require"
    # rediss: TLS to Valkey, with its password.
    REDIS_URL              = "rediss://:${random_password.cache.result}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
    RATE_LIMIT_STORAGE_URI = "rediss://:${random_password.cache.result}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/1"
    SECRET_KEY             = random_password.secret_key.result
    OTP_HASH_KEY           = random_password.otp_hash_key.result
  })
}

# The MSG91 key (D-058) is not generated: a founder pastes it in the AWS
# console once the MSG91 account exists. OpenTofu creates the empty place for
# it and never overwrites what is put there.
resource "aws_secretsmanager_secret" "msg91" {
  name                    = "${local.name}/msg91-auth-key"
  description             = "MSG91 auth key, pasted in by a founder (D-058)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "msg91" {
  secret_id     = aws_secretsmanager_secret.msg91.id
  secret_string = "not-set-yet"
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# --- image registries ---------------------------------------------------------------

resource "aws_ecr_repository" "image" {
  for_each             = toset(["api", "embeddings"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE" # a tag always means the same image
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "KMS"
  }
}

resource "aws_ecr_lifecycle_policy" "image" {
  for_each   = aws_ecr_repository.image
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images; older ones cannot be rolled back to anyway"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
      action       = { type = "expire" }
    }]
  })
}
