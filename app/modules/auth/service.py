"""OTP login rules (D-007, D-008, D-011, D-013).

Each public function is one unit of work and commits once. Callers pass `now`
from an injectable clock so expiry and limits are testable.
"""

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.exceptions import OtpInvalid, OtpSendLimitReached, RoleMismatch
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.otp_challenge import MAX_OTP_ATTEMPTS, OTP_TTL, OtpChallenge
from app.modules.auth.sender import OtpSender
from app.modules.auth.tokens import (
    create_access_token,
    generate_otp_code,
    hash_otp_code,
    hash_refresh_token,
    new_refresh_token,
    otp_code_matches,
)

logger = logging.getLogger(__name__)

# Per-phone send limits (security.md section 4): (window, max codes in window).
OTP_SEND_LIMITS: tuple[tuple[timedelta, int], ...] = (
    (timedelta(minutes=10), 3),
    (timedelta(days=1), 10),
)


@dataclass(frozen=True)
class PendingOtp:
    """A code to deliver after the transaction commits."""

    phone: str
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class LoginResult:
    account_id: uuid.UUID
    role: str
    is_new_account: bool
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str
    refresh_token_expires_at: datetime


def _lock_phone(db: Session, phone: str) -> None:
    """Serialize OTP work per phone until the transaction ends.

    Stops two concurrent requests from both passing a limit or both creating
    an account for the same number.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"otp:{phone}"},
    )


def _seconds_until_send_allowed(db: Session, phone: str, now: datetime) -> int:
    """0 if a code may be sent now, otherwise whole seconds until one may."""
    wait = 0
    for window, max_codes in OTP_SEND_LIMITS:
        sent_at = db.scalars(
            select(OtpChallenge.created_at)
            .where(OtpChallenge.phone == phone, OtpChallenge.created_at > now - window)
            .order_by(OtpChallenge.created_at)
        ).all()
        if len(sent_at) >= max_codes:
            # The window reopens when enough of the oldest codes fall out of it.
            reopens_at = sent_at[len(sent_at) - max_codes] + window
            wait = max(wait, math.ceil((reopens_at - now).total_seconds()))
    return wait


def request_otp(db: Session, phone: str, now: datetime) -> PendingOtp:
    """Create a one-time code for `phone` and return it for delivery.

    Behaves the same whether or not the phone has an account.
    Raises OtpSendLimitReached if a per-phone send limit is reached.
    """
    _lock_phone(db, phone)
    retry_after = _seconds_until_send_allowed(db, phone, now)
    if retry_after > 0:
        db.rollback()
        raise OtpSendLimitReached(headers={"Retry-After": str(retry_after)})

    code = generate_otp_code()
    challenge = OtpChallenge(
        phone=phone,
        code_hash=hash_otp_code(code),
        expires_at=now + OTP_TTL,
        # Set from the same clock the limits use.
        created_at=now,
        updated_at=now,
    )
    db.add(challenge)
    db.commit()
    return PendingOtp(phone=phone, code=code, expires_at=challenge.expires_at)


def deliver_otp(sender: OtpSender, pending: PendingOtp) -> None:
    """Send a code after the response. Failures are logged, never raised.

    The user can simply request a new code (D-013). The log line carries no
    phone number or code.
    """
    try:
        sender.send_code(pending.phone, pending.code)
    except Exception:
        logger.exception("otp.send_failed")


def verify_otp(db: Session, phone: str, code: str, role: str, now: datetime) -> LoginResult:
    """Check a code and log the phone in, creating the account if it is new.

    Only the latest code for the phone counts. A wrong code uses up one of
    MAX_OTP_ATTEMPTS attempts.
    Raises OtpInvalid (wrong, expired, used, exhausted or no code) and
    RoleMismatch (the account exists with another role; the code stays usable).
    """
    _lock_phone(db, phone)
    challenge = db.scalars(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone)
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
    ).first()

    if (
        challenge is None
        or challenge.consumed_at is not None
        or now >= challenge.expires_at
        or challenge.attempts >= MAX_OTP_ATTEMPTS
    ):
        db.rollback()
        raise OtpInvalid()

    if not otp_code_matches(code, challenge.code_hash):
        challenge.attempts += 1
        # Commit so the used attempt counts even though the request fails.
        db.commit()
        raise OtpInvalid()

    account = db.scalars(select(Account).where(Account.phone == phone)).first()
    if account is not None and account.role != role:
        db.rollback()
        raise RoleMismatch()

    is_new_account = account is None
    if account is None:
        account = Account(phone=phone, role=role)
        db.add(account)
        db.flush()

    challenge.consumed_at = now
    refresh_token = new_refresh_token()
    refresh_expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    db.add(
        AuthSession(
            account_id=account.id,
            family_id=uuid.uuid4(),
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expires_at,
            created_at=now,
            updated_at=now,
        )
    )
    access_token, access_expires_at = create_access_token(account.id, account.role, now)
    db.commit()

    return LoginResult(
        account_id=account.id,
        role=account.role,
        is_new_account=is_new_account,
        access_token=access_token,
        access_token_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_token_expires_at=refresh_expires_at,
    )
