"""Access tokens, refresh tokens and one-time codes (D-008, D-013).

Pure functions: callers pass `now`, so expiry is testable without waiting.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.modules.auth.exceptions import InvalidToken
from app.modules.auth.models.account import ACCOUNT_ROLES

ALGORITHM = "HS256"
# Key ID in the token header, so the signing key can be rotated later.
CURRENT_KEY_ID = "k1"
ACCESS_TOKEN_TYPE = "access"
OTP_CODE_DIGITS = 6
REFRESH_TOKEN_BYTES = 32


@dataclass(frozen=True)
class AccessTokenClaims:
    account_id: uuid.UUID
    role: str
    expires_at: datetime


def create_access_token(account_id: uuid.UUID, role: str, now: datetime) -> tuple[str, datetime]:
    """Sign a short-lived access token. Returns the token and its expiry time."""
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    claims = {
        "sub": str(account_id),
        "role": role,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(
        claims,
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": CURRENT_KEY_ID},
    )
    return token, expires_at


def decode_access_token(token: str, now: datetime) -> AccessTokenClaims:
    """Verify an access token and return its claims.

    Raises InvalidToken for any problem (bad signature, wrong key ID, wrong
    type, unknown role, malformed claims, or expired at `now`).
    """
    try:
        if jwt.get_unverified_header(token).get("kid") != CURRENT_KEY_ID:
            raise InvalidToken()
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            # Expiry is checked below against the caller's clock.
            options={"verify_exp": False, "require": ["sub", "role", "typ", "iat", "exp", "jti"]},
        )
        account_id = uuid.UUID(claims["sub"])
        expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidToken() from exc

    if claims["typ"] != ACCESS_TOKEN_TYPE or claims["role"] not in ACCOUNT_ROLES:
        raise InvalidToken()
    if now >= expires_at:
        raise InvalidToken()
    return AccessTokenClaims(account_id=account_id, role=claims["role"], expires_at=expires_at)


def new_refresh_token() -> str:
    """A fresh random refresh token (shown to the client once, never stored)."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex of a refresh token, as stored in auth_session.token_hash."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_otp_code() -> str:
    """A cryptographically random 6-digit code, e.g. '042917'."""
    return f"{secrets.randbelow(10**OTP_CODE_DIGITS):0{OTP_CODE_DIGITS}d}"


def hash_otp_code(code: str) -> str:
    """HMAC-SHA256 hex of a code, keyed by OTP_HASH_KEY (otp_challenge.code_hash)."""
    key = settings.otp_hash_key.get_secret_value().encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


def otp_code_matches(code: str, code_hash: str) -> bool:
    """Constant-time comparison, so timing reveals nothing about the code."""
    return hmac.compare_digest(hash_otp_code(code), code_hash)
