"""Platform tokens sealed at rest (item 29, D-134)."""

import uuid

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.modules.profiles import connection_secrets as vault

KEY = "test-platform-token-key-not-a-secret"


@pytest.fixture(autouse=True)
def key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "platform_token_key", SecretStr(KEY))


def context() -> bytes:
    return b"access:" + uuid.uuid4().bytes + b"instagram"


def test_a_token_comes_back_for_its_own_context():
    where = context()
    sealed = vault.seal("the-token", where)

    assert b"the-token" not in sealed
    assert vault.unseal(sealed, where) == "the-token"


def test_two_seals_of_one_token_differ():
    where = context()

    assert vault.seal("the-token", where) != vault.seal("the-token", where)


def test_a_token_moved_to_another_row_does_not_open():
    sealed = vault.seal("the-token", context())

    assert vault.unseal(sealed, context()) is None


def test_another_key_does_not_open_it(monkeypatch):
    where = context()
    sealed = vault.seal("the-token", where)
    monkeypatch.setattr(settings, "platform_token_key", SecretStr(KEY + "-rotated"))

    assert vault.unseal(sealed, where) is None


def test_the_authenticator_key_does_not_open_it(monkeypatch):
    """Its own key and purpose: SECOND_FACTOR_KEY's value opens nothing here."""
    where = context()
    sealed = vault.seal("the-token", where)
    monkeypatch.setattr(settings, "platform_token_key", settings.second_factor_key)

    assert vault.unseal(sealed, where) is None


def test_without_a_key_nothing_is_sealed(monkeypatch):
    monkeypatch.setattr(settings, "platform_token_key", None)

    with pytest.raises(vault.TokenKeyMissing):
        vault.seal("the-token", context())
