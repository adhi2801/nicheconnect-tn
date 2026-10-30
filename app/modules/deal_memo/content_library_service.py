"""A brand's content library (item 70, D-132): every approved post, and its rights.

Worked out, never stored (backend.md section 2): the library is the brand's
approved proofs, each with the usage window its accepted memo sealed
(`usage_rights_days`), counted from the Tamil Nadu day the work was
approved. A window the memo left empty reads `not_agreed`, never a guess.
What the window means in law is a Confirm item (legal.md section 3.11):
the library states the memo's terms, never a right.

Approval by the clock is written lazily, when a submission is next read
(`proof_service.settle_if_overdue`), so the brand's overdue submissions are
settled before a page is read, and the library never depends on whether
anyone happened to look at the deal.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import ColumnElement, Date, and_, cast, literal, select, text
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import proof_service
from app.modules.deal_memo.content_rights import (
    LAPSING_WITHIN_DAYS,
    RightsState,
    rights_state,
    rights_until,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof


@dataclass(frozen=True)
class LibraryItem:
    proof: DeliverableProof
    memo: DealMemo
    campaign_id: object
    campaign_title: str
    creator_id: object
    creator_handle: str
    rights_until: date | None
    rights_state: RightsState


def page(
    db: Session,
    brand: Brand,
    now: datetime,
    *,
    limit: int,
    cursor: str | None,
    state: RightsState | None = None,
) -> Slice[LibraryItem]:
    """The brand's approved posts, latest approved first, in keyset pages.

    Two queries a page, whatever its size, once nothing waits: one for
    submissions still waiting, one for the page. Three while any wait, the
    third reading their deals' submissions at once; proof waiting on a deal
    cancelled before its window closed waits for good (D-146), and costs no
    query of its own.
    """
    _settle_overdue(db, brand, now)
    today = india_date(now)
    query = (
        select(
            DeliverableProof,
            DealMemo,
            Campaign.id,
            Campaign.title,
            Creator.id,
            Creator.handle,
        )
        .join(DealMemo, DealMemo.id == DeliverableProof.deal_memo_id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Creator, Creator.id == Application.creator_id)
        .where(Campaign.brand_id == brand.id, DeliverableProof.status == "approved")
    )
    if state is not None:
        query = query.where(_in_state(state, today))
    if cursor is not None:
        query = query.where(
            older_than_cursor(DeliverableProof.approved_at, DeliverableProof.id, cursor)  # type: ignore[arg-type]
        )
    rows = list(
        db.execute(
            query.order_by(
                DeliverableProof.approved_at.desc(), DeliverableProof.id.desc()
            ).limit(limit + 1)
        ).all()
    )
    page_rows = build_slice(
        rows, limit, key=lambda row: (_approved_at(row[0]), row[0].id)
    )
    items = []
    for proof, memo, campaign_id, title, creator_id, handle in page_rows.rows:
        until = rights_until(_approved_at(proof), memo.usage_rights_days)
        items.append(
            LibraryItem(
                proof=proof,
                memo=memo,
                campaign_id=campaign_id,
                campaign_title=title,
                creator_id=creator_id,
                creator_handle=handle,
                rights_until=until,
                rights_state=rights_state(until, today),
            )
        )
    return Slice(rows=items, next_cursor=page_rows.next_cursor)


def _until_sql() -> ColumnElement[date]:
    """`rights_until` in SQL: the approval's Tamil Nadu day plus the days."""
    return cast(
        cast(DeliverableProof.approved_at + text("interval '5 hours 30 minutes'"), Date)
        + DealMemo.usage_rights_days,
        Date,
    )


def _in_state(state: RightsState, today: date) -> ColumnElement[bool]:
    """`rights_state(...) == state`, asked in SQL."""
    until = _until_sql()
    lapsing_by = today + timedelta(days=LAPSING_WITHIN_DAYS)
    if state == "not_agreed":
        return DealMemo.usage_rights_days.is_(None)
    agreed = DealMemo.usage_rights_days.is_not(None)
    if state == "lapsed":
        return and_(agreed, until <= literal(today))
    if state == "lapsing":
        return and_(agreed, until > literal(today), until <= literal(lapsing_by))
    return and_(agreed, until > literal(lapsing_by))


def _settle_overdue(db: Session, brand: Brand, now: datetime) -> None:
    """Approve, by the clock, the brand's submissions whose window has passed."""
    waiting = list(
        db.execute(
            select(DeliverableProof, DealMemo)
            .join(DealMemo, DealMemo.id == DeliverableProof.deal_memo_id)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .where(Campaign.brand_id == brand.id, DeliverableProof.status == "submitted")
        ).all()
    )
    if not waiting:
        return
    histories: dict[uuid.UUID, list[DeliverableProof]] = {}
    for earlier in db.scalars(
        select(DeliverableProof).where(
            DeliverableProof.deal_memo_id.in_({memo.id for _, memo in waiting})
        )
    ):
        histories.setdefault(earlier.deal_memo_id, []).append(earlier)
    for proof, memo in waiting:
        proof_service.settle_if_overdue(db, memo, proof, now, history=histories[memo.id])


def _approved_at(proof: DeliverableProof) -> datetime:
    # Only approved proofs are read, and an approved proof has its time.
    if proof.approved_at is None:
        raise ValueError(f"approved proof {proof.id} has no approval time")
    return proof.approved_at
