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

# How login codes reach a phone (D-058). "fake" keeps them in memory and only
# runs in local and test; "msg91" sends them by WhatsApp through MSG91.
OtpSenderName = Literal["fake", "msg91"]
# The WhatsApp number registered with MSG91, as MSG91 writes it: country code
# then number, digits only (e.g. 919876543210).
MSG91_NUMBER = re.compile(r"91[6-9][0-9]{9}")
# WhatsApp template names: lower case letters, digits and underscores.
WHATSAPP_TEMPLATE_NAME = re.compile(r"[a-z0-9_]{1,512}")


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
    # Background jobs (D-060). Off unless this instance should run them;
    # several instances may, since DBOS shares the work between them.
    run_jobs: bool = False
    # Login codes (D-058). The MSG91 settings are required only when
    # otp_sender is "msg91", and checked at startup when they are.
    otp_sender: OtpSenderName = "fake"
    msg91_auth_key: SecretStr | None = None
    msg91_whatsapp_number: str | None = None
    msg91_otp_template: str = "login_code"
    msg91_template_language: str = Field(default="en", pattern=r"^[a-z]{2}(_[A-Z]{2})?$")
    # Proof files (D-065): the private bucket infra/ creates, and its region.
    # Unset in local and test, which use the in-memory store instead.
    uploads_bucket: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"
    )
    aws_region: str = Field(default="ap-south-1", pattern=r"^[a-z]{2}(-[a-z]+)+-\d$")
    # Results read from proof (D-070). Off until the validation pack says
    # whether a creator's insights may go to a processor (constraint 6).
    # On, it needs the key, checked at startup.
    proof_reading_enabled: bool = False
    anthropic_api_key: SecretStr | None = None
    proof_reader_model: str = Field(
        default="claude-opus-5-5", pattern=r"^claude-[a-z0-9]+(-[a-z0-9]+)*$"
    )
    # The most screenshots read in any 24 hours: a ceiling on the bill if
    # something loops. The job stops at it; no request ever waits on it.
    proof_reading_daily_limit: int = Field(default=300, ge=1, le=10_000)
    # Error tracking (D-074). Unset means off, which is right for local and
    # test. A DSN only lets a program send errors in, never read them, which
    # is why Sentry treats it as public; it is still a setting, never code.
    sentry_dsn: str | None = Field(
        default=None, pattern=r"^https://[0-9a-f]{32}@[a-z0-9.-]+/[0-9]+$"
    )
    # Which build an error came from: the image's git commit, set by infra/.
    app_release: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._+-]{1,200}$")

    @field_validator("sentry_dsn", "app_release", mode="before")
    @classmethod
    def empty_is_unset(cls, value: object) -> object:
        # `SENTRY_DSN=` in .env means "off", not an address that is "".
        return None if value == "" else value

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def empty_key_is_no_key(cls, value: object) -> object:
        # `ANTHROPIC_API_KEY=` in .env means "none", not an empty key.
        return None if value == "" else value

    @model_validator(mode="after")
    def proof_reading_is_usable(self) -> Settings:
        """Reading switched on without a key fails at startup, not per file."""
        if not self.proof_reading_enabled:
            return self
        key = self.anthropic_api_key.get_secret_value() if self.anthropic_api_key else ""
        if not key or key.startswith(PLACEHOLDER_PREFIX):
            raise ValueError(
                "proof_reading_enabled is on, so ANTHROPIC_API_KEY must be set"
            )
        return self

    @field_validator("uploads_bucket", mode="before")
    @classmethod
    def empty_bucket_is_no_bucket(cls, value: object) -> object:
        # `UPLOADS_BUCKET=` in .env means "none", not a bucket named "".
        return None if value == "" else value

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
    def msg91_is_usable(self) -> Settings:
        """A half-configured provider fails at startup, not at a user's login."""
        if self.otp_sender != "msg91":
            return self
        key = self.msg91_auth_key.get_secret_value() if self.msg91_auth_key else ""
        if not key or key.startswith(PLACEHOLDER_PREFIX):
            raise ValueError("otp_sender is msg91, so MSG91_AUTH_KEY must be set")
        if not self.msg91_whatsapp_number or not MSG91_NUMBER.fullmatch(
            self.msg91_whatsapp_number
        ):
            raise ValueError(
                "otp_sender is msg91, so MSG91_WHATSAPP_NUMBER must be the "
                "registered number as digits, e.g. 919876543210"
            )
        if not WHATSAPP_TEMPLATE_NAME.fullmatch(self.msg91_otp_template):
            raise ValueError(
                "MSG91_OTP_TEMPLATE must be a WhatsApp template name: "
                "lower case letters, digits and underscores"
            )
        return self

    @model_validator(mode="after")
    def keys_must_differ(self) -> Settings:
        if self.secret_key.get_secret_value() == self.otp_hash_key.get_secret_value():
            raise ValueError("secret_key and otp_hash_key must be different keys")
        return self


settings = Settings()
