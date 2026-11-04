"""Who applied, in one call (R2 of docs/PROPOSAL_FRONTEND_API_REQUESTS.md).

A brand's board shows every applicant's name, city, niches and how they
deliver; fetching each from the media kit would be twenty calls a page. The
same facts a saved list shows (D-129), never a phone number, and only on
the brand's own campaign (`OwnedCampaign`), so no creator ever reads
another's through it.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models.creator import Creator
from app.modules.campaigns import offer_service as offers
from app.modules.campaigns.applicant_schemas import ApplicantRead, BrandApplicationRead
from app.modules.campaigns.models import Application
from app.modules.deal_memo import delivery_record
from app.modules.deal_memo.schemas import to_delivery_read

# Those who came forward and are the brand's to decide on, or were decided
# on: never an invitation still waiting, one declined, or one withdrawn.
# Each one an allowed status: `test_applicant_summary_api.py` holds them to APPLICATION_STATUSES.
APPLICANT_STATUSES = ("submitted", "shortlisted", "accepted", "rejected")


def read_for_brand(
    db: Session, applications: list[Application], now: datetime
) -> list[BrandApplicationRead]:
    """Applications with their creators, in a fixed number of queries whatever the page.

    The offers (one), the creators (one), their delivery records (two or three).
    """
    reads = offers.read_applications(db, applications)
    ids = list({application.creator_id for application in applications})
    if not ids:
        return []
    creators = {
        creator.id: creator
        for creator in db.scalars(select(Creator).where(Creator.id.in_(ids)))
    }
    records = delivery_record.for_creators(db, ids, now)
    return [
        BrandApplicationRead(
            **read.model_dump(),
            creator=ApplicantRead(
                creator_id=creator.id,
                handle=creator.handle,
                display_name=creator.display_name,
                city=creator.city,
                niches=list(creator.niches),
                delivery=to_delivery_read(records[creator.id]),
            ),
        )
        for read, creator in (
            (read, creators[application.creator_id])
            for read, application in zip(reads, applications, strict=True)
        )
    ]


def applicant_counts(db: Session, campaign_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """How many came forward to each campaign. One query for the page."""
    if not campaign_ids:
        return {}
    rows = db.execute(
        select(Application.campaign_id, func.count())
        .where(
            Application.campaign_id.in_(campaign_ids),
            Application.status.in_(APPLICANT_STATUSES),
        )
        .group_by(Application.campaign_id)
    ).all()
    counts = {campaign_id: count for campaign_id, count in rows}
    return {campaign_id: counts.get(campaign_id, 0) for campaign_id in campaign_ids}
