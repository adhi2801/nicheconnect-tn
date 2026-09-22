import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Keys must carry at least 256 bits (D-008). A token_urlsafe(32) value is
# 43 characters, so 32 characters is the floor.
MIN_KEY_LENGTH = 32
PLACEHOLDER_PREFIX = "change-me"

# Every environment the app knows. Anything else is a typo, and a typo must
# stop the app rather than quietly count as one of these (D-044).
Environment = Literal["local", "test", "staging", "production"]

# Reached over plain HTTP on a developer's own machine.
PLAIN_HTTP_ENVIRONMENTS = frozenset({"local", "test"})

# A host name as a browser writes it in the Origin header: lower case, digits,
# dots and hyphens. An international name arrives as punycode, so this covers it.
HOST_NAME = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*")
DEFAULT_PORTS = {"http": 80, "https": 443}


def split_origins(raw: str) -> tuple[str, ...]:
    """The comma-separated setting as a list, blanks dropped, repeats removed."""
    entries = (entry.strip() for entry in raw.split(","))
    return tuple(dict.fromkeys(entry for entry in entries if entry))


def _is_host(host: str) -> bool:
    # Only a bracketed IPv6 address gives a host with a colon, and urlsplit
    # has already refused a malformed one, as "is not a web address".
    return ":" in host or HOST_NAME.fullmatch(host) is not None


def origin_problem(origin: str, *, allow_http: bool) -> str | None:
    """Why a browser would never send this origin, or None if it would.

    The CORS check compares strings exactly, so "https://app.com/" never
    matches the "https://app.com" a browser sends. Such an entry would not
    fail; it would silently block the dashboard. Refusing it at startup,
    with the form to write instead, turns that into a one-line fix.
    """
    if origin == "*":
        return "is a wildcard; list each website instead"
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        return "is not a web address"
    scheme, host = parts.scheme, parts.hostname
    if scheme not in DEFAULT_PORTS or not host:
        return "must be a web address starting with https://"
    if scheme == "http" and not allow_http:
        return "must use https:// outside local development"
    if not _is_host(host):
        return "has a host name a browser would never send"
    canonical = f"{scheme}://{f'[{host}]' if ':' in host else host}"
    if port is not None and port != DEFAULT_PORTS[scheme]:
        canonical += f":{port}"
    if origin != canonical:
        return f"must be written exactly as a browser sends it: {canonical}"
    return None


class Settings(BaseSettings):
    """All app settings, read from environment variables (or .env locally).

    The app refuses to start if a required setting is missing or unsafe.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Environment = "local"
    # Websites allowed to call the API from a browser, comma separated
    # (e.g. "https://app.example.in"). Empty means none, which is right until
    # the brand dashboard exists. The mobile app is unaffected: CORS is a
    # browser rule (D-044).
    cors_allowed_origins: str = ""
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

    @field_validator("cors_allowed_origins")
    @classmethod
    def usable_origins(cls, value: str, info: ValidationInfo) -> str:
        # `environment` is declared first, so it is already checked here. If
        # it failed its own check it is missing, and https is required.
        allow_http = info.data.get("environment") in PLAIN_HTTP_ENVIRONMENTS
        for origin in split_origins(value):
            problem = origin_problem(origin, allow_http=allow_http)
            if problem:
                raise ValueError(f"'{origin}' {problem}")
        return value

    @property
    def cors_origins(self) -> tuple[str, ...]:
        """The allowed websites, one per entry, as the CORS check needs them."""
        return split_origins(self.cors_allowed_origins)

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
