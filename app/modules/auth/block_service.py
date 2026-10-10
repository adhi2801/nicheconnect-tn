"""Blocking: one account stops another reaching it (item 59).

A creator blocks a brand; a brand blocks a creator. Each is named by the id
the person already sees (a campaign's `brand_id`, a search result's
`creator_id`), and stored as the two accounts behind them, since a block is
about people, not profiles. What a block changes is in `blocks.py` and the
queries that use it; this file only records and lists them.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth.exceptions import BlockNotFound, BlockTargetNotFound
from app.modules.auth.models.account import Account
from app.modules.auth.models.block import AccountBlock
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator

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
    model = Brand if account.role == "creator" else Creator
    target = db.scalar(select(model.account_id).where(model.id == target_id))
    if target is None:
        raise BlockTargetNotFound()
    return target


def block(
    db: Session, account: Account, target_id: uuid.UUID | None, now: datetime
) -> BlockView:
    """Block, or find the block already there: blocking twice is one block.

    One INSERT ... ON CONFLICT DO NOTHING, so two taps at once cannot
    collide. Raises BlockTargetNotFound.
    """
    blocked = _target_account(db, account, target_id)
    db.execute(
        insert(AccountBlock)
        .values(
            blocker_account_id=account.id,
            blocked_account_id=blocked,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_account_block_pair")
    )
    db.commit()
    block_id = db.scalar(
        select(AccountBlock.id).where(
            AccountBlock.blocker_account_id == account.id,
            AccountBlock.blocked_account_id == blocked,
        )
    )
    return _views(db, account, select(AccountBlock).where(AccountBlock.id == block_id))[0]


def unblock(db: Session, account: Account, block_id: uuid.UUID) -> None:
    """Remove one of this account's own blocks. Raises BlockNotFound."""
    removed = db.execute(
        delete(AccountBlock)
        .where(AccountBlock.id == block_id, AccountBlock.blocker_account_id == account.id)
        .returning(AccountBlock.id)
    ).first()
    if removed is None:
        db.rollback()
        raise BlockNotFound()
    db.commit()


def _views(
    db: Session, account: Account, query: Select[tuple[AccountBlock]]
) -> list[BlockView]:
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
    db: Session, account: Account, *, limit: int, cursor: str | None = None
) -> Slice[BlockView]:
    """This account's own blocks, newest first. Never those placed against it."""
    query = select(AccountBlock).where(AccountBlock.blocker_account_id == account.id)
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
