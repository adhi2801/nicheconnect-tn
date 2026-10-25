"""One number, both sides (item 8, D-126): the accounts a phone number holds.

A number may hold a brand account and a creator account of one person,
each exactly as before: its own role, profile, sessions, passkeys and data
(D-014 holds for each). What belongs to the number rather than to an
account is answered here, so every module agrees on it:

- which accounts are on a number (`on_number`): login codes and their caps
  are the number's, and a phone change or a lost-number cancel covers all;
- whether two accounts are one person (`same_person`), so the two sides
  never deal with each other, which is how a record would be pumped;
- the owner's other side, if any (`other_side`).

An admin's number holds the admin account alone (`login`), so an admin
never shares a session table, a passkey list or a phone change with a
brand or a creator account.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models.account import Account

SIDES = ("brand", "creator")


def on_number(db: Session, phone: str) -> list[Account]:
    """Every account on the number, brand before creator. Deleted ones have none."""
    return list(
        db.scalars(
            select(Account).where(Account.phone == phone).order_by(Account.role)
        ).all()
    )


def same_person(db: Session, one: uuid.UUID, other: uuid.UUID) -> bool:
    """True when the two accounts share a number: one person's two sides."""
    phones = db.scalars(select(Account.phone).where(Account.id.in_([one, other]))).all()
    return len(phones) == 2 and phones[0] is not None and phones[0] == phones[1]


def other_side(db: Session, account: Account) -> str | None:
    """The role of the account's other side on its number, or None."""
    if account.phone is None or account.role not in SIDES:
        return None
    return db.scalar(
        select(Account.role).where(
            Account.phone == account.phone, Account.id != account.id
        )
    )
