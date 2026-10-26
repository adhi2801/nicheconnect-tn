"""A brand's saved creator lists (item 66, D-129): the rules.

Lists are the brand's own and private (`creator_list_models`). Who appears
in one follows search's own rule (`search_service.visible`): only creators
the brand could find today, so a list never becomes a way round an
unpublished Passport, a suspension, a takedown or a block. Saving one is
refused the same way, as not found.

At most MAX_LISTS_PER_BRAND lists and MAX_CREATORS_PER_LIST creators a
list, each counted under a row lock (the brand's row, the list's row), so
two requests at once cannot both slip past a cap.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.export import ExportedSection, allow, build_section
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.deal_memo import delivery_record
from app.modules.deal_memo.delivery_record import DeliveryRecord
from app.modules.matching import search_service
from app.modules.matching.creator_list_models import (
    MAX_CREATORS_PER_LIST,
    MAX_LISTS_PER_BRAND,
    CreatorList,
    CreatorListEntry,
)
from app.modules.matching.exceptions import (
    CreatorListFull,
    CreatorListNameTaken,
    CreatorListNotFound,
    CreatorListsFull,
    ListedCreatorNotFound,
)

EXPORTED_TABLES = frozenset({"creator_list", "creator_list_entry"})
LIST_EXPORT_FIELDS = allow("id", "brand_id", "name", "created_at", "updated_at")
ENTRY_EXPORT_FIELDS = allow("id", "list_id", "creator_id", "created_at")


def lists_of(db: Session, brand: Brand) -> list[tuple[CreatorList, int]]:
    """The brand's lists, newest first, each with how many creators it shows today.

    Whole, not paged: at most MAX_LISTS_PER_BRAND. Two queries.
    """
    lists = list(
        db.scalars(
            select(CreatorList)
            .where(CreatorList.brand_id == brand.id)
            .order_by(CreatorList.created_at.desc(), CreatorList.id.desc())
        ).all()
    )
    counts: dict[uuid.UUID, int] = {}
    if lists:
        counts = dict(
            db.execute(
                select(CreatorListEntry.list_id, func.count())
                .join(Creator, Creator.id == CreatorListEntry.creator_id)
                .where(
                    CreatorListEntry.list_id.in_([lst.id for lst in lists]),
                    *search_service.visible(brand.account_id),
                )
                .group_by(CreatorListEntry.list_id)
            ).all()
        )
    return [(lst, counts.get(lst.id, 0)) for lst in lists]


def own(db: Session, brand: Brand, list_id: uuid.UUID) -> CreatorList:
    """One of the brand's lists. Another brand's, or none, is CreatorListNotFound."""
    found = db.scalars(
        select(CreatorList).where(
            CreatorList.id == list_id, CreatorList.brand_id == brand.id
        )
    ).first()
    if found is None:
        raise CreatorListNotFound()
    return found


def create(db: Session, brand: Brand, name: str, now: datetime) -> CreatorList:
    """A new, empty list. Commits. Raises CreatorListsFull and CreatorListNameTaken."""
    db.scalars(select(Brand.id).where(Brand.id == brand.id).with_for_update()).one()
    count = db.scalar(select(func.count()).where(CreatorList.brand_id == brand.id))
    if count is not None and count >= MAX_LISTS_PER_BRAND:
        db.rollback()
        raise CreatorListsFull()
    created = CreatorList(brand_id=brand.id, name=name, created_at=now, updated_at=now)
    db.add(created)
    _flush_name(db)
    db.commit()
    db.refresh(created)
    return created


def rename(db: Session, found: CreatorList, name: str, now: datetime) -> CreatorList:
    """Commits. Raises CreatorListNameTaken."""
    found.name = name
    found.updated_at = now
    _flush_name(db)
    db.commit()
    db.refresh(found)
    return found


def remove(db: Session, found: CreatorList) -> None:
    """The list and every line of it. Commits."""
    db.delete(found)
    db.commit()


def creators_in(
    db: Session,
    brand: Brand,
    found: CreatorList,
    now: datetime,
    *,
    limit: int,
    cursor: str | None,
) -> Slice[tuple[search_service.SearchResult, datetime, DeliveryRecord]]:
    """The list's creators the brand can find today, latest saved first.

    Each with when it was saved and its delivery record. Five queries a
    page, whatever its size: the page, the creators' channels and prices
    (`search_service.results_for`), and their deals and proofs
    (`delivery_record.for_creators`).
    """
    query = (
        select(CreatorListEntry, Creator)
        .join(Creator, Creator.id == CreatorListEntry.creator_id)
        .where(
            CreatorListEntry.list_id == found.id,
            *search_service.visible(brand.account_id),
        )
    )
    if cursor is not None:
        query = query.where(
            older_than_cursor(CreatorListEntry.created_at, CreatorListEntry.id, cursor)
        )
    rows = list(
        db.execute(
            query.order_by(
                CreatorListEntry.created_at.desc(), CreatorListEntry.id.desc()
            ).limit(limit + 1)
        )
    )
    page = build_slice(rows, limit, key=lambda row: (row[0].created_at, row[0].id))
    creators = [creator for _, creator in page.rows]
    results = search_service.results_for(db, creators)
    records = delivery_record.for_creators(db, [c.id for c in creators], now)
    return Slice(
        rows=[
            (result, entry.created_at, records[creator.id])
            for result, (entry, creator) in zip(results, page.rows, strict=True)
        ],
        next_cursor=page.next_cursor,
    )


def add(
    db: Session, brand: Brand, found: CreatorList, creator_id: uuid.UUID, now: datetime
) -> None:
    """Save a creator the brand can find; saving one twice is fine. Commits.

    Raises ListedCreatorNotFound (not one the brand could find in search)
    and CreatorListFull.
    """
    findable = db.scalar(
        select(Creator.id).where(
            Creator.id == creator_id, *search_service.visible(brand.account_id)
        )
    )
    if findable is None:
        raise ListedCreatorNotFound()
    db.scalars(
        select(CreatorList.id).where(CreatorList.id == found.id).with_for_update()
    ).one()
    count = db.scalar(select(func.count()).where(CreatorListEntry.list_id == found.id))
    already = db.scalar(
        select(CreatorListEntry.id).where(
            CreatorListEntry.list_id == found.id,
            CreatorListEntry.creator_id == creator_id,
        )
    )
    if already is None and count is not None and count >= MAX_CREATORS_PER_LIST:
        db.rollback()
        raise CreatorListFull()
    db.execute(
        insert(CreatorListEntry)
        .values(list_id=found.id, creator_id=creator_id, created_at=now, updated_at=now)
        .on_conflict_do_nothing(
            index_elements=[CreatorListEntry.list_id, CreatorListEntry.creator_id]
        )
    )
    db.commit()


def take_out(db: Session, found: CreatorList, creator_id: uuid.UUID) -> None:
    """Remove a creator from the list; one not on it is fine. Commits."""
    db.execute(
        delete(CreatorListEntry).where(
            CreatorListEntry.list_id == found.id,
            CreatorListEntry.creator_id == creator_id,
        )
    )
    db.commit()


def erase_for_brand(db: Session, brand_id: uuid.UUID) -> None:
    """On deleting the account (D-122): the brand's lists, and their lines. Never commits."""
    db.execute(delete(CreatorList).where(CreatorList.brand_id == brand_id))


def erase_for_creator(db: Session, creator_id: uuid.UUID) -> None:
    """On deleting the account (D-122): every line about the creator. Never commits."""
    db.execute(delete(CreatorListEntry).where(CreatorListEntry.creator_id == creator_id))


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """A brand's lists and their lines. A creator is never shown whose lists they are on."""
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == account_id))
    lists = (
        list(
            db.scalars(
                select(CreatorList)
                .where(CreatorList.brand_id == brand_id)
                .order_by(CreatorList.created_at, CreatorList.id)
            ).all()
        )
        if brand_id is not None
        else []
    )
    entries = (
        list(
            db.scalars(
                select(CreatorListEntry)
                .where(CreatorListEntry.list_id.in_([lst.id for lst in lists]))
                .order_by(CreatorListEntry.created_at, CreatorListEntry.id)
            ).all()
        )
        if lists
        else []
    )
    return [
        build_section(
            "creator_lists",
            table="creator_list",
            purpose="The lists of creators you saved, by name.",
            objects=lists,
            fields=LIST_EXPORT_FIELDS,
        ),
        build_section(
            "creator_list_entries",
            table="creator_list_entry",
            purpose="Who you saved on each list, by the creator's id, and when.",
            objects=entries,
            fields=ENTRY_EXPORT_FIELDS,
        ),
    ]


def _flush_name(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if "uq_creator_list_name" not in str(error):
            raise
        raise CreatorListNameTaken() from None
