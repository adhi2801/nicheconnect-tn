import secrets
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def valid_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "database_url": "postgresql+psycopg://user:pass@localhost:5432/db",
        "redis_url": "redis://localhost:6379/0",
        "secret_key": secrets.token_urlsafe(32),
        "otp_hash_key": secrets.token_urlsafe(32),
    }
    values.update(overrides)
    return values


def load(**overrides: Any) -> Settings:
    # _env_file=None: ignore the developer's .env so only these values count.
    return Settings(_env_file=None, **valid_values(**overrides))


def assert_rejected(field: str, **overrides: Any) -> None:
    with pytest.raises(ValidationError) as exc_info:
        load(**overrides)
    assert field in {str(error["loc"][0]) for error in exc_info.value.errors()}


def test_valid_settings_load_with_safe_defaults():
    settings = load()

    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_token_expire_days == 30
    assert settings.db_statement_timeout_ms == 5000


def test_keys_are_hidden_when_printed():
    settings = load(secret_key="k" * 40)

    assert "k" * 40 not in repr(settings)
    assert "k" * 40 not in str(settings.secret_key)


@pytest.mark.parametrize(
    "field", ["database_url", "redis_url", "secret_key", "otp_hash_key"]
)
def test_missing_required_setting_is_rejected(monkeypatch, field):
    monkeypatch.delenv(field.upper(), raising=False)
    values = valid_values()
    del values[field]

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **values)
    assert field in str(exc_info.value)


@pytest.mark.parametrize("field", ["secret_key", "otp_hash_key"])
def test_short_key_is_rejected(field):
    assert_rejected(field, **{field: "x" * 31})


@pytest.mark.parametrize("field", ["secret_key", "otp_hash_key"])
def test_placeholder_key_is_rejected(field):
    assert_rejected(field, **{field: "change-me-generate-a-real-key-please"})


def test_same_key_for_both_purposes_is_rejected():
    key = secrets.token_urlsafe(32)

    with pytest.raises(ValidationError) as exc_info:
        load(secret_key=key, otp_hash_key=key)
    assert "must be different" in str(exc_info.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access_token_expire_minutes", 16),
        ("access_token_expire_minutes", 0),
        ("refresh_token_expire_days", 31),
        ("db_statement_timeout_ms", 0),
    ],
)
def test_out_of_range_number_is_rejected(field, value):
    assert_rejected(field, **{field: value})


# --- Environment (D-044) -------------------------------------------------


@pytest.mark.parametrize("environment", ["local", "test", "staging", "production"])
def test_known_environment_is_accepted(environment):
    assert load(environment=environment).environment == environment


@pytest.mark.parametrize("environment", ["prod", "Production", "dev", ""])
def test_unknown_environment_stops_the_app(environment):
    """A typo must not quietly count as some environment: it decides HSTS,
    the OTP sender and whether the API docs are public."""
    assert_rejected("environment", environment=environment)


# --- CORS allow-list (D-044) ---------------------------------------------


def test_no_website_is_allowed_by_default():
    assert load().cors_origins == ()


def test_allowed_websites_are_read_as_a_list():
    settings = load(
        environment="production",
        cors_allowed_origins="https://app.example.in, https://brands.example.in:8443,",
    )

    assert settings.cors_origins == (
        "https://app.example.in",
        "https://brands.example.in:8443",
    )


def test_a_repeated_website_is_listed_once():
    settings = load(cors_allowed_origins="https://a.example.in,https://a.example.in")

    assert settings.cors_origins == ("https://a.example.in",)


@pytest.mark.parametrize("environment", ["local", "test"])
@pytest.mark.parametrize(
    "origin", ["http://localhost:5173", "http://127.0.0.1:3000", "http://[::1]:5173"]
)
def test_plain_http_is_allowed_on_a_developer_machine(environment, origin):
    settings = load(environment=environment, cors_allowed_origins=origin)

    assert settings.cors_origins == (origin,)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_plain_http_is_refused_once_deployed(environment):
    with pytest.raises(ValidationError) as exc_info:
        load(environment=environment, cors_allowed_origins="http://app.example.in")

    assert "must use https://" in str(exc_info.value)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "app.example.in",
        "ftp://app.example.in",
        "https://",
        "https://app.example.in:99999",
        "https://exa mple.in",
        "https://app_example.in",
        "http://[zzz]:5173",
        "http://[::1",
    ],
)
def test_an_origin_no_browser_sends_stops_the_app(origin):
    assert_rejected("cors_allowed_origins", cors_allowed_origins=origin)


@pytest.mark.parametrize(
    ("origin", "written_as"),
    [
        ("https://app.example.in/", "https://app.example.in"),
        ("https://app.example.in/dashboard", "https://app.example.in"),
        ("https://App.Example.in", "https://app.example.in"),
        ("https://app.example.in:443", "https://app.example.in"),
        ("https://user@app.example.in", "https://app.example.in"),
        ("https://app.example.in?x=1", "https://app.example.in"),
    ],
)
def test_a_near_miss_origin_is_refused_with_the_form_to_use(origin, written_as):
    """The CORS check compares exactly, so these would silently never match.
    The error names the exact text to write instead."""
    with pytest.raises(ValidationError) as exc_info:
        load(cors_allowed_origins=origin)

    assert f"exactly as a browser sends it: {written_as}" in str(exc_info.value)


def test_one_bad_origin_refuses_the_whole_list():
    assert_rejected(
        "cors_allowed_origins",
        cors_allowed_origins="https://good.example.in,https://bad.example.in/",
    )


def test_a_wildcard_is_refused_with_its_own_reason():
    """`*` would allow every website on the internet (security.md section 7)."""
    with pytest.raises(ValidationError) as exc_info:
        load(cors_allowed_origins="*")

    assert "list each website instead" in str(exc_info.value)


# --- .env.example (backend.md section 8) ---------------------------------


def env_example_values() -> dict[str, str]:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    pairs = (line.split("=", 1) for line in lines if "=" in line and line[0] != "#")
    return {name.strip(): value.strip() for name, value in pairs}


def test_every_setting_is_listed_in_env_example():
    """A new setting nobody can find is a setting nobody sets."""
    listed = set(env_example_values())

    assert {name.upper() for name in Settings.model_fields} <= listed


def test_the_example_values_load():
    """Copying .env.example must give a working app once the two keys are
    generated, which the placeholders deliberately force."""
    values = {name.lower(): value for name, value in env_example_values().items()}
    values["secret_key"] = secrets.token_urlsafe(32)
    values["otp_hash_key"] = secrets.token_urlsafe(32)

    settings = Settings(_env_file=None, **values)

    assert settings.environment == "local"
    assert settings.cors_origins == ()
