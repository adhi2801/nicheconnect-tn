"""Matching a team invite to a phone number without keeping the number (item 13, D-148).

An invite keeps only HMAC-SHA256 of the invited number, keyed by
OTP_HASH_KEY under its own label, as assistants' tokens are
(`auth.agent_tokens`): the person was never asked, so their number is not
stored. When that number signs in as a brand, its hash finds the invite.
"""

import hashlib
import hmac

from app.core.config import settings


def hash_invited_phone(phone: str) -> str:
    """The keyed hash of an E.164 number, as stored in brand_invite.phone_hash."""
    key = settings.otp_hash_key.get_secret_value().encode()
    return hmac.new(key, b"team-invite\x00" + phone.encode(), hashlib.sha256).hexdigest()
