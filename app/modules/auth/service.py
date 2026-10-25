"""OTP login rules (D-007, D-008, D-011, D-013).

Each public function is one unit of work and commits once. Callers pass `now`
from an injectable clock so expiry and limits are testable.
"""

import logging
import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, NoReturn, cast

from sqlalchemy import CursorResult, func, select, text, union_all, update
from sqlalchemy.orm import Session

from app.modules.auth import attribution_service as attribution
from app.modules.auth import device_service as devices
from app.modules.auth import phone_changes
from app.modules.auth.attribution_service import Arrival
from app.modules.auth.exceptions import (
    AccountSuspended,
    InvalidToken,
    OtpInvalid,
    OtpSendLimitReached,
    OtpVerifyLimitReached,
    PasskeyOnly,
    PhoneChangeWaiting,
    RoleMismatch,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession, refresh_token_expiry
from app.modules.auth.models.otp_challenge import MAX_OTP_ATTEMPTS, OTP_TTL, OtpChallenge
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.auth.sender import OtpSender
from app.modules.auth.tokens import (
    PASSKEY,
    PHONE_CODE_ONLY,
    TWO_FACTORS,
    create_access_token,
    generate_otp_code,
    hash_otp_code,
    hash_refresh_token,
    new_refresh_token,
    otp_code_matches,
)

logger = logging.getLogger(__name__)

# Per-phone guess limit (security.md section 1): wrong codes allowed for one
# number in a window, counted across all of its codes. The per-code limit
# (MAX_OTP_ATTEMPTS) alone would allow 5 guesses per code, so three codes in
# ten minutes would allow fifteen.
VERIFY_ATTEMPT_WINDOW = timedelta(minutes=10)
MAX_VERIFY_ATTEMPTS_PER_WINDOW = 10

# Per-phone send limits (security.md section 1): (window, max codes in window).
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


@dataclass(frozen=True)
class ClientDevice:
    """What the app said it is, at sign-in (D-114). Never checked, only shown."""

    platform: str
    label: str


def phone_of(account: Account) -> str:
    """The number an account logs in with. Raises InvalidToken for a deleted one.

    Only a deleted account has none (D-122), and a deleted account has no
    session, so no request reaches here for one; this says so rather than
    assume it.
    """
    if account.phone is None:
        raise InvalidToken()
    return account.phone


def lock_phone(db: Session, phone: str) -> None:
    """Serialize OTP work per phone until the transaction ends.

    Stops two concurrent requests from both passing a limit or both creating
    an account for the same number.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"otp:{phone}"},
    )


def lock_phones(db: Session, *phones: str) -> None:
    """`lock_phone` for several numbers, always in sorted order.

    Work that touches two numbers (a phone number change, item 80) takes
    both. Sorted, so two transactions locking the same two numbers take them
    in the same order and can never wait on each other in a circle; taking a
    lock already held in this transaction returns at once.
    """
    for phone in sorted(set(phones)):
        lock_phone(db, phone)


def codes_for_phone(
    db: Session, phone: str, since: datetime, *, sent_only: bool = False
) -> list[tuple[datetime, int]]:
    """Every code for `phone` after `since`, with the wrong tries each used.

    Login codes and step-up codes (item 82) together, so the caps on sending
    and guessing are one budget per phone: asking for step-up codes buys no
    extra messages and no extra guesses. `sent_only` leaves out grants a
    passkey earned (D-113), which no message carried; their wrong tries
    still count.
    """
    login_codes = select(OtpChallenge.created_at, OtpChallenge.attempts).where(
        OtpChallenge.phone == phone, OtpChallenge.created_at > since
    )
    step_up_codes = (
        select(StepUpChallenge.created_at, StepUpChallenge.attempts)
        .join(Account, Account.id == StepUpChallenge.account_id)
        .where(Account.phone == phone, StepUpChallenge.created_at > since)
    )
    if sent_only:
        step_up_codes = step_up_codes.where(StepUpChallenge.method == "phone_code")
    return [
        (created_at, attempts)
        for created_at, attempts in db.execute(union_all(login_codes, step_up_codes))
    ]


def seconds_until_send_allowed(db: Session, phone: str, now: datetime) -> int:
    """0 if a code may be sent now, otherwise whole seconds until one may."""
    longest = max(window for window, _ in OTP_SEND_LIMITS)
    sent = sorted(
        created_at
        for created_at, _ in codes_for_phone(db, phone, now - longest, sent_only=True)
    )
    wait = 0
    for window, max_codes in OTP_SEND_LIMITS:
        sent_at = [created_at for created_at in sent if created_at > now - window]
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
    lock_phone(db, phone)
    retry_after = seconds_until_send_allowed(db, phone, now)
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


def seconds_until_verify_allowed(db: Session, phone: str, now: datetime) -> int:
    """0 if another guess is allowed for this number, else seconds to wait.

    Counts wrong guesses across every code sent to the phone in the window,
    step-up codes included.
    """
    rows = codes_for_phone(db, phone, now - VERIFY_ATTEMPT_WINDOW)
    used = sum(attempts for _, attempts in rows)
    if used < MAX_VERIFY_ATTEMPTS_PER_WINDOW:
        return 0
    # Free again when the oldest counted code leaves the window.
    oldest = min(created_at for created_at, _ in rows)
    return max(1, math.ceil((oldest + VERIFY_ATTEMPT_WINDOW - now).total_seconds()))


def verify_otp(
    db: Session,
    phone: str,
    code: str,
    role: str,
    now: datetime,
    arrival: Arrival | None = None,
    device: ClientDevice | None = None,
) -> LoginResult:
    """Check a code and log the phone in, creating the account if it is new.

    Only the latest code for the phone counts. A wrong code uses up one of
    MAX_OTP_ATTEMPTS attempts. `device` is what the app said it is (D-114).
    Raises OtpInvalid (wrong, expired, used, exhausted or no code),
    RoleMismatch (the account exists with another role) and
    PhoneChangeWaiting (no account has the number, but one is waiting to
    move onto it, item 80); for both of those the code stays usable.
    """
    challenge = check_phone_code(db, phone, code, now)

    if role == "admin":
        # An admin logs in with two factors, at /auth/admin/login (D-105);
        # here, never. Login never creates an admin either, and must not
        # reveal who is one: so for anyone, admin or not, this is answered
        # exactly as a wrong code, attempt used and all (D-061).
        refuse_phone_code(db, challenge)
    account = db.scalars(select(Account).where(Account.phone == phone)).first()
    if account is None and phone_changes.is_waiting_to_move(db, phone):
        # A new account here would take the number from under the change.
        db.rollback()
        raise PhoneChangeWaiting()
    if account is not None and account.role != role:
        db.rollback()
        raise RoleMismatch()
    if account is not None and account.suspended_at is not None:
        # The code is right, so the person is told; it stays unused (D-061).
        db.rollback()
        raise AccountSuspended.because(account.suspension_reason)
    if account is not None and account.passkey_only:
        # A phone code no longer logs this account in (D-113). The code stays
        # unused, so the same one can start a passkey reset.
        db.rollback()
        raise PasskeyOnly()

    is_new_account = account is None
    if account is None:
        account = Account(phone=phone, role=role)
        db.add(account)
        db.flush()
        # How they arrived, in this same transaction, and only now: a
        # returning login never gets here, so it cannot rewrite it (D-080).
        attribution.record_arrival(db, account, arrival, now)

    challenge.consumed_at = now
    # A fresh login starts its own rotation family.
    result = issue_session(db, account, uuid.uuid4(), now, device=device)
    db.commit()
    return replace(result, is_new_account=is_new_account)


def check_phone_code(db: Session, phone: str, code: str, now: datetime) -> OtpChallenge:
    """The phone's latest challenge, if `code` is right for it. The caller commits.

    Locks the phone for the rest of the transaction, so the same number's
    logins run one at a time. A wrong code uses up an attempt, committed here
    since the request then fails.
    Raises OtpVerifyLimitReached (too many wrong tries for this phone) and
    OtpInvalid (wrong, expired, used, exhausted or no code).
    """
    lock_phone(db, phone)
    retry_after = seconds_until_verify_allowed(db, phone, now)
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
        refuse_phone_code(db, challenge)
    return challenge


def refuse_phone_code(db: Session, challenge: OtpChallenge) -> NoReturn:
    """Answer exactly as a wrong code: an attempt used, committed, OtpInvalid."""
    count_failed_attempt(challenge)
    db.commit()
    raise OtpInvalid()


def count_failed_attempt(challenge: OtpChallenge) -> None:
    """Use up one of the code's attempts, as a wrong code does. The caller commits."""
    challenge.attempts += 1


def lock_sessions_of(db: Session, account_id: uuid.UUID) -> None:
    """Hold the account's sessions still until the transaction ends (D-114).

    Every refresh and every way of ending a session takes this lock first,
    so they run one at a time per account. Without it, a refresh holding its
    token's row while a logout waited on it would add the session's next row
    after the logout's statement began, and read committed isolation would
    hide that row from the logout: the logged-out phone kept a working
    session. `FOR NO KEY UPDATE` on the account row, so rows that only point
    at the account (a new session's own foreign key) are never held up by it.
    """
    db.execute(
        select(Account.id).where(Account.id == account_id).with_for_update(key_share=True)
    )


def end_sessions(
    db: Session,
    account_id: uuid.UUID,
    now: datetime,
    *,
    family_id: uuid.UUID | None = None,
) -> int:
    """End the account's sessions, or one login's (`family_id`). The caller commits.

    Returns how many rows were still active. Locks first (`lock_sessions_of`),
    so the update, a statement of its own, sees any row a refresh added while
    it waited. The phones those sessions registered for push are forgotten
    with them (D-116), so a phone logged out from elsewhere is told nothing
    more.
    """
    lock_sessions_of(db, account_id)
    statement = update(AuthSession).where(
        AuthSession.account_id == account_id, AuthSession.revoked_at.is_(None)
    )
    if family_id is not None:
        statement = statement.where(AuthSession.family_id == family_id)
    # SQLAlchemy types Session.execute() as Result[Any], which has no rowcount.
    # An UPDATE returns a CursorResult at runtime, and that is where rowcount
    # lives; the cast is type-checker-only and emits no runtime code.
    result = cast(
        "CursorResult[Any]", db.execute(statement.values(revoked_at=now, updated_at=now))
    )
    devices.forget_session(db, account_id, family_id)
    return result.rowcount


def _revoke_family(db: Session, auth_session: AuthSession, now: datetime) -> None:
    """End every session in one login's rotation chain."""
    end_sessions(db, auth_session.account_id, now, family_id=auth_session.family_id)


def issue_session(
    db: Session,
    account: Account,
    family_id: uuid.UUID,
    now: datetime,
    *,
    second_factor_at: datetime | None = None,
    authenticated_at: datetime | None = None,
    passkey_at: datetime | None = None,
    device: ClientDevice | None = None,
    sign_in_acknowledged_at: datetime | None = None,
) -> LoginResult:
    """Create one session in `family_id` and return its tokens. The caller commits.

    `second_factor_at` is when the login proved a second factor; it is kept
    on every session of the family, and makes its access tokens say `mfa`.
    `authenticated_at` is when the family's login was proven, `now` for a
    new login; its access tokens carry it as `auth_time` (D-109).
    `passkey_at` is when a passkey proved the login, kept on every session
    of the family, and makes its access tokens say so (D-113).
    `device` is what the app said it is, kept on every session of the
    family, so its owner can tell it from the others (D-114). Every access
    token carries the family as `sid`, so ending it ends them at once.
    `sign_in_acknowledged_at` is carried the same way (D-120).
    """
    refresh_token = new_refresh_token()
    refresh_expires_at = refresh_token_expiry(account.role, now, second_factor_at)
    db.add(
        AuthSession(
            account_id=account.id,
            family_id=family_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expires_at,
            second_factor_at=second_factor_at,
            passkey_at=passkey_at,
            sign_in_acknowledged_at=sign_in_acknowledged_at,
            client_platform=None if device is None else device.platform,
            client_label=None if device is None else device.label,
            created_at=now,
            updated_at=now,
        )
    )
    if second_factor_at is not None:
        methods = TWO_FACTORS
    elif passkey_at is not None:
        methods = PASSKEY
    else:
        methods = PHONE_CODE_ONLY
    access_token, access_expires_at = create_access_token(
        account.id,
        account.role,
        now,
        methods=methods,
        not_after=refresh_expires_at if account.role == "admin" else None,
        authenticated_at=now if authenticated_at is None else authenticated_at,
        session_id=family_id,
    )
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
    token_hash = hash_refresh_token(refresh_token)
    account_id = db.scalar(
        select(AuthSession.account_id).where(AuthSession.token_hash == token_hash)
    )
    if account_id is None:
        db.rollback()
        raise InvalidToken()
    # The account's sessions first, as everything that ends one does, then
    # this token's row, read again under the lock: a logout that ran while
    # this waited is seen, and two callers cannot rotate one token at once.
    lock_sessions_of(db, account_id)
    auth_session = db.scalars(
        select(AuthSession)
        .where(AuthSession.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if auth_session is None:  # pragma: no cover - its account went meanwhile
        db.rollback()
        raise InvalidToken()

    if auth_session.used_at is not None:
        # Token reuse: assume theft and end every session in the family.
        _revoke_family(db, auth_session, now)
        db.commit()
        logger.warning("auth.refresh_token_reused family_id=%s", auth_session.family_id)
        raise InvalidToken()

    if auth_session.revoked_at is not None or now >= auth_session.expires_at:
        db.rollback()
        raise InvalidToken()

    auth_session.used_at = now
    auth_session.updated_at = now
    account = db.get_one(Account, auth_session.account_id)
    if account.suspended_at is not None:
        # A suspension ends every session; this catches any it missed.
        _revoke_family(db, auth_session, now)
        db.commit()
        raise AccountSuspended.because(account.suspension_reason)
    if account.role == "admin" and auth_session.second_factor_at is None:
        # An admin session from before D-105, or made any way but the
        # two-factor login: the migration ended them all, and this ends any
        # that slipped past it.
        _revoke_family(db, auth_session, now)
        db.commit()
        raise InvalidToken()
    result = issue_session(
        db,
        account,
        auth_session.family_id,
        now,
        second_factor_at=auth_session.second_factor_at,
        authenticated_at=logged_in_at(db, auth_session.family_id),
        passkey_at=auth_session.passkey_at,
        sign_in_acknowledged_at=auth_session.sign_in_acknowledged_at,
        device=_device_of(auth_session),
    )
    db.commit()
    return result


def _device_of(auth_session: AuthSession) -> ClientDevice | None:
    """The device a session's sign-in named, to carry to its next row."""
    if auth_session.client_platform is None or auth_session.client_label is None:
        return None
    return ClientDevice(
        platform=auth_session.client_platform, label=auth_session.client_label
    )


def logged_in_at(db: Session, family_id: uuid.UUID) -> datetime:
    """When this login was proven: its family's first session (D-109).

    Rotation adds a row to the family and never removes one, so the
    earliest row is the login itself.
    """
    return db.execute(
        select(func.min(AuthSession.created_at)).where(AuthSession.family_id == family_id)
    ).scalar_one()


def logout(
    db: Session, refresh_token: str, now: datetime, *, device_token: str | None = None
) -> None:
    """End the login this refresh token belongs to.

    Revokes the whole rotation chain, so older copies stop working too.
    With the phone's push token, its notifications stop as well, but only
    if the token is the same account's (D-095). Unknown tokens are ignored:
    logout always looks the same to the caller.
    """
    auth_session = db.scalars(
        select(AuthSession).where(
            AuthSession.token_hash == hash_refresh_token(refresh_token)
        )
    ).first()
    if auth_session is not None:
        _revoke_family(db, auth_session, now)
        if device_token is not None:
            devices.forget_token(db, auth_session.account_id, device_token)
    db.commit()


def logout_all_sessions(db: Session, account_id: uuid.UUID, now: datetime) -> int:
    """End every session of one account. Returns how many were still active.

    The caller commits, after spending the code that allowed it (item 82).
    """
    ended = end_sessions(db, account_id, now)
    # Logged out everywhere means told nowhere: every phone's push stops.
    devices.forget_all(db, account_id)
    return ended
