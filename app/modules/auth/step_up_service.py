"""A second check before a risky change (item 82, D-107).

Setting a UPI ID, downloading the data export, logging out everywhere and
changing the phone number (item 80) each need a fresh code, on top of the
access token. A stolen session (malware,
a borrowed laptop, a copied token) is then not enough: the thief also needs
the phone. ASVS 5.0 7.5.1 to 7.5.3.

**One code, one change.** A code is asked for to do one action and, where it
has one, to set one exact value: a code asked for to set `meena@okhdfc`
cannot set any other UPI ID. That is the EU's dynamic linking (RTS Article
5) applied to an account change, so a code tricked out of someone for one
change cannot be spent on another. Each code works once, for 5 minutes.

**One budget per phone.** Step-up codes count against the same caps as login
codes, for sending and for guessing (`service.codes_for_phone`), and take the
same per-phone lock, so neither route buys extra messages or extra guesses.

**Admins** prove it with their authenticator (D-105), under the login's
rules: no message is sent, each step's code works once, refusals count
towards the lock.

**What it does not stop:** a SIM swap or a hijacked WhatsApp, since the code
goes to whoever holds the number. That is why a new UPI ID also waits 24
hours before brands see it (`payment_status.upi_service`), and a new phone
number 72 hours (`me.phone_change_service`).

`consume` is called first in its caller's transaction and leaves the use
uncommitted, so the code is spent only if the change itself commits.
"""

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.modules.auth import second_factor_service
from app.modules.auth import service as login
from app.modules.auth.exceptions import (
    OtpSendLimitReached,
    OtpVerifyLimitReached,
    RoleNotAllowed,
    StepUpCodeInvalid,
    StepUpRequired,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.step_up_challenge import (
    MAX_STEP_UP_ATTEMPTS,
    STEP_UP_TTL,
    StepUpChallenge,
)
from app.modules.auth.service import PendingOtp
from app.modules.auth.tokens import generate_otp_code, hash_otp_code, otp_code_matches

StepUpAction = Literal[
    "set_upi_id", "download_export", "log_out_everywhere", "change_phone"
]
StepUpMethod = Literal["phone_code", "authenticator"]
# The request header a risky change carries its code in.
STEP_UP_HEADER = "Step-Up-Code"
# Who may ask for each; an action not named here is for every role.
# An admin's number changes only through scripts/make_admin.py (item 80).
ACTION_ROLES: dict[str, tuple[str, ...]] = {
    "set_upi_id": ("creator",),
    "change_phone": ("brand", "creator"),
}

EXPORTED_TABLES = frozenset({"step_up_challenge"})
# What was asked for and when, never the hashes of the code or the value.
EXPORT_FIELDS = allow(
    "id", "action", "attempts", "expires_at", "consumed_at", "created_at", "updated_at"
)


@dataclass(frozen=True)
class StepUpCode:
    """How the code for a change is proven, and the message to send, if any."""

    action: StepUpAction
    method: StepUpMethod
    # None for an authenticator code, which lasts its 30-second step.
    expires_at: datetime | None
    pending: PendingOtp | None


def value_hash(action: StepUpAction, value: str) -> str:
    """HMAC-SHA256 of an action and its new value, keyed by OTP_HASH_KEY.

    The action is in the hash too, with a separator neither can contain, so
    a code for one action never matches another's.
    """
    key = settings.otp_hash_key.get_secret_value().encode()
    message = b"step-up\x00" + action.encode() + b"\x00" + value.encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def request_code(
    db: Session, account: Account, action: StepUpAction, value: str, now: datetime
) -> StepUpCode:
    """A code for this account to do `action` with `value`. Commits.

    For an admin nothing is sent: their authenticator gives the code.
    Raises RoleNotAllowed (only creators give a UPI ID; admins change no
    phone number here) and
    OtpSendLimitReached (the phone's caps are reached).
    """
    if account.role not in ACTION_ROLES.get(action, (account.role,)):
        raise RoleNotAllowed()
    if account.role == "admin":
        return StepUpCode(
            action=action, method="authenticator", expires_at=None, pending=None
        )
    login.lock_phone(db, account.phone)
    retry_after = login.seconds_until_send_allowed(db, account.phone, now)
    if retry_after > 0:
        db.rollback()
        raise OtpSendLimitReached(headers={"Retry-After": str(retry_after)})

    code = generate_otp_code()
    expires_at = now + STEP_UP_TTL
    db.add(
        StepUpChallenge(
            account_id=account.id,
            action=action,
            value_hash=value_hash(action, value),
            code_hash=hash_otp_code(code),
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    return StepUpCode(
        action=action,
        method="phone_code",
        expires_at=expires_at,
        pending=PendingOtp(phone=account.phone, code=code, expires_at=expires_at),
    )


def consume(
    db: Session,
    account: Account,
    action: StepUpAction,
    value: str,
    code: str | None,
    now: datetime,
) -> None:
    """Spend the code that allows exactly this change. The caller commits.

    Call it before any other write: a refusal rolls back, or commits the
    attempt it used, before raising.
    Raises StepUpRequired (no code given), StepUpCodeInvalid (wrong, expired,
    used, exhausted, for another change, or none asked for) and
    OtpVerifyLimitReached (too many wrong tries for this phone).
    """
    if code is None:
        raise StepUpRequired()
    if account.role == "admin":
        if not second_factor_service.check_authenticator_code(db, account, code, now):
            db.commit()
            raise StepUpCodeInvalid()
        return

    login.lock_phone(db, account.phone)
    retry_after = login.seconds_until_verify_allowed(db, account.phone, now)
    if retry_after > 0:
        db.rollback()
        raise OtpVerifyLimitReached(headers={"Retry-After": str(retry_after)})

    challenge = _latest(db, account.id, action)
    if (
        challenge is None
        or challenge.consumed_at is not None
        or now >= challenge.expires_at
        or challenge.attempts >= MAX_STEP_UP_ATTEMPTS
    ):
        db.rollback()
        raise StepUpCodeInvalid()
    right_code = otp_code_matches(code, challenge.code_hash)
    right_value = hmac.compare_digest(value_hash(action, value), challenge.value_hash)
    if not (right_code and right_value):
        challenge.attempts += 1
        challenge.updated_at = now
        db.commit()
        raise StepUpCodeInvalid()
    challenge.consumed_at = now
    challenge.updated_at = now


def _latest(
    db: Session, account_id: uuid.UUID, action: StepUpAction
) -> StepUpChallenge | None:
    """The account's newest code for `action`; only it counts, as for login.

    Two asked for in the same instant are told apart by their ids, which
    uuidv7 orders by when they were made.
    """
    return db.scalars(
        select(StepUpChallenge)
        .where(StepUpChallenge.account_id == account_id, StepUpChallenge.action == action)
        .order_by(StepUpChallenge.created_at.desc(), StepUpChallenge.id.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    ).first()


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """Every code this account asked for before a risky change, newest first."""
    rows = list(
        db.scalars(
            select(StepUpChallenge)
            .where(StepUpChallenge.account_id == account_id)
            .order_by(StepUpChallenge.created_at.desc(), StepUpChallenge.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    return [
        build_section(
            "step_up_codes",
            table="step_up_challenge",
            purpose=(
                "The codes you asked for before a risky change (setting a UPI "
                "ID, downloading this file, logging out everywhere, changing "
                "your phone number): which "
                "change, when, how many wrong tries, and whether it was used. "
                "We keep only an unreadable hash of each code and of the new "
                "value, so neither is included."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]
