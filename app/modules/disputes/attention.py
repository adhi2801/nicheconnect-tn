"""Disputes waiting on someone's side of the story (see app/core/attention.py).

D-028: the side that did not raise a dispute has until `response_due_on` to
put its account on the record. The item asks for exactly that, nothing more:
we record, we never judge, so there is no "resolve this" item for anybody.
"""

import uuid
from datetime import date

from sqlalchemy import ColumnElement, exists, select
from sqlalchemy.orm import QueryableAttribute, Session

from app.core.attention import AttentionItem
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.disputes.event_models import DisputeEvent
from app.modules.disputes.models import Dispute
from app.modules.disputes.service import is_open
from app.modules.payment_status.models import PaymentStatus


def for_brand(db: Session, brand_id: uuid.UUID, today: date) -> list[AttentionItem]:
    return _awaiting(
        db, "brand", today, Campaign.brand_id == brand_id, counterparty=Creator.handle
    )


def for_creator(db: Session, creator_id: uuid.UUID, today: date) -> list[AttentionItem]:
    return _awaiting(
        db,
        "creator",
        today,
        Application.creator_id == creator_id,
        counterparty=Brand.name,
    )


def _awaiting(
    db: Session,
    role: str,
    today: date,
    whose: ColumnElement[bool],
    *,
    counterparty: QueryableAttribute[str],
) -> list[AttentionItem]:
    """Live disputes the other side raised, where `role` has said nothing yet."""
    has_spoken = exists().where(
        DisputeEvent.dispute_id == Dispute.id, DisputeEvent.actor_role == role
    )
    rows = db.execute(
        select(
            Dispute,
            DealMemo.id,
            Application.id,
            Campaign.id,
            Campaign.title,
            counterparty,
        )
        .join(PaymentStatus, PaymentStatus.id == Dispute.payment_status_id)
        .join(DealMemo, DealMemo.id == PaymentStatus.deal_memo_id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Creator, Creator.id == Application.creator_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(whose, Dispute.opened_by != role, Dispute.outcome.is_(None), ~has_spoken)
    ).tuples()
    return [
        AttentionItem(
            kind="respond_to_dispute",
            due_on=dispute.response_due_on,
            campaign_id=campaign_id,
            campaign_title=title,
            counterparty=other,
            application_id=application_id,
            memo_id=memo_id,
        )
        for dispute, memo_id, application_id, campaign_id, title, other in rows
        # Past its 30 days it is `unresolved`: a fact, and nothing left to answer.
        if is_open(dispute, today)
    ]
