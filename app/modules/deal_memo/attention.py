"""What in deal memos and proof is waiting on someone (see app/core/attention.py).

Due dates come from the deal itself. A memo with an agreed date cannot be
sent or accepted once that date has passed (D-039), so answering or
revising it is due by then. Work is due by the agreed date. A brand's
review is due by the moment the proof approves itself (D-025).
"""

import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.attention import AttentionItem
from app.core.clock import india_date
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.delivery_record import is_approved
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.proof_service import approval_deadline


def for_brand(db: Session, brand_id: uuid.UUID, now: datetime) -> list[AttentionItem]:
    """Memos to draft or revise, and proof to review, in three queries."""
    items: list[AttentionItem] = []

    # Accepted, and nobody has written the memo yet.
    for application_id, campaign_id, title, handle in db.execute(
        select(Application.id, Campaign.id, Campaign.title, Creator.handle)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Creator, Creator.id == Application.creator_id)
        .outerjoin(DealMemo, DealMemo.application_id == Application.id)
        .where(
            Campaign.brand_id == brand_id,
            Application.status == "accepted",
            DealMemo.id.is_(None),
        )
    ).tuples():
        items.append(
            AttentionItem(
                kind="draft_memo",
                due_on=None,
                campaign_id=campaign_id,
                campaign_title=title,
                counterparty=handle,
                application_id=application_id,
            )
        )

    # The creator asked for a change; the memo is back with the brand.
    for memo_id, due_on, application_id, campaign_id, title, handle in db.execute(
        select(
            DealMemo.id,
            DealMemo.content_due_on,
            Application.id,
            Campaign.id,
            Campaign.title,
            Creator.handle,
        )
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Creator, Creator.id == Application.creator_id)
        .where(Campaign.brand_id == brand_id, DealMemo.status == "change_requested")
    ).tuples():
        items.append(
            AttentionItem(
                kind="revise_memo",
                due_on=due_on,
                campaign_id=campaign_id,
                campaign_title=title,
                counterparty=handle,
                application_id=application_id,
                memo_id=memo_id,
            )
        )

    # Proof waiting for a decision, until it approves itself.
    for proof, memo, campaign_id, title, handle in db.execute(
        select(DeliverableProof, DealMemo, Campaign.id, Campaign.title, Creator.handle)
        .join(DealMemo, DealMemo.id == DeliverableProof.deal_memo_id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Creator, Creator.id == Application.creator_id)
        .where(
            Campaign.brand_id == brand_id,
            DealMemo.status == "accepted",
            DeliverableProof.status == "submitted",
        )
    ).tuples():
        deadline = approval_deadline(memo, proof)
        if now >= deadline:
            continue  # already approved by the clock; nothing left to decide
        items.append(
            AttentionItem(
                kind="review_proof",
                due_on=india_date(deadline),
                campaign_id=campaign_id,
                campaign_title=title,
                counterparty=handle,
                application_id=memo.application_id,
                memo_id=memo.id,
                proof_id=proof.id,
            )
        )
    return items


def for_creator(db: Session, creator_id: uuid.UUID, now: datetime) -> list[AttentionItem]:
    """Memos to answer, and work to deliver or redo, in three queries."""
    items: list[AttentionItem] = []

    for memo_id, due_on, application_id, campaign_id, title, brand_name in db.execute(
        select(
            DealMemo.id,
            DealMemo.content_due_on,
            Application.id,
            Campaign.id,
            Campaign.title,
            Brand.name,
        )
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(Application.creator_id == creator_id, DealMemo.status == "sent")
    ).tuples():
        items.append(
            AttentionItem(
                kind="answer_memo",
                due_on=due_on,
                campaign_id=campaign_id,
                campaign_title=title,
                counterparty=brand_name,
                application_id=application_id,
                memo_id=memo_id,
            )
        )

    accepted = list(
        db.execute(
            select(DealMemo, Campaign.id, Campaign.title, Brand.name)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .join(Brand, Brand.id == Campaign.brand_id)
            .where(Application.creator_id == creator_id, DealMemo.status == "accepted")
        ).tuples()
    )
    proofs: dict[uuid.UUID, list[DeliverableProof]] = defaultdict(list)
    if accepted:
        for proof in db.scalars(
            select(DeliverableProof)
            .where(DeliverableProof.deal_memo_id.in_([memo.id for memo, *_ in accepted]))
            .order_by(DeliverableProof.created_at, DeliverableProof.id)
        ):
            proofs[proof.deal_memo_id].append(proof)

    for memo, campaign_id, title, brand_name in accepted:
        kind = _work_waiting(memo, proofs[memo.id], now)
        if kind is None:
            continue
        items.append(
            AttentionItem(
                kind=kind,
                due_on=memo.content_due_on,
                campaign_id=campaign_id,
                campaign_title=title,
                counterparty=brand_name,
                application_id=memo.application_id,
                memo_id=memo.id,
            )
        )
    return items


def _work_waiting(
    memo: DealMemo, proofs: list[DeliverableProof], now: datetime
) -> str | None:
    """What an accepted deal still needs from the creator, if anything."""
    if any(is_approved(memo, proof, now) for proof in proofs):
        return None  # delivered
    if any(proof.status == "submitted" for proof in proofs):
        return None  # waiting on the brand, not the creator
    if proofs and proofs[-1].status == "revision_requested":
        return "resubmit_work"
    return "deliver_work"
