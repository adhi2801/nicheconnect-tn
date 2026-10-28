"""The admins' login with two factors, and the alerts around it (item 101, D-105).

The rules are `auth.second_factor_service`'s. This layer adds what that one
cannot reach: **every active admin is told** of every admin sign-in, every
second factor refused after a right phone code, and every setup ticket
issued or redeemed, by an in-app notification nobody can mute (ASVS 5.0
6.3.5 and 6.3.7). The refusals and setup changes are also logged at error
level, which error tracking sends to the founders (D-074). With two
founders, each sees the other's logins: a stolen one cannot go unnoticed.

Each function is one unit of work and commits once, alert included.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth import second_factor
from app.modules.auth import second_factor_service as rules
from app.modules.auth.exceptions import OtpInvalid
from app.modules.auth.models.account import Account
from app.modules.auth.second_factor_service import SecondFactorCheck
from app.modules.auth.service import ClientDevice, LoginResult
from app.modules.notifications import service as notifications

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecondFactorSetup:
    """A new secret, to be shown once."""

    secret: str
    setup_link: str


def log_in(
    db: Session,
    phone: str,
    code: str,
    authenticator_code: str,
    now: datetime,
    device: ClientDevice | None = None,
) -> LoginResult:
    """An admin session for both codes right; OtpInvalid for anything else.

    Raises OtpInvalid, OtpVerifyLimitReached and AccountSuspended.
    """
    check = rules.check_admin_login(db, phone, code, authenticator_code, now, device)
    if check.login is None:
        _refused(db, check, now)
    _tell_every_admin(db, "admin_signed_in", check.account, now, {})
    db.commit()
    logger.info("auth.admin_signed_in account_id=%s", check.account.id)
    return check.login


def set_up(
    db: Session, phone: str, code: str, ticket: str, now: datetime
) -> SecondFactorSetup:
    """Redeem a setup ticket for a new authenticator secret, shown once.

    Raises OtpInvalid, OtpVerifyLimitReached and AccountSuspended.
    """
    check = rules.redeem_ticket(db, phone, code, ticket, now)
    if check.secret is None:
        _refused(db, check, now)
    _tell_every_admin(
        db, "admin_second_factor_changed", check.account, now, {"change": "set_up"}
    )
    db.commit()
    logger.error("auth.admin_second_factor_set_up account_id=%s", check.account.id)
    return SecondFactorSetup(
        secret=second_factor.secret_text(check.secret),
        setup_link=second_factor.setup_link(
            check.secret, f"admin-{check.account.id.hex[:8]}"
        ),
    )


def issue_ticket(db: Session, admin: Account, now: datetime) -> str:
    """A setup ticket for this admin, for `scripts/make_admin.py` to print once.

    Ends the admin's sessions and voids their old authenticator. Every admin
    is told, so a ticket nobody asked for is noticed.
    """
    ticket = rules.issue_ticket(db, admin, now)
    _tell_every_admin(
        db, "admin_second_factor_changed", admin, now, {"change": "ticket_issued"}
    )
    db.commit()
    logger.error("auth.admin_second_factor_ticket_issued account_id=%s", admin.id)
    return ticket


def _refused(db: Session, check: SecondFactorCheck, now: datetime) -> NoReturn:
    """Alert, commit the used attempts, and answer exactly as a wrong code."""
    _tell_every_admin(
        db,
        "admin_second_factor_refused",
        check.account,
        now,
        {"reason": check.refused, "locked": check.locked_now},
    )
    db.commit()
    logger.error(
        "auth.admin_second_factor_refused account_id=%s reason=%s locked=%s",
        check.account.id,
        check.refused,
        check.locked_now,
    )
    raise OtpInvalid()


def _tell_every_admin(
    db: Session,
    notification_type: str,
    about: Account,
    now: datetime,
    details: dict[str, Any],
) -> None:
    """One notification to each active admin, the one it is about included."""
    admin_ids: list[uuid.UUID] = list(
        db.scalars(
            select(Account.id).where(
                Account.role == "admin", Account.suspended_at.is_(None)
            )
        ).all()
    )
    for admin_id in admin_ids:
        notifications.record(
            db,
            account_id=admin_id,
            notification_type=notification_type,
            now=now,
            details={"admin_account_id": str(about.id), **details},
        )
