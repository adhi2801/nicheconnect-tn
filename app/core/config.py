from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keys must carry at least 256 bits (D-008). A token_urlsafe(32) value is
# 43 characters, so 32 characters is the floor.
MIN_KEY_LENGTH = 32
PLACEHOLDER_PREFIX = "change-me"


class Settings(BaseSettings):
    """All app settings, read from environment variables (or .env locally).

    The app refuses to start if a required setting is missing or unsafe.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str
    # Connection pool (database.md section 7).
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=50)
    db_statement_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    redis_url: str
    # Addresses or ranges we accept X-Forwarded-For from, comma separated
    # (e.g. "10.0.0.0/8,172.16.0.0/12"). Empty means trust nothing, which is
    # right for local development and any direct-to-internet deployment.
    trusted_proxies: str = ""
    # Where rate-limit counters live. "memory://" is per process, so it only
    # works with a single process (D-003). Point it at Redis before running
    # more than one, e.g. "redis://localhost:6379/1".
    rate_limit_storage_uri: str = "memory://"
    # Signs access tokens (D-008).
    secret_key: SecretStr = Field(min_length=MIN_KEY_LENGTH)
    # Keys the HMAC of one-time codes (D-011). Must differ from secret_key.
    otp_hash_key: SecretStr = Field(min_length=MIN_KEY_LENGTH)
    access_token_expire_minutes: int = Field(default=15, ge=1, le=15)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=30)

    @field_validator("rate_limit_storage_uri")
    @classmethod
    def known_storage(cls, value: str) -> str:
        if not value.startswith(("memory://", "redis://", "rediss://")):
            raise ValueError("must start with memory://, redis:// or rediss://")
        return value

    @field_validator("secret_key", "otp_hash_key")
    @classmethod
    def reject_placeholder(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value().startswith(PLACEHOLDER_PREFIX):
            raise ValueError("still the .env.example placeholder; generate a real key")
        return value

    @model_validator(mode="after")
    def keys_must_differ(self) -> "Settings":
        if self.secret_key.get_secret_value() == self.otp_hash_key.get_secret_value():
            raise ValueError("secret_key and otp_hash_key must be different keys")
        return self


settings = Settings()
