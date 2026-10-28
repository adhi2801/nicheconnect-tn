"""Platform tokens encrypted at rest (item 29, D-134).

An access token reads a creator's account at the platform, so it is held
the way an admin's authenticator secret is (`auth.second_factor_secrets`):
AES-256-GCM under a key derived from PLATFORM_TOKEN_KEY, its own key and
purpose, so neither key opens the other's rows. What a token belongs to is
bound in as associated data: a token copied onto another creator's row, or
another platform's, does not decrypt. A copy of the database alone, a
backup or a leaked dump, yields no token.
"""

import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

NONCE_BYTES = 12
# Changing this voids every stored token, like rotating the key.
KEY_PURPOSE = b"nicheconnect platform token v1"


class TokenKeyMissing(RuntimeError):
    """PLATFORM_TOKEN_KEY is unset: connections are switched off (D-134)."""


def _cipher() -> AESGCM:
    if settings.platform_token_key is None:
        raise TokenKeyMissing()
    key = HKDF(algorithm=SHA256(), length=32, salt=None, info=KEY_PURPOSE).derive(
        settings.platform_token_key.get_secret_value().encode()
    )
    return AESGCM(key)


def seal(value: str, context: bytes) -> bytes:
    """The value encrypted for this context: a fresh nonce, then the ciphertext."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce + _cipher().encrypt(nonce, value.encode(), KEY_PURPOSE + context)


def unseal(sealed: bytes, context: bytes) -> str | None:
    """The value, or None if it was not sealed for this context under this key."""
    nonce, ciphertext = sealed[:NONCE_BYTES], sealed[NONCE_BYTES:]
    try:
        return _cipher().decrypt(nonce, ciphertext, KEY_PURPOSE + context).decode()
    except InvalidTag:
        return None
