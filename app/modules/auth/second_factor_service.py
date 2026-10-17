"""The admins' second factor: logging in with two, setting one up (item 101, D-105).

An admin proves two things in one request: the code sent to their phone, and
the code their authenticator app shows. Both in one request means there is
no half-logged-in state to attack, and either code wrong gets the same
answer as a wrong phone code (OtpInvalid), so a caller learns nothing about
which one failed or whether the number is an admin's.

**Setup only through a founder.** An authenticator is set up only by
redeeming a ticket that `scripts/make_admin.py` issues to someone with
access to the database: there is no API route to change it, so there is no
help desk to talk round (as at M&S in 2025). Issuing a ticket ends the
admin's sessions and clears any old secret.

These functions do not commit when an admin's phone code was right: the
admin module records the alert to every admin in the same transaction, then
commits (it sits above notifications; this module cannot reach them). Where
the phone code was wrong, or the number is not an admin's, nobody is
alerted and the failure is committed here, exactly as at /auth/otp/verify.
"""

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.auth import second_factor, second_factor_secrets
from app.modules.auth import service as login
from app.modules.auth.exceptions import AccountSuspended
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.totp_factor import MAX_CONSECUTIVE_FAILURES, TotpFactor
from app.modules.auth.service import LoginResult

TICKET_LIFETIME = timedelta(minutes=15)

# Why an admin whose phone code was right was still refused, for the alert.
Refusal = Literal["wrong_code", "locked", "not_set_up", "bad_ticket"]


@dataclass(frozen=True)
class SecondFactorCheck:
    """What happened after an admin's phone code was right. Nothing is committed yet.

    Exactly one of `refused`, `login` and `secret` is set.
    """

    account: Account
    refused: Refusal | None = None
    # True when this refusal is the one that locked the factor.
    locked_now: bool = False
    login: LoginResult | None = None
    secret: bytes | None = None


def check_admin_login(
    db: Session, phone: str, code: str, authenticator_code: str, now: datetime
) -> SecondFactorCheck:
    """Check both codes; on success, a new admin session.

    Raises OtpInvalid (the phone code is wrong, or the number is not an
    admin's: committed, as at /auth/otp/verify), OtpVerifyLimitReached and
    AccountSuspended. Otherwise returns a check for the caller to alert on
    and commit. A refused authenticator code uses an attempt on the phone
    code too, so one phone code buys at most five tries.
    """
    challenge, account = _admin_with_right_phone_code(db, phone, code, now)
    factor = _locked_factor(db, account.id)
    if factor is None or factor.secret_ciphertext is None:
        return _refuse(challenge, account, "not_set_up")
    if factor.locked_at is not None:
        return _refuse(challenge, account, "locked")

    secret = second_factor_secrets.unseal(factor.secret_ciphertext, account.id)
    step = (
        None
        if secret is None
        else second_factor.accepted_step(
            secret, authenticator_code, now, factor.last_used_step
        )
    )
    if step is None:
        factor.consecutive_failures += 1
        factor.updated_at = now
        locked_now = factor.consecutive_failures >= MAX_CONSECUTIVE_FAILURES
        if locked_now:
            factor.locked_at = now
        return _refuse(challenge, account, "wrong_code", locked_now=locked_now)

    factor.last_used_step = step
    factor.consecutive_failures = 0
    factor.updated_at = now
    challenge.consumed_at = now
    # A fresh login starts its own rotation family; the 12 hours start now.
    result = login.issue_session(db, account, uuid.uuid4(), now, second_factor_at=now)
    return SecondFactorCheck(account=account, login=result)


def redeem_ticket(
    db: Session, phone: str, code: str, ticket: str, now: datetime
) -> SecondFactorCheck:
    """Swap a founder's setup ticket, with the phone code, for a new secret.

    The secret is returned once, to be shown once; only its encrypted form
    is kept. Raises as check_admin_login does, and refuses a ticket that is
    wrong, used or expired as `bad_ticket`.
    """
    challenge, account = _admin_with_right_phone_code(db, phone, code, now)
    factor = _locked_factor(db, account.id)
    if (
        factor is None
        or factor.ticket_hash is None
        or factor.ticket_expires_at is None
        or now >= factor.ticket_expires_at
        or not hmac.compare_digest(factor.ticket_hash, second_factor.hash_ticket(ticket))
    ):
        return _refuse(challenge, account, "bad_ticket")

    secret = second_factor.new_secret()
    factor.secret_ciphertext = second_factor_secrets.seal(secret, account.id)
    factor.enrolled_at = now
    factor.ticket_hash = None
    factor.ticket_expires_at = None
    factor.updated_at = now
    challenge.consumed_at = now
    return SecondFactorCheck(account=account, secret=secret)


def issue_ticket(db: Session, account: Account, now: datetime) -> str:
    """A new setup ticket for this admin, ending their sessions. The caller commits.

    Any old secret is cleared and a lock lifted: the ticket is how a lost or
    locked authenticator is replaced. Only `scripts/make_admin.py` calls this.
    """
    ticket = second_factor.new_ticket()
    factor = _locked_factor(db, account.id)
    if factor is None:
        factor = TotpFactor(account_id=account.id, created_at=now)
        db.add(factor)
    factor.secret_ciphertext = None
    factor.enrolled_at = None
    factor.ticket_hash = second_factor.hash_ticket(ticket)
    factor.ticket_expires_at = now + TICKET_LIFETIME
    factor.last_used_step = None
    factor.consecutive_failures = 0
    factor.locked_at = None
    factor.updated_at = now
    # Whoever held a session made with the old authenticator is out.
    db.execute(
        update(AuthSession)
        .where(AuthSession.account_id == account.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, updated_at=now)
    )
    return ticket


def check_authenticator_code(
    db: Session, account: Account, code: str, now: datetime
) -> bool:
    """Whether `code` is the admin's authenticator code now. The caller commits.

    The step-up check before a risky change (item 82): an admin proves it
    with the authenticator, under the same rules as at login. Each step's
    code works once, a refusal counts towards the lock, and a locked or
    missing factor refuses everything.
    """
    factor = _locked_factor(db, account.id)
    if factor is None or factor.secret_ciphertext is None or factor.locked_at is not None:
        return False
    secret = second_factor_secrets.unseal(factor.secret_ciphertext, account.id)
    step = (
        None
        if secret is None
        else second_factor.accepted_step(secret, code, now, factor.last_used_step)
    )
    factor.updated_at = now
    if step is None:
        factor.consecutive_failures += 1
        if factor.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            factor.locked_at = now
        return False
    factor.last_used_step = step
    factor.consecutive_failures = 0
    return True


def _admin_with_right_phone_code(
    db: Session, phone: str, code: str, now: datetime
) -> tuple[OtpChallenge, Account]:
    challenge = login.check_phone_code(db, phone, code, now)
    account = db.scalars(select(Account).where(Account.phone == phone)).first()
    if account is None or account.role != "admin":
        # Never reveal who is an admin: exactly a wrong code (D-061).
        login.refuse_phone_code(db, challenge)
    if account.suspended_at is not None:
        # The code is right, so the person is told; it stays unused (D-061).
        db.rollback()
        raise AccountSuspended.because(account.suspension_reason)
    return challenge, account


def _locked_factor(db: Session, account_id: uuid.UUID) -> TotpFactor | None:
    """The account's factor, locked, so two requests cannot both use one code."""
    return db.scalars(
        select(TotpFactor)
        .where(TotpFactor.account_id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def _refuse(
    challenge: OtpChallenge,
    account: Account,
    refused: Refusal,
    *,
    locked_now: bool = False,
) -> SecondFactorCheck:
    login.count_failed_attempt(challenge)
    return SecondFactorCheck(account=account, refused=refused, locked_now=locked_now)
