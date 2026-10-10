# What differs between staging and production. Everything else is decided
# once, in this module, so the two environments cannot drift apart in how
# they are built, only in how big they are.

variable "environment" {
  type        = string
  description = "staging or production; also what the app's ENVIRONMENT setting becomes"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "domain_name" {
  type        = string
  description = "The API's own name, e.g. api.example.in. HTTPS needs one; there is no plain-HTTP option."
}

variable "cors_allowed_origins" {
  type        = string
  default     = ""
  description = "Websites allowed to call the API from a browser, comma separated (D-044). Empty until the dashboard exists."
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

# --- database -------------------------------------------------------------------

variable "db_engine_version" {
  type        = string
  default     = "18"
  description = "PostgreSQL major (D-049); minor versions are applied by AWS in the maintenance window."
}

variable "db_instance_class" {
  type = string
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_max_allocated_storage_gb" {
  type        = number
  default     = 100
  description = "Storage grows by itself up to this, so a full disk never takes the site down."
}

variable "db_backup_retention_days" {
  type = number
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_deletion_protection" {
  type = bool
}

# --- cache --------------------------------------------------------------------------

variable "cache_node_type" {
  type = string
}

variable "cache_engine_version" {
  type        = string
  default     = "9.1"
  description = "Valkey (D-048); matches what runs locally and in CI."
}

variable "cache_replicas" {
  type        = number
  default     = 0
  description = "Extra nodes; one or more turns on automatic failover."
}

# --- app ----------------------------------------------------------------------------

variable "image_tag" {
  type        = string
  description = "The image to run, by its git commit, never 'latest'."
}

variable "api_cpu" {
  type    = number
  default = 512
}

variable "api_memory" {
  type    = number
  default = 1024
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "embeddings_cpu" {
  type    = number
  default = 1024
}

variable "embeddings_memory" {
  type        = number
  default     = 4096
  description = "The embedding model needs about 2.5 GB once loaded (D-052)."
}

# CERT-In's Directions of 28 April 2022 require every company to keep the
# logs of its systems for 180 days, in India (D-086, legal.md section 3.2).
# The log group is in Mumbai; this keeps them long enough. Lower only with
# a decision that names the legal answer allowing it.
variable "log_retention_days" {
  type    = number
  default = 180
  validation {
    condition     = var.log_retention_days >= 180
    error_message = "log_retention_days must be at least 180: CERT-In requires 180 days of logs."
  }
}

# --- login codes (D-058) ------------------------------------------------------------

variable "otp_sender" {
  type        = string
  default     = "fake"
  description = "msg91 once the MSG91 key is in its secret. Until then the app starts, and login is refused outside local."
  validation {
    condition     = contains(["fake", "msg91"], var.otp_sender)
    error_message = "otp_sender must be fake or msg91."
  }
}

variable "msg91_whatsapp_number" {
  type        = string
  default     = ""
  description = "The WhatsApp number registered with MSG91, digits only (919876543210)."
}

variable "msg91_otp_template" {
  type    = string
  default = "login_code"
}

# --- results read from proof (D-070) ------------------------------------------------

variable "proof_reading_enabled" {
  type        = bool
  default     = false
  description = "true once the validation pack allows it and the Claude key is in its secret. Until the key is pasted, true stops the app at startup."
}

variable "proof_reader_model" {
  type        = string
  default     = "claude-opus-5-5"
  description = "The Claude model that reads proof screenshots, chosen by scripts/score_proof_reader.py."
  validation {
    condition     = can(regex("^claude-[a-z0-9]+(-[a-z0-9]+)*$", var.proof_reader_model))
    error_message = "proof_reader_model must be a Claude model id, such as claude-opus-5-5."
  }
}

variable "sentry_dsn" {
  type        = string
  default     = ""
  description = "Where errors are sent (D-074). Empty means error tracking is off. A DSN can only send errors in, never read them, so it is a setting, not a secret."
  validation {
    condition     = var.sentry_dsn == "" || can(regex("^https://[0-9a-f]{32}@[a-z0-9.-]+/[0-9]+$", var.sentry_dsn))
    error_message = "sentry_dsn must be empty or a Sentry DSN, https://<key>@<host>/<project>."
  }
}

variable "upi_notice_version" {
  type        = string
  default     = ""
  description = "The version of the UPI notice creators read (D-085). Empty keeps adding a UPI ID off; set it once the validation pack supplies the wording."
  validation {
    condition     = var.upi_notice_version == "" || can(regex("^[A-Za-z0-9._-]{1,40}$", var.upi_notice_version))
    error_message = "upi_notice_version must be empty, or 1 to 40 letters, digits, dots, dashes or underscores."
  }
}
