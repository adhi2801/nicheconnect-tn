"""What in campaigns is waiting on someone (see app/core/attention.py)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.attention import AttentionItem
from app.modules.auth.models.brand import Brand
from app.modules.auth.suspension import brand_is_active
from app.modules.campaigns.models import Application, Campaign

# Applications still waiting for the brand's decision: shortlist or reject a
# new one, accept or reject a shortlisted one.
AWAITING_DECISION = ("submitted", "shortlisted")


def for_brand(db: Session, brand_id: uuid.UUID) -> list[AttentionItem]:
    """One item per campaign with applications waiting, with how many.

    One item per campaign rather than per application: fifty applicants are
    one job, and fifty rows would bury everything else. A cancelled campaign
    is left out; its applications are no longer anybody's to decide.
    """
    rows = db.execute(
        select(Campaign.id, Campaign.title, func.count(Application.id))
        .join(Application, Application.campaign_id == Campaign.id)
        .where(
            Campaign.brand_id == brand_id,
            Campaign.status.in_(("open", "closed")),
            Application.status.in_(AWAITING_DECISION),
        )
        .group_by(Campaign.id, Campaign.title)
    ).tuples()
    return [
        AttentionItem(
            kind="review_applications",
            due_on=None,
            campaign_id=campaign_id,
            campaign_title=title,
            count=waiting,
        )
        for campaign_id, title, waiting in rows
    ]


def for_creator(db: Session, creator_id: uuid.UUID) -> list[AttentionItem]:
    """One item per invitation waiting for this creator's answer (D-084).

    One per invitation, not a count: each is a different brand asking, and
    each is answered on its own. Only those that can still be accepted: the
    campaign open and its brand not suspended.
    """
    rows = db.execute(
        select(Application.id, Campaign.id, Campaign.title, Brand.name)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(
            Application.creator_id == creator_id,
            Application.status == "invited",
            Campaign.status == "open",
            brand_is_active(Campaign.brand_id),
        )
    ).tuples()
    return [
        AttentionItem(
            kind="answer_invitation",
            due_on=None,
            campaign_id=campaign_id,
            campaign_title=title,
            counterparty=brand_name,
            application_id=application_id,
        )
        for application_id, campaign_id, title, brand_name in rows
    ]
