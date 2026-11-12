"""The rules of a direct offer that need no database (D-189).

Pure functions of their inputs, so each is tested on every branch without a
database (testing.md section 3) and mutated nightly (D-091): the link's
token and its keyed hash, the number's keyed hash, what an offer shows as
now, whether its due date may be agreed, and the two ceilings' arithmetic.

**The link's token** is 256 random bits, shown to the creator once, in the
answer that sends the offer, for them to send the brand; only its HMAC is
kept, keyed by OTP_HASH_KEY under its own label, as assistants' tokens are
(D-138; OWASP ASVS 5.0 V7.2.3, a reference token of at least 128 bits of
entropy, read 12 November 2026). It travels in the `Offer-Token` header,
never in a path or a query string, which the access log would keep
(backend.md section 9); the website reads it from its link's fragment,
which a browser never sends to any server.
"""

import hashlib
import hmac
import math
import re
import secrets
from datetime import date, datetime, timedelta

from app.core.clock import end_of_india_day, india_date
from app.core.config import settings

LINK_TOKEN_BYTES = 32
# `secrets.token_urlsafe(32)`: 43 characters of the URL-safe alphabet.
LINK_TOKEN_PATTERN = r"^[A-Za-z0-9_-]{43}$"  # noqa: S105 - a format check, not a secret
_LINK_TOKEN = re.compile(LINK_TOKEN_PATTERN)

# Abuse limits (D-189): a creator's offers in one Tamil Nadu day, and the
# offers one number may receive, from anyone, in any 7 days.
DAILY_OFFERS_PER_CREATOR = 10
WEEKLY_OFFERS_PER_NUMBER = 3
NUMBER_WINDOW = timedelta(days=7)
# A due date further ahead than a year is a typing mistake, not a plan; it
# also bounds a value a person types (the standards' checklist).
MAX_DUE_AHEAD = timedelta(days=365)


def new_link_token() -> str:
    """A fresh link token, shown to the creator once and never stored."""
    return secrets.token_urlsafe(LINK_TOKEN_BYTES)


def is_link_token(value: str) -> bool:
    """Whether `value` has a link token's shape; anything else finds nothing."""
    return _LINK_TOKEN.fullmatch(value) is not None


def _keyed(label: bytes, value: str) -> str:
    key = settings.otp_hash_key.get_secret_value().encode()
    return hmac.new(key, label + b"\x00" + value.encode(), hashlib.sha256).hexdigest()


def hash_link_token(token: str) -> str:
    """HMAC-SHA256 hex of a link token, as stored in direct_offer.token_hash."""
    return _keyed(b"direct-offer-link", token)


def hash_recipient_phone(phone: str) -> str:
    """HMAC-SHA256 hex of an E.164 number, as stored in recipient_phone_hash.

    Its own label, so it matches no other hash of the same number we keep
    (a team invite's, D-148).
    """
    return _keyed(b"direct-offer-phone", phone)


def shown_status(status: str, expires_at: datetime, now: datetime) -> str:
    """What an offer is now: its stored status, or "expired" once its 14 days
    ran out before the job that empties it reached it."""
    if status == "sent" and now >= expires_at:
        return "expired"
    return status


def is_waiting(status: str, expires_at: datetime, now: datetime) -> bool:
    """Whether the brand may still accept it."""
    return shown_status(status, expires_at, now) == "sent"


def due_date_problem(due_on: date, now: datetime) -> str | None:
    """Why `due_on` cannot be offered at `now`, or None.

    "passed" before today in Tamil Nadu (a date behind us is nobody's to
    agree), "too_far" more than a year ahead.
    """
    today = india_date(now)
    if due_on < today:
        return "passed"
    if due_on > today + MAX_DUE_AHEAD:
        return "too_far"
    return None


def start_of_india_day(now: datetime) -> datetime:
    """The first moment of `now`'s Tamil Nadu day, where the daily count starts."""
    return end_of_india_day(india_date(now) - timedelta(days=1))


def seconds_until_tomorrow(now: datetime) -> int:
    """Whole seconds until the next Tamil Nadu day begins, at least 1."""
    return max(1, math.ceil((end_of_india_day(india_date(now)) - now).total_seconds()))


def seconds_until_number_frees(oldest_in_window: datetime, now: datetime) -> int:
    """Whole seconds until the oldest of a number's week of offers leaves it."""
    return max(1, math.ceil((oldest_in_window + NUMBER_WINDOW - now).total_seconds()))
