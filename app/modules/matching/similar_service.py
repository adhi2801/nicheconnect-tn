"""More like the creators who delivered for you (item 65, D-133).

A brand's anchors are the creators who finished a deal with it: paid and
confirmed by the creator, or, for barter, the work approved. The ranking
is closeness to the average of their embeddings (pgvector cosine
distance, exact search), among creators the brand could find in search
today (`search_service.visible`), never one it has already agreed a deal
with, nor its own other side (D-126). Embeddings hold internal ids and
public profile text only (constraint 2).

Each result says which anchor it is closest to, so the brand can see why
it is shown, and carries its own delivery record. Paged by closeness,
then id, with a cursor of its own: the order is by distance, not time.
"""

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, aliased

from app.core.pagination import InvalidCursor
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import delivery_record
from app.modules.deal_memo.delivery_record import DeliveryRecord
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.matching import search_service
from app.modules.matching.models import CreatorEmbedding
from app.modules.payment_status.models import PaymentStatus

_SEPARATOR = "|"


@dataclass(frozen=True)
class Anchor:
    creator_id: uuid.UUID
    handle: str


@dataclass(frozen=True)
class SimilarCreator:
    result: search_service.SearchResult
    similarity: float
    closest_to: Anchor
    delivery: DeliveryRecord


@dataclass(frozen=True)
class SimilarPage:
    based_on: int
    rows: list[SimilarCreator]
    next_cursor: str | None


def finished_with(brand_id: uuid.UUID) -> ColumnElement[bool]:
    """True for a deal of this brand's that finished: paid and confirmed, or
    barter with its work approved."""
    confirmed = exists().where(
        PaymentStatus.deal_memo_id == DealMemo.id, PaymentStatus.confirmed_at.is_not(None)
    )
    approved = exists().where(
        DeliverableProof.deal_memo_id == DealMemo.id,
        DeliverableProof.status == "approved",
    )
    return and_(
        Campaign.brand_id == brand_id,
        or_(confirmed, and_(Campaign.campaign_type == "barter", approved)),
    )


def page(
    db: Session, brand: Brand, now: datetime, *, limit: int, cursor: str | None
) -> SimilarPage:
    """The brand's closest findable creators, closest first. Four queries a page
    (the anchors, the page, the closest anchor of each), plus search's two and
    the delivery records' two."""
    anchors = {
        row.creator_id: Anchor(row.creator_id, row.handle)
        for row in db.execute(
            select(Creator.id.label("creator_id"), Creator.handle)
            .join(CreatorEmbedding, CreatorEmbedding.creator_id == Creator.id)
            .where(Creator.id.in_(_anchor_ids(brand.id)))
        )
    }
    if not anchors:
        return SimilarPage(based_on=0, rows=[], next_cursor=None)

    centre = (
        select(
            func.avg(CreatorEmbedding.embedding, type_=CreatorEmbedding.embedding.type)
        )
        .where(CreatorEmbedding.creator_id.in_(list(anchors)))
        .scalar_subquery()
    )
    distance = CreatorEmbedding.embedding.cosine_distance(centre)
    creator_account = aliased(Account)
    brand_phone = db.scalar(select(Account.phone).where(Account.id == brand.account_id))
    query = (
        select(Creator, distance.label("d"))
        .join(CreatorEmbedding, CreatorEmbedding.creator_id == Creator.id)
        .join(creator_account, creator_account.id == Creator.account_id)
        .where(
            *search_service.visible(brand.account_id),
            Creator.id.not_in(_worked_with(brand.id)),
            or_(
                creator_account.phone.is_(None),
                creator_account.phone.is_distinct_from(brand_phone),
            ),
        )
    )
    if cursor is not None:
        after_distance, after_id = decode_cursor(cursor)
        query = query.where(
            or_(
                distance > after_distance,
                and_(distance == after_distance, Creator.id > after_id),
            )
        )
    rows = list(db.execute(query.order_by(distance, Creator.id).limit(limit + 1)).all())
    more = len(rows) > limit
    rows = rows[:limit]
    creators = [creator for creator, _ in rows]
    results = search_service.results_for(db, creators)
    closest = _closest_anchor(db, [c.id for c in creators], list(anchors))
    records = delivery_record.for_creators(db, [c.id for c in creators], now)
    return SimilarPage(
        based_on=len(anchors),
        rows=[
            SimilarCreator(
                result=result,
                similarity=round(1.0 - float(d), 4),
                closest_to=anchors[closest[creator.id]],
                delivery=records[creator.id],
            )
            for result, (creator, d) in zip(results, rows, strict=True)
        ],
        next_cursor=encode_cursor(float(rows[-1][1]), rows[-1][0].id) if more else None,
    )


def _anchor_ids(brand_id: uuid.UUID) -> Select[uuid.UUID]:
    return (
        select(Application.creator_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(DealMemo, DealMemo.application_id == Application.id)
        .where(finished_with(brand_id))
    )


def _worked_with(brand_id: uuid.UUID) -> Select[uuid.UUID]:
    """Every creator the brand has agreed a deal with, finished or not."""
    return (
        select(Application.creator_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(DealMemo, DealMemo.application_id == Application.id)
        .where(Campaign.brand_id == brand_id, DealMemo.accepted_at.is_not(None))
    )


def _closest_anchor(
    db: Session, creator_ids: list[uuid.UUID], anchor_ids: list[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Each creator's nearest anchor, in one query for the whole page."""
    if not creator_ids:
        return {}
    shown = aliased(CreatorEmbedding)
    anchor = aliased(CreatorEmbedding)
    rows = db.execute(
        select(shown.creator_id, anchor.creator_id)
        .join(anchor, anchor.creator_id.in_(anchor_ids))
        .where(shown.creator_id.in_(creator_ids))
        .ext(distinct_on(shown.creator_id))
        .order_by(
            shown.creator_id,
            shown.embedding.cosine_distance(anchor.embedding),
            anchor.creator_id,
        )
    ).all()
    return {shown_id: anchor_id for shown_id, anchor_id in rows}


def encode_cursor(distance: float, row_id: uuid.UUID) -> str:
    raw = f"{distance!r}{_SEPARATOR}{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[float, uuid.UUID]:
    """Raises InvalidCursor for anything malformed."""
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode()
        distance_text, row_id_text = raw.split(_SEPARATOR)
        return float(distance_text), uuid.UUID(row_id_text)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursor() from exc
