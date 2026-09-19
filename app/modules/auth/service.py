"""OTP login rules (D-007, D-008, D-011, D-013).

Each public function is one unit of work and commits once. Callers pass `now`
from an injectable clock so expiry and limits are testable.
"""

import logging
import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth.exceptions import (
    InvalidToken,
    OtpInvalid,
    OtpSendLimitReached,
    OtpVerifyLimitReached,
    RoleMismatch,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession, refresh_token_ttl
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

# Per-phone guess limit (security.md section 4): wrong codes allowed for one
# number in a window, counted across all of its codes. The per-code limit
# (MAX_OTP_ATTEMPTS) alone would allow 5 guesses per code, so three codes in
# ten minutes would allow fifteen.
VERIFY_ATTEMPT_WINDOW = timedelta(minutes=10)
MAX_VERIFY_ATTEMPTS_PER_WINDOW = 10

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
    except Exception as exc:
        # Provider errors can echo the phone or code, so never log the
        # exception text or traceback: only the error type.
        logger.error("otp.send_failed error_type=%s", type(exc).__name__)


def _seconds_until_verify_allowed(db: Session, phone: str, now: datetime) -> int:
    """0 if another guess is allowed for this number, else seconds to wait.

    Counts wrong guesses across every code sent to the phone in the window.
    """
    window_start = now - VERIFY_ATTEMPT_WINDOW
    rows = db.execute(
        select(OtpChallenge.created_at, OtpChallenge.attempts).where(
            OtpChallenge.phone == phone, OtpChallenge.created_at > window_start
        )
    ).all()
    used = sum(attempts for _, attempts in rows)
    if used < MAX_VERIFY_ATTEMPTS_PER_WINDOW:
        return 0
    # Free again when the oldest counted code leaves the window.
    oldest = min(created_at for created_at, _ in rows)
    return max(1, math.ceil((oldest + VERIFY_ATTEMPT_WINDOW - now).total_seconds()))


def verify_otp(db: Session, phone: str, code: str, role: str, now: datetime) -> LoginResult:
    """Check a code and log the phone in, creating the account if it is new.

    Only the latest code for the phone counts. A wrong code uses up one of
    MAX_OTP_ATTEMPTS attempts.
    Raises OtpInvalid (wrong, expired, used, exhausted or no code) and
    RoleMismatch (the account exists with another role; the code stays usable).
    """
    _lock_phone(db, phone)
    retry_after = _seconds_until_verify_allowed(db, phone, now)
    if retry_after > 0:
        db.rollback()
        raise OtpVerifyLimitReached(headers={"Retry-After": str(retry_after)})

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
    # A fresh login starts its own rotation family.
    result = _issue_session(db, account, uuid.uuid4(), now)
    db.commit()
    return replace(result, is_new_account=is_new_account)

def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    """End every session in one login's rotation chain."""
    db.execute(
        update(AuthSession)
        .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, updated_at=now)
    )


def _issue_session(
    db: Session, account: Account, family_id: uuid.UUID, now: datetime
) -> LoginResult:
    """Create one session in `family_id` and return its tokens."""
    refresh_token = new_refresh_token()
    refresh_expires_at = now + refresh_token_ttl()
    db.add(
        AuthSession(
            account_id=account.id,
            family_id=family_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expires_at,
            created_at=now,
            updated_at=now,
        )
    )
    access_token, access_expires_at = create_access_token(account.id, account.role, now)
    return LoginResult(
        account_id=account.id,
        role=account.role,
        is_new_account=False,
        access_token=access_token,
        access_token_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_token_expires_at=refresh_expires_at,
    )


def refresh_session(db: Session, refresh_token: str, now: datetime) -> LoginResult:
    """Swap a refresh token for a new pair of tokens (D-008).

    Rotation: the old token is marked used and a new one joins the same family.
    Presenting an already-used token means it was copied, so the whole family
    is revoked and the caller must log in again.
    Raises InvalidToken for unknown, expired, revoked or reused tokens.
    """
    # Locked so two callers cannot rotate the same token at once.
    auth_session = db.scalars(
        select(AuthSession)
        .where(AuthSession.token_hash == hash_refresh_token(refresh_token))
        .with_for_update()
    ).first()

    if auth_session is None:
        db.rollback()
        raise InvalidToken()

    if auth_session.used_at is not None:
        # Token reuse: assume theft and end every session in the family.
        _revoke_family(db, auth_session.family_id, now)
        db.commit()
        logger.warning("auth.refresh_token_reused family_id=%s", auth_session.family_id)
        raise InvalidToken()

    if auth_session.revoked_at is not None or now >= auth_session.expires_at:
        db.rollback()
        raise InvalidToken()

    auth_session.used_at = now
    auth_session.updated_at = now
    account = db.get(Account, auth_session.account_id)
    result = _issue_session(db, account, auth_session.family_id, now)
    db.commit()
    return result


def logout(db: Session, refresh_token: str, now: datetime) -> None:
    """End the login this refresh token belongs to.

    Revokes the whole rotation chain, so older copies stop working too.
    Unknown tokens are ignored: logout always looks the same to the caller.
    """
    auth_session = db.scalars(
        select(AuthSession).where(
            AuthSession.token_hash == hash_refresh_token(refresh_token)
        )
    ).first()
    if auth_session is not None:
        _revoke_family(db, auth_session.family_id, now)
    db.commit()

def logout_all_sessions(db: Session, account_id: uuid.UUID, now: datetime) -> int:
    """End every session of one account. Returns how many were still active."""
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.account_id == account_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, updated_at=now)
    )
    db.commit()
    return result.rowcount
