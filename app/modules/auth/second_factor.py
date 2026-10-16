"""Authenticator-app codes and setup tickets, as pure rules (item 101, D-105).

The codes are RFC 6238's: HMAC-SHA1 over the number of 30-second steps
since 1970, cut to 6 digits, which every authenticator app shows by default
(pyotp computes them). The clock is always the server's, passed in (ASVS 5.0
6.5.8): never the client's.

**Which codes are accepted.** The current step's, and the one before it, for
the seconds it takes to read and type a code (NIST SP 800-63B-4 section
3.1.4.2 lets the lifetime cover entry time and drift); never a future step's.
**Each step is accepted once** (ASVS 5.0 6.5.1): a code is refused when its
step is not later than the last one accepted, so neither a replay nor an
older code that is still in the window gets in.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime

import pyotp

from app.modules.auth.models.totp_factor import SECRET_BYTES

PERIOD_SECONDS = 30
DIGITS = 6
# The issuer an authenticator app shows beside the code.
ISSUER = "NicheConnect TN"
# 192 bits: far past what can be guessed, and above ASVS 5.0 6.5.2's 112, so
# a plain SHA-256 of it is enough to store.
TICKET_BYTES = 24


def new_secret() -> bytes:
    """A new 160-bit secret from the operating system's CSPRNG (ASVS 5.0 6.5.3)."""
    return secrets.token_bytes(SECRET_BYTES)


def secret_text(secret: bytes) -> str:
    """The secret as an authenticator app takes it typed in: base32, no padding."""
    return base64.b32encode(secret).decode().rstrip("=")


def step_at(now: datetime) -> int:
    """Which 30-second step `now` falls in."""
    return int(now.timestamp()) // PERIOD_SECONDS


def code_at_step(secret: bytes, step: int) -> str:
    """The code an authenticator app shows during `step`.

    Straight from the step's number (RFC 6238's T), never through a date:
    pyotp's `at()` makes one, which fails on Windows for far-off steps.
    """
    totp = pyotp.TOTP(secret_text(secret), digits=DIGITS, interval=PERIOD_SECONDS)
    return totp.generate_otp(step)


def accepted_step(
    secret: bytes, code: str, now: datetime, last_used_step: int | None
) -> int | None:
    """The step `code` belongs to, if it may be accepted now; otherwise None.

    Only the current step and the one before count, and only a step later
    than `last_used_step`, so each code works once.
    """
    current = step_at(now)
    for step in (current, current - 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(code_at_step(secret, step), code):
            return step
    return None


def setup_link(secret: bytes, label: str) -> str:
    """The otpauth:// link an authenticator app reads from a QR code."""
    totp = pyotp.TOTP(secret_text(secret), digits=DIGITS, interval=PERIOD_SECONDS)
    return totp.provisioning_uri(name=label, issuer_name=ISSUER)


def new_ticket() -> str:
    """A setup ticket, shown to a founder once and stored only as its hash."""
    return secrets.token_urlsafe(TICKET_BYTES)


def hash_ticket(ticket: str) -> str:
    """SHA-256 hex of a ticket, as stored in totp_factor.ticket_hash."""
    return hashlib.sha256(ticket.encode()).hexdigest()
