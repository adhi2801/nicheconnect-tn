"""Access tokens, refresh tokens and one-time codes (D-008, D-013).

Pure functions: callers pass `now`, so expiry is testable without waiting.
"""

import hashlib
import hmac
import math
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings
from app.modules.auth.exceptions import InvalidToken
from app.modules.auth.models.account import ACCOUNT_ROLES

ALGORITHM = "HS256"
# Key ID in the token header, so the signing key can be rotated later.
CURRENT_KEY_ID = "k1"
ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - a claim value, not a secret
OTP_CODE_DIGITS = 6
REFRESH_TOKEN_BYTES = 32

# How the login behind a token was proven, as RFC 8176's registered
# "Authentication Method Reference" values: `otp`, a one-time code (the
# phone's); `mfa`, more than one factor (D-105). Admin routes refuse a token
# without `mfa`, so no admin session can come from the phone code alone.
PHONE_CODE_ONLY: tuple[str, ...] = ("otp",)
TWO_FACTORS: tuple[str, ...] = ("mfa", "otp")
# A passkey (D-113): proof of possession of a key (`pop`), with the person
# checked by the phone's own lock (`user`).
PASSKEY: tuple[str, ...] = ("pop", "user")
MULTI_FACTOR = "mfa"
KNOWN_METHODS = frozenset(TWO_FACTORS) | frozenset(PASSKEY)


@dataclass(frozen=True)
class AccessTokenClaims:
    account_id: uuid.UUID
    role: str
    expires_at: datetime
    # RFC 8176 values. Empty for a token signed before D-105.
    methods: tuple[str, ...] = ()
    # When the person last proved a code to log in: OpenID Connect's
    # `auth_time`, kept through every refresh of that login (D-109). None
    # for a token signed before it, which counts as a login made just now.
    authenticated_at: datetime | None = None

    @property
    def is_multi_factor(self) -> bool:
        return MULTI_FACTOR in self.methods


def create_access_token(
    account_id: uuid.UUID,
    role: str,
    now: datetime,
    *,
    methods: tuple[str, ...] = PHONE_CODE_ONLY,
    not_after: datetime | None = None,
    authenticated_at: datetime | None = None,
) -> tuple[str, datetime]:
    """Sign a short-lived access token. Returns the token and its expiry time.

    `not_after` ends it sooner, so a session's own limit binds its last
    access token too (an admin's 12 hours, D-105). `authenticated_at` is
    when its login was proven, signed as `auth_time` (D-109).
    """
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    if not_after is not None:
        expires_at = min(expires_at, not_after)
    claims = {
        "sub": str(account_id),
        "role": role,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
        "amr": list(methods),
    }
    if authenticated_at is not None:
        # Rounded up, so a login never reads as older than it is.
        claims["auth_time"] = math.ceil(authenticated_at.timestamp())
    token = jwt.encode(
        claims,
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": CURRENT_KEY_ID},
    )
    return token, expires_at


def _verified_claims(token: str) -> dict[str, Any]:
    """Check a token's signature and shape. Expiry is the caller's business.

    Split out so that scoping (which does not care whether the token has
    just lapsed) and authentication (which very much does) share one piece
    of verification rather than two that could drift apart.
    """
    try:
        if jwt.get_unverified_header(token).get("kid") != CURRENT_KEY_ID:
            raise InvalidToken()
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            # Expiry is checked below against the caller's clock, which is the
            # single source of time here. PyJWT's own exp and iat checks use
            # the machine clock, so they are off: with them on, a token issued
            # a moment "ahead" of the machine (clock skew, or a test clock) is
            # refused even though our rules accept it.
            options={
                "verify_exp": False,
                "verify_iat": False,
                "require": ["sub", "role", "typ", "iat", "exp", "jti"],
            },
        )
        uuid.UUID(claims["sub"])
        datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidToken() from exc

    if claims["typ"] != ACCESS_TOKEN_TYPE or claims["role"] not in ACCOUNT_ROLES:
        raise InvalidToken()
    # Optional, so tokens signed before D-105 still decode (as one factor).
    methods = claims.get("amr", [])
    if not isinstance(methods, list) or not all(
        isinstance(method, str) and method in KNOWN_METHODS for method in methods
    ):
        raise InvalidToken()
    # Optional for the same reason (D-109); an integer when present.
    if "auth_time" in claims and (
        isinstance(claims["auth_time"], bool) or not isinstance(claims["auth_time"], int)
    ):
        raise InvalidToken()
    return claims


def decode_access_token(token: str, now: datetime) -> AccessTokenClaims:
    """Verify an access token and return its claims.

    Raises InvalidToken for any problem (bad signature, wrong key ID, wrong
    type, unknown role, malformed claims, or expired at `now`).
    """
    claims = _verified_claims(token)
    expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
    if now >= expires_at:
        raise InvalidToken()
    return AccessTokenClaims(
        account_id=uuid.UUID(claims["sub"]),
        role=claims["role"],
        expires_at=expires_at,
        methods=tuple(claims.get("amr", [])),
        authenticated_at=(
            datetime.fromtimestamp(claims["auth_time"], tz=UTC)
            if "auth_time" in claims
            else None
        ),
    )


def account_id_for_scoping(token: str) -> uuid.UUID | None:
    """Which account a token belongs to, for grouping retries of one request.

    The signature is verified, so this cannot be forged into somebody else's
    bucket. Expiry deliberately is not: a retry arriving just after a token
    lapsed, or after the client refreshed it, is still the same person
    retrying the same request, and should still get their first answer.

    Never use this to decide access. It answers "whose request is this",
    not "may they do it" — `decode_access_token` answers that.
    """
    try:
        return uuid.UUID(_verified_claims(token)["sub"])
    except InvalidToken:
        return None


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
