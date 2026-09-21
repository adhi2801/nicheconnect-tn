"""What in campaigns is waiting on a brand (see app/core/attention.py)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.attention import AttentionItem
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
