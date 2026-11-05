"""Blocking: one account stops another reaching it (item 59).

A creator blocks a brand; a brand blocks a creator. Each is named by the id
the person already sees (a campaign's `brand_id`, a search result's
`creator_id`), and stored as the two accounts behind them, since a block is
about people, not profiles. What a block changes is in `blocks.py` and the
queries that use it; this file only records and lists them.

A brand's block is the brand's (D-148 piece 2): whoever on its team places
it, it is stored as the brand's owner's, the account every block check of a
brand reads, so it stops the whole brand and the whole team sees it. Each
function takes `for_brand`, the brand someone on its team acts for, or None
for a creator, or a brand account in no brand, who block as themselves. A
brand's owner is read under a share of the brand's row lock, so a block
placed as the brand is handed over waits for it and lands on the new owner.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, delete, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.safety.exceptions import BlockNotFound, BlockTargetNotFound
from app.modules.safety.models import AccountBlock

EXPORTED_TABLES = frozenset({"account_block"})
EXPORT_FIELDS = allow("id", "blocked_account_id", "created_at")


@dataclass(frozen=True)
class BlockView:
    """A block as its owner sees it: who, by the id and name they know."""

    id: uuid.UUID
    brand_id: uuid.UUID | None
    creator_id: uuid.UUID | None
    name: str
    created_at: datetime


def _target_account(
    db: Session, account: Account, target_id: uuid.UUID | None
) -> uuid.UUID:
    """The account behind the profile a person may block.

    A creator blocks brands and a brand blocks creators: the two sides that
    can reach each other. Anything else is not found.
    """
    if target_id is None:
        raise BlockTargetNotFound()
    if account.role == "creator":
        # A brand's owner, as the block check reads it: see the module's note.
        target = db.scalar(
            select(Brand.account_id)
            .where(Brand.id == target_id)
            .with_for_update(key_share=True)
        )
    else:
        target = db.scalar(select(Creator.account_id).where(Creator.id == target_id))
    if target is None:
        raise BlockTargetNotFound()
    return target


def _blocker(
    db: Session, account: Account, for_brand: uuid.UUID | None, *, lock: bool
) -> uuid.UUID:
    """The account a block is stored as: the brand's owner, for anyone on its team."""
    if for_brand is None:
        return account.id
    query = select(Brand.account_id).where(Brand.id == for_brand)
    owner = db.scalar(query.with_for_update(key_share=True) if lock else query)
    return owner if owner is not None else account.id


def block(
    db: Session,
    account: Account,
    for_brand: uuid.UUID | None,
    target_id: uuid.UUID | None,
    now: datetime,
) -> BlockView:
    """Block, or find the block already there: blocking twice is one block.

    One INSERT ... ON CONFLICT DO NOTHING, so two taps at once cannot
    collide. Raises BlockTargetNotFound.
    """
    blocker = _blocker(db, account, for_brand, lock=True)
    blocked = _target_account(db, account, target_id)
    db.execute(
        insert(AccountBlock)
        .values(
            blocker_account_id=blocker,
            blocked_account_id=blocked,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_account_block_pair")
    )
    db.commit()
    block_id = db.scalar(
        select(AccountBlock.id).where(
            AccountBlock.blocker_account_id == blocker,
            AccountBlock.blocked_account_id == blocked,
        )
    )
    return _views(db, account, select(AccountBlock).where(AccountBlock.id == block_id))[0]


def unblock(
    db: Session, account: Account, for_brand: uuid.UUID | None, block_id: uuid.UUID
) -> None:
    """Remove one of this account's own blocks, or its brand's. Raises BlockNotFound."""
    blocker = _blocker(db, account, for_brand, lock=True)
    removed = db.execute(
        delete(AccountBlock)
        .where(AccountBlock.id == block_id, AccountBlock.blocker_account_id == blocker)
        .returning(AccountBlock.id)
    ).first()
    if removed is None:
        db.rollback()
        raise BlockNotFound()
    db.commit()


def move_brand_blocks(db: Session, old: uuid.UUID, new: uuid.UUID, now: datetime) -> None:
    """On handing a brand over (D-148): every block placed by or against it, from
    its old owner's account to the new. Never commits.

    An account that owned a brand is a brand account owning only that one,
    so each of its blocks is the brand's. Each is moved in place, keeping its
    id and when it was placed, so a block id someone holds still works; one
    the new owner already had is kept once, as theirs. Three statements,
    however many blocks.
    """
    same = aliased(AccountBlock)
    db.execute(
        update(AccountBlock)
        .where(
            AccountBlock.blocker_account_id == old,
            AccountBlock.blocked_account_id != new,
            ~exists().where(
                and_(
                    same.blocker_account_id == new,
                    same.blocked_account_id == AccountBlock.blocked_account_id,
                )
            ),
        )
        .values(blocker_account_id=new, updated_at=now)
    )
    db.execute(
        update(AccountBlock)
        .where(
            AccountBlock.blocked_account_id == old,
            AccountBlock.blocker_account_id != new,
            ~exists().where(
                and_(
                    same.blocked_account_id == new,
                    same.blocker_account_id == AccountBlock.blocker_account_id,
                )
            ),
        )
        .values(blocked_account_id=new, updated_at=now)
    )
    # What is left was already the new owner's, or between the two of them.
    db.execute(
        delete(AccountBlock).where(
            or_(
                AccountBlock.blocker_account_id == old,
                AccountBlock.blocked_account_id == old,
            )
        )
    )


def _views(db: Session, account: Account, query: Select[AccountBlock]) -> list[BlockView]:
    """The blocks a query picks, with each target's public name, in one query."""
    blocks = list(db.scalars(query).all())
    if not blocks:
        return []
    accounts = {row.blocked_account_id for row in blocks}
    if account.role == "creator":
        rows = db.execute(
            select(Brand.account_id, Brand.id, Brand.name).where(
                Brand.account_id.in_(accounts)
            )
        ).all()
    else:
        rows = db.execute(
            select(Creator.account_id, Creator.id, Creator.handle).where(
                Creator.account_id.in_(accounts)
            )
        ).all()
    found = {row[0]: (row[1], row[2]) for row in rows}
    views = []
    for row in blocks:
        profile_id, name = found.get(row.blocked_account_id, (None, ""))
        views.append(
            BlockView(
                id=row.id,
                brand_id=profile_id if account.role == "creator" else None,
                creator_id=profile_id if account.role != "creator" else None,
                name=name,
                created_at=row.created_at,
            )
        )
    return views


def list_blocks(
    db: Session,
    account: Account,
    for_brand: uuid.UUID | None,
    *,
    limit: int,
    cursor: str | None = None,
) -> Slice[BlockView]:
    """This account's own blocks, or its brand's, newest first. Never those placed against it."""
    blocker = _blocker(db, account, for_brand, lock=False)
    query = select(AccountBlock).where(AccountBlock.blocker_account_id == blocker)
    if cursor is not None:
        query = query.where(
            older_than_cursor(AccountBlock.created_at, AccountBlock.id, cursor)
        )
    query = query.order_by(AccountBlock.created_at.desc(), AccountBlock.id.desc()).limit(
        limit + 1
    )
    return build_slice(
        _views(db, account, query), limit, key=lambda view: (view.created_at, view.id)
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The blocks this person placed.

    Not the ones placed against them: telling someone who blocked them is
    exactly what blocking must not do. Whether the DPDP right of access
    reaches that is a question for the validation pack (legal.md section 4).
    """
    rows = list(
        db.scalars(
            select(AccountBlock)
            .where(AccountBlock.blocker_account_id == account_id)
            .order_by(AccountBlock.created_at, AccountBlock.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    return [
        build_section(
            "blocks",
            table="account_block",
            purpose=(
                "The accounts you blocked, and when. Neither side can start "
                "anything new with the other while a block stands."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]


def erase_for_account(db: Session, account_id: uuid.UUID) -> None:
    """On deleting the account (D-122): its blocks, made by it or of it. Never commits."""
    db.execute(
        delete(AccountBlock).where(
            (AccountBlock.blocker_account_id == account_id)
            | (AccountBlock.blocked_account_id == account_id)
        )
    )
