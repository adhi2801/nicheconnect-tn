import secrets
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings


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
