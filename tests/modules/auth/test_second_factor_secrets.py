"""Authenticator secrets encrypted at rest (item 101, D-105)."""

import uuid

from pydantic import SecretStr

from app.core.config import settings
from app.modules.auth import second_factor_secrets
from app.modules.auth.models.totp_factor import SECRET_BYTES, SECRET_CIPHERTEXT_BYTES

SECRET = bytes(range(SECRET_BYTES))
ACCOUNT = uuid.UUID("0199e2b4-1f0c-7a9b-8c3d-2e4f5a6b7c8d")


def test_a_sealed_secret_opens_for_its_account():
    sealed = second_factor_secrets.seal(SECRET, ACCOUNT)

    assert second_factor_secrets.unseal(sealed, ACCOUNT) == SECRET


def test_the_stored_form_is_the_length_the_database_holds():
    assert len(second_factor_secrets.seal(SECRET, ACCOUNT)) == SECRET_CIPHERTEXT_BYTES


def test_the_secret_itself_is_not_in_what_is_stored():
    assert SECRET not in second_factor_secrets.seal(SECRET, ACCOUNT)


def test_sealing_twice_never_repeats_a_nonce():
    first = second_factor_secrets.seal(SECRET, ACCOUNT)
    second = second_factor_secrets.seal(SECRET, ACCOUNT)

    assert (
        first[: second_factor_secrets.NONCE_BYTES]
        != (second[: second_factor_secrets.NONCE_BYTES])
    )


def test_a_secret_copied_onto_another_account_does_not_open():
    """So one admin's authenticator can never open another's account."""
    sealed = second_factor_secrets.seal(SECRET, ACCOUNT)

    assert second_factor_secrets.unseal(sealed, uuid.uuid4()) is None


def test_a_changed_byte_does_not_open():
    sealed = bytearray(second_factor_secrets.seal(SECRET, ACCOUNT))
    sealed[-1] ^= 1

    assert second_factor_secrets.unseal(bytes(sealed), ACCOUNT) is None


def test_after_the_key_is_rotated_an_old_secret_does_not_open(monkeypatch):
    sealed = second_factor_secrets.seal(SECRET, ACCOUNT)

    monkeypatch.setattr(settings, "second_factor_key", SecretStr("z" * 43))

    assert second_factor_secrets.unseal(sealed, ACCOUNT) is None
