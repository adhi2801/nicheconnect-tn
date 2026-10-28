"""How accounts arrive, and who invited whom (D-080).

Four rules, each for a reason:

- **Written once, at sign-up only.** `record_arrival` runs inside the login
  that creates the account; a returning login never reaches it, so nobody can
  rewrite how they arrived, or claim an invitation later for a reward.
- **A bad code never blocks sign-up.** An unknown code is ignored and the
  account is recorded as `not_given`: a typo must not cost us a creator.
- **Inviters see counts, never names** (D-080): who joined is that person's
  own business; telling another person is a DPDP question for the validation
  pack.
- **No reward logic here.** Recording makes a reward possible; what it is,
  and its tax treatment, is a founders' and validation-pack question.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import IST, india_date
from app.core.export import ExportedSection, allow, build_section
from app.modules.auth.models.account import Account
from app.modules.auth.models.attribution import (
    CODE_ALPHABET,
    CODE_LENGTH,
    AccountAttribution,
    InviteCode,
)

EXPORTED_TABLES = frozenset({"invite_code", "account_attribution"})
CODE_EXPORT_FIELDS = allow("code", "created_at")
ARRIVAL_EXPORT_FIELDS = allow("source", "campaign_tag", "created_at")

# Room for a code to collide with an existing one before giving up. With 32
# characters to the power of 8, about a trillion codes, a second try is
# already a curiosity.
MAX_CODE_ATTEMPTS = 5


@dataclass(frozen=True)
class Arrival:
    """What the app says about how a new person found us. All optional."""

    invite_code: str | None = None
    source: str | None = None
    campaign_tag: str | None = None


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalise_code(raw: str) -> str:
    """As people type it: any case, spaces or hyphens dropped."""
    return raw.strip().upper().replace(" ", "").replace("-", "")


def record_arrival(
    db: Session, account: Account, arrival: Arrival | None, now: datetime
) -> AccountAttribution:
    """Write how this new account arrived. Call only when creating an account.

    Flushes, never commits: it is part of the login's own transaction, so an
    account never exists without its attribution, or the reverse.
    """
    arrival = arrival or Arrival()
    code: InviteCode | None = None
    if arrival.invite_code:
        code = db.scalars(
            select(InviteCode).where(
                InviteCode.code == normalise_code(arrival.invite_code)
            )
        ).first()
    if code is not None:
        source = "invite"
    elif arrival.source in (None, "invite"):
        # An invitation with no valid code is not an invitation we can stand behind.
        source = "not_given"
    else:
        source = arrival.source
    row = AccountAttribution(
        account_id=account.id,
        invite_code_id=code.id if code is not None else None,
        source=source,
        campaign_tag=arrival.campaign_tag,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def invite_code_for(db: Session, account: Account, now: datetime) -> InviteCode:
    """This account's code, made on the first request.

    Two first requests at once both end with the same single code: the insert
    does nothing if the account already has one, and the code is read after.
    """
    for _ in range(MAX_CODE_ATTEMPTS):
        existing = db.scalars(
            select(InviteCode).where(InviteCode.account_id == account.id)
        ).first()
        if existing is not None:
            return existing
        result = db.execute(
            insert(InviteCode)
            .values(
                account_id=account.id, code=new_code(), created_at=now, updated_at=now
            )
            .on_conflict_do_nothing()
            .returning(InviteCode.id)
        ).first()
        db.commit()
        if result is not None:
            return db.scalars(select(InviteCode).where(InviteCode.id == result.id)).one()
        # Nothing inserted: either another request made this account's code
        # (found on the next pass) or the random code was taken (retried).
    raise RuntimeError("Could not make an invite code; the alphabet may be exhausted")


@dataclass(frozen=True)
class InviteCounts:
    brands: int
    creators: int


def invites_by(db: Session, account: Account) -> InviteCounts:
    """How many brands and creators joined with this account's code. Counts only."""
    counts: dict[str, int] = {
        role: count
        for role, count in db.execute(
            select(Account.role, func.count())
            .join(AccountAttribution, AccountAttribution.account_id == Account.id)
            .join(InviteCode, InviteCode.id == AccountAttribution.invite_code_id)
            .where(InviteCode.account_id == account.id)
            .group_by(Account.role)
        )
    }
    return InviteCounts(brands=counts.get("brand", 0), creators=counts.get("creator", 0))


@dataclass(frozen=True)
class SignupRow:
    week_starting: date
    source: str
    role: str
    accounts: int


def signups_by_source(db: Session, now: datetime, *, weeks: int) -> list[SignupRow]:
    """New accounts per week (Monday, Tamil Nadu time), source and role. Counts only.

    Accounts created before attribution existed have no row and are not
    counted: they arrived before anybody asked.
    """
    today = india_date(now)
    first_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    since = datetime.combine(first_monday, datetime.min.time(), tzinfo=IST)
    week = func.date_trunc(
        "week", func.timezone("Asia/Kolkata", AccountAttribution.created_at)
    )
    rows = db.execute(
        select(week, AccountAttribution.source, Account.role, func.count())
        .join(Account, Account.id == AccountAttribution.account_id)
        .where(AccountAttribution.created_at >= since)
        .group_by(week, AccountAttribution.source, Account.role)
        .order_by(week.desc(), AccountAttribution.source, Account.role)
    ).all()
    return [
        SignupRow(week_starting=started.date(), source=source, role=role, accounts=count)
        for started, source, role, count in rows
    ]


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """How this account arrived, and its own invite code.

    The code used to invite this account is left out: it belongs to the
    person who invited them, and the export is about this person only.
    """
    arrival = list(
        db.scalars(
            select(AccountAttribution).where(AccountAttribution.account_id == account_id)
        ).all()
    )
    codes = list(
        db.scalars(select(InviteCode).where(InviteCode.account_id == account_id)).all()
    )
    return [
        build_section(
            "how_you_joined",
            table="account_attribution",
            purpose=(
                "Where you told us you heard of us when you signed up, so we "
                "know which ways of reaching people work."
            ),
            objects=arrival,
            fields=ARRIVAL_EXPORT_FIELDS,
            extra=lambda row: {"joined_with_an_invite": row.invite_code_id is not None},
        ),
        build_section(
            "your_invite_code",
            table="invite_code",
            purpose="The code you share to invite others, if you asked for one.",
            objects=codes,
            fields=CODE_EXPORT_FIELDS,
        ),
    ]
