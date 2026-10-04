"""Every payment across a brand's or a creator's deals, in two calls (D-075).

Until now a Payments screen had to list the deals, then read each deal's
payment one by one: one call per row, which `docs/standards/ux.md` section 7
calls a backend request. These two queries answer the whole screen: the
list, filtered to what the screen is showing, and the totals across all of it.

Each row carries the deal's context (the campaign, the creator, the brand),
read in the same query, so a list of fifty payments is one round trip.

A list never decides anything: every state is worked out as it is for a
single payment (service.derive_state), against the same day.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.payment_status.models import PaymentStatus

# The three questions a Payments screen asks, and the rows that answer each.
# Every payment is in exactly one of them.
VIEWS: dict[str, ColumnElement[bool]] = {
    # The brand has not said it paid yet: due, late or unpaid.
    "to_pay": PaymentStatus.marked_paid_at.is_(None),
    # Said to be sent, not yet confirmed as arrived.
    "awaiting_confirmation": and_(
        PaymentStatus.marked_paid_at.is_not(None), PaymentStatus.confirmed_at.is_(None)
    ),
    # The creator confirmed it arrived. Nothing more will happen.
    "finished": PaymentStatus.confirmed_at.is_not(None),
}


@dataclass(frozen=True)
class PaymentRow:
    """One payment and the deal it belongs to."""

    payment: PaymentStatus
    campaign_id: uuid.UUID
    campaign_title: str
    creator_id: uuid.UUID
    creator_handle: str
    creator_display_name: str
    brand_id: uuid.UUID
    brand_name: str


@dataclass(frozen=True)
class Bucket:
    count: int
    amount_paise: int


@dataclass(frozen=True)
class PaymentTotals:
    to_pay: Bucket
    overdue: Bucket
    awaiting_confirmation: Bucket
    finished: Bucket


def _for_party[Row: tuple[object, ...]](
    query: Select[Row], party: Brand | Creator
) -> Select[Row]:
    """Only the payments on this brand's campaigns, or this creator's deals."""
    query = (
        query.join(DealMemo, DealMemo.id == PaymentStatus.deal_memo_id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
    )
    if isinstance(party, Brand):
        return query.where(Campaign.brand_id == party.id)
    return query.where(Application.creator_id == party.id)


def list_payments(
    db: Session,
    party: Brand | Creator,
    *,
    view: str | None,
    limit: int,
    cursor: str | None = None,
) -> Slice[PaymentRow]:
    """This party's payments, newest first, optionally one view of them."""
    query = _for_party(
        select(
            PaymentStatus,
            Campaign.id,
            Campaign.title,
            Creator.id,
            Creator.handle,
            Creator.display_name,
            Brand.id,
            Brand.name,
        ),
        party,
    )
    query = query.join(Creator, Creator.id == Application.creator_id).join(
        Brand, Brand.id == Campaign.brand_id
    )
    if view is not None:
        query = query.where(VIEWS[view])
    if cursor is not None:
        query = query.where(
            older_than_cursor(PaymentStatus.created_at, PaymentStatus.id, cursor)
        )
    found = db.execute(
        query.order_by(PaymentStatus.created_at.desc(), PaymentStatus.id.desc()).limit(
            limit + 1
        )
    ).all()
    rows = [PaymentRow(*row) for row in found]
    return build_slice(
        rows, limit, key=lambda row: (row.payment.created_at, row.payment.id)
    )


def totals(db: Session, party: Brand | Creator, today: date) -> PaymentTotals:
    """How many payments, and how much, in each view, in one query.

    `overdue` is the part of `to_pay` past its due date, so it is always
    shown and never hidden inside a bigger number (D-027).
    """
    overdue = and_(VIEWS["to_pay"], PaymentStatus.due_on < today)
    conditions = {
        "to_pay": VIEWS["to_pay"],
        "overdue": overdue,
        "awaiting_confirmation": VIEWS["awaiting_confirmation"],
        "finished": VIEWS["finished"],
    }
    columns: list[ColumnElement[int]] = []
    for condition in conditions.values():
        columns.append(func.count().filter(condition))
        columns.append(
            func.coalesce(func.sum(PaymentStatus.amount_paise).filter(condition), 0)
        )
    row = db.execute(_for_party(select(*columns).select_from(PaymentStatus), party)).one()
    buckets = [
        Bucket(count=int(row[index]), amount_paise=int(row[index + 1]))
        for index in range(0, len(row), 2)
    ]
    return PaymentTotals(*buckets)
