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

# Encrypts the admins' authenticator secrets at rest (item 101, D-105).
resource "random_password" "second_factor_key" {
  length  = 64
  special = false
}

# Encrypts the platforms' tokens of connected Instagram and YouTube accounts
# at rest (item 29, D-134).
resource "random_password" "platform_token_key" {
  length  = 64
  special = false
}

# The app's own database login, nicheconnect_app (item 97, D-100): it may
# read and write rows and nothing more. Letters and digits only, so it can sit
# in a URL and SCRAM computes the same verifier on both sides (app/db/roles.py).
resource "random_password" "app_database" {
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
    # The API and the nightly task connect as the app's own login, which owns
    # nothing (item 97). Only the release step connects as the owner.
    DATABASE_URL = "postgresql+psycopg://nicheconnect_app:${random_password.app_database.result}@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}?sslmode=require"
    # The owner, for the release step alone (app/db/prepare.py): migrations,
    # DBOS's schema, and setting the app login's password below.
    MIGRATION_DATABASE_URL = "postgresql+psycopg://${aws_db_instance.main.username}:${random_password.database.result}@${aws_db_instance.main.address}:5432/${aws_db_instance.main.db_name}?sslmode=require"
    APP_DATABASE_PASSWORD  = random_password.app_database.result
    # rediss: TLS to Valkey, with its password.
    REDIS_URL              = "rediss://:${random_password.cache.result}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0"
    RATE_LIMIT_STORAGE_URI = "rediss://:${random_password.cache.result}@${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/1"
    SECRET_KEY             = random_password.secret_key.result
    OTP_HASH_KEY           = random_password.otp_hash_key.result
    SECOND_FACTOR_KEY      = random_password.second_factor_key.result
    PLATFORM_TOKEN_KEY     = random_password.platform_token_key.result
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
  secret_id = aws_secretsmanager_secret.msg91.id
  # Starts with "change-me", which the app refuses as an MSG91 key: choosing
  # otp_sender = "msg91" before the real key is pasted stops the app at
  # startup, and ECS rolls the deploy back, instead of every login failing.
  secret_string = "change-me-paste-the-msg91-auth-key"
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# The Claude API key that reads proof screenshots (D-070), pasted in by a
# founder like the MSG91 key, and never overwritten by OpenTofu.
resource "aws_secretsmanager_secret" "anthropic" {
  name                    = "${local.name}/anthropic-api-key"
  description             = "Claude API key for reading proof screenshots, pasted in by a founder (D-070)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "anthropic" {
  secret_id = aws_secretsmanager_secret.anthropic.id
  # Starts with "change-me", which the app refuses as a key: switching
  # proof_reading_enabled on before the real key is pasted stops the app at
  # startup, and ECS rolls the deploy back, instead of every reading failing.
  secret_string = "change-me-paste-the-anthropic-api-key"
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# The Meta app's secret and the Google OAuth client's secret for connected
# accounts (item 29, D-134), pasted in by a founder once Meta App Review and
# Google's verification approve the apps, and never overwritten by OpenTofu.
resource "aws_secretsmanager_secret" "meta_app" {
  name                    = "${local.name}/meta-app-secret"
  description             = "Meta app secret for connected Instagram accounts, pasted in by a founder (D-134)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "meta_app" {
  secret_id = aws_secretsmanager_secret.meta_app.id
  # Starts with "change-me", which the app refuses: switching connections on
  # before the real secret is pasted stops the app at startup.
  secret_string = "change-me-paste-the-meta-app-secret"
  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "google_client" {
  name                    = "${local.name}/google-client-secret"
  description             = "Google OAuth client secret for connected YouTube channels, pasted in by a founder (D-134)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "google_client" {
  secret_id     = aws_secretsmanager_secret.google_client.id
  secret_string = "change-me-paste-the-google-client-secret"
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
