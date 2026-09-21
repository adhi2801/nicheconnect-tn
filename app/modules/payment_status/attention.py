"""What in payment records is waiting on someone (see app/core/attention.py).

We never hold or move money (constraint 1). These items are about the
record: a brand saying it has paid, and a creator saying it arrived.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.attention import AttentionItem
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.payment_status.models import PaymentStatus
from app.modules.payment_status.service import confirmation_deadline


def for_brand(db: Session, brand_id: uuid.UUID) -> list[AttentionItem]:
    """Every payment the brand has not yet said it sent: due, late or unpaid.

    Kept even while a dispute is open about it: the payment is still owed.
    """
    return [
        AttentionItem(
            kind="pay_creator",
            due_on=payment.due_on,
            campaign_id=campaign_id,
            campaign_title=title,
            counterparty=handle,
            application_id=application_id,
            memo_id=payment.deal_memo_id,
            amount_paise=payment.amount_paise,
        )
        for payment, application_id, campaign_id, title, handle in db.execute(
            select(
                PaymentStatus, Application.id, Campaign.id, Campaign.title, Creator.handle
            )
            .join(DealMemo, DealMemo.id == PaymentStatus.deal_memo_id)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .join(Creator, Creator.id == Application.creator_id)
            .where(Campaign.brand_id == brand_id, PaymentStatus.marked_paid_at.is_(None))
        ).tuples()
    ]


def for_creator(db: Session, creator_id: uuid.UUID, today: date) -> list[AttentionItem]:
    """Money the brand says it sent, to confirm; and money past its due date.

    Confirming stays open after the window: a late confirmation is still a
    confirmation (D-033), so the item stays until it is given. A payment not
    yet due is not listed; there is nothing to do about it yet.
    """
    items: list[AttentionItem] = []
    for payment, application_id, campaign_id, title, brand_name in db.execute(
        select(PaymentStatus, Application.id, Campaign.id, Campaign.title, Brand.name)
        .join(DealMemo, DealMemo.id == PaymentStatus.deal_memo_id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(Application.creator_id == creator_id, PaymentStatus.confirmed_at.is_(None))
    ).tuples():
        if payment.marked_paid_at is not None:
            kind, due_on = "confirm_payment", confirmation_deadline(payment)
        elif today > payment.due_on:
            kind, due_on = "payment_overdue", payment.due_on
        else:
            continue
        items.append(
            AttentionItem(
                kind=kind,
                due_on=due_on,
                campaign_id=campaign_id,
                campaign_title=title,
                counterparty=brand_name,
                application_id=application_id,
                memo_id=payment.deal_memo_id,
                amount_paise=payment.amount_paise,
            )
        )
    return items
