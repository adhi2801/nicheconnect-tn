"""Builders for valid test objects. Contact details are obviously fake."""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from itertools import count
from typing import Any

from sqlalchemy.orm import Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession, refresh_token_ttl
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign
from app.modules.auth.models.otp_challenge import OTP_TTL, OtpChallenge

_sequence = count(1)
TEST_OTP_HASH_KEY = b"test-only-otp-hash-key"
FIXED_NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def fake_phone() -> str:
    """A unique, valid-format Indian mobile number reserved for tests."""
    return f"+9199999{next(_sequence):05d}"


def create_account(db: Session, role: str, **overrides: Any) -> Account:
    """Save an account and return it, so profiles can link to its id."""
    fields: dict[str, Any] = {"phone": fake_phone(), "role": role}
    fields.update(overrides)
    account = Account(**fields)
    db.add(account)
    db.flush()
    return account


def build_brand(db: Session, **overrides: Any) -> Brand:
    """Return an unsaved brand linked to a newly saved brand account."""
    fields: dict[str, Any] = {"name": "Acme", "email": "acme@example.com"}
    fields.update(overrides)
    fields.setdefault("account_id", create_account(db, "brand").id)
    return Brand(**fields)


def build_creator(db: Session, **overrides: Any) -> Creator:
    """Return an unsaved creator linked to a newly saved creator account."""
    fields: dict[str, Any] = {
        "display_name": "Priya Eats",
        "handle": "priya.eats",
        "city": "Coimbatore",
        "niches": ["food", "travel"],
        "languages": ["en"],
        "bio": "Street food across Tamil Nadu.",
    }
    fields.update(overrides)
    fields.setdefault("account_id", create_account(db, "creator").id)
    return Creator(**fields)


def fake_code_hash(code: str = "123456") -> str:
    """HMAC-SHA256 of a code with a test-only key, as the service will store it."""
    return hmac.new(TEST_OTP_HASH_KEY, code.encode(), hashlib.sha256).hexdigest()


def build_otp_challenge(**overrides: Any) -> OtpChallenge:
    """Return an unsaved, unexpired-looking OTP challenge for a fake phone."""
    fields: dict[str, Any] = {
        "phone": fake_phone(),
        "code_hash": fake_code_hash(),
        "expires_at": FIXED_NOW + OTP_TTL,
    }
    fields.update(overrides)
    return OtpChallenge(**fields)


def fake_token_hash() -> str:
    """SHA-256 of a fresh random refresh token, as the service will store it."""
    return hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()


def build_auth_session(db: Session, **overrides: Any) -> AuthSession:
    """Return an unsaved session linked to a newly saved creator account."""
    fields: dict[str, Any] = {
        "family_id": uuid.uuid4(),
        "token_hash": fake_token_hash(),
        "expires_at": FIXED_NOW + refresh_token_ttl(),
    }
    fields.update(overrides)
    fields.setdefault("account_id", create_account(db, "creator").id)
    return AuthSession(**fields)

def build_campaign(db: Session, **overrides: Any) -> Campaign:
    """Return an unsaved paid campaign owned by a newly saved brand."""
    fields: dict[str, Any] = {
        "title": "Pongal sweets launch",
        "description": "Three reels featuring our new sweet box.",
        "campaign_type": "paid",
        "budget_min_paise": 500_000,
        "budget_max_paise": 1_500_000,
        "cities": ["Madurai", "Coimbatore"],
        "niches": ["food"],
        "deliverables": "3 Instagram reels, 1 story set.",
        "status": "open",
    }
    fields.update(overrides)
    if "brand_id" not in fields:
        brand = build_brand(db)
        db.add(brand)
        db.flush()
        fields["brand_id"] = brand.id
    return Campaign(**fields)
