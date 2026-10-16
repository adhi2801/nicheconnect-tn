"""Authenticator secrets encrypted at rest (item 101, D-105).

A code can only be checked with the secret itself, so it cannot be hashed
the way a ticket is. It is encrypted instead, with AES-256-GCM, under a key
derived from SECOND_FACTOR_KEY: a copy of the database alone, a backup or a
leaked dump, yields no admin's secret. NIST SP 800-63B-4 section 3.1.4.2
asks for exactly that protection of a verifier's stored keys.

The account's id is bound in as associated data, so a secret copied onto
another account's row does not decrypt: one admin's authenticator never
opens another's account.
"""

import secrets
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

NONCE_BYTES = 12
# Changing this voids every stored secret, like rotating the key.
KEY_PURPOSE = b"nicheconnect totp secret v1"


def _cipher() -> AESGCM:
    # HKDF turns the setting, a long random string, into exactly the 32
    # bytes AES-256 needs, bound to this one purpose.
    key = HKDF(algorithm=SHA256(), length=32, salt=None, info=KEY_PURPOSE).derive(
        settings.second_factor_key.get_secret_value().encode()
    )
    return AESGCM(key)


def _context(account_id: uuid.UUID) -> bytes:
    return KEY_PURPOSE + account_id.bytes


def seal(secret: bytes, account_id: uuid.UUID) -> bytes:
    """The secret encrypted for this account: a fresh nonce, then the ciphertext."""
    # Random per seal: a nonce must never repeat under one key.
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce + _cipher().encrypt(nonce, secret, _context(account_id))


def unseal(sealed: bytes, account_id: uuid.UUID) -> bytes | None:
    """The secret, or None if it was not sealed for this account under this key."""
    nonce, ciphertext = sealed[:NONCE_BYTES], sealed[NONCE_BYTES:]
    try:
        return _cipher().decrypt(nonce, ciphertext, _context(account_id))
    except InvalidTag:
        return None
