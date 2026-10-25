"""What happens to campaigns and applications when their brand or creator leaves (item 6, D-122).

Deleting an account waits until every deal of the person is finished
(`deal_memo.unfinished`). What is left is what never became a deal, and it
is ended the way its owner could have ended it, with nobody notified:

- a brand that leaves: its open campaigns close, its drafts are cancelled,
  and its invitations still waiting are withdrawn;
- a creator who leaves: their applications still waiting are withdrawn, and
  invitations still waiting for them are declined, with the reason "other".

Campaigns and applications stay, as deal history the other side keeps
(choice 3A). Accepted applications are final and stay as they are; a memo
for one is refused once the creator has left (`deal_memo.service`).

Every application of the person is locked for update first, in id order,
after the profile and the campaigns: writing a memo locks its application,
so a memo lands wholly before the erasure, and holds it, or after, and is
refused. Nothing here commits.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.campaigns.models import Application, Campaign

# What ends, and how: the status each waiting status becomes.
BRAND_LEAVING: dict[str, str] = {"invited": "withdrawn"}
CREATOR_LEAVING: dict[str, str] = {
    "submitted": "withdrawn",
    "shortlisted": "withdrawn",
    "invited": "declined",
}
CAMPAIGN_LEAVING: dict[str, str] = {"draft": "cancelled", "open": "closed"}
# A creator who leaves declines an invitation with no reason of their own.
LEAVING_DECLINE_REASON = "other"


def lock_for_brand(db: Session, brand_id: uuid.UUID) -> list[Application]:
    """Lock the brand's campaigns, then every application to them, for update."""
    db.scalars(
        select(Campaign.id)
        .where(Campaign.brand_id == brand_id)
        .order_by(Campaign.id)
        .with_for_update()
    ).all()
    return list(
        db.scalars(
            select(Application)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .where(Campaign.brand_id == brand_id)
            .order_by(Application.id)
            .with_for_update(of=Application)
            .execution_options(populate_existing=True)
        ).all()
    )


def lock_for_creator(db: Session, creator_id: uuid.UUID) -> list[Application]:
    """Lock every application of the creator for update."""
    return list(
        db.scalars(
            select(Application)
            .where(Application.creator_id == creator_id)
            .order_by(Application.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )


def end_for_brand(
    db: Session, brand_id: uuid.UUID, applications: list[Application], now: datetime
) -> None:
    """Close and cancel the brand's campaigns, withdraw its waiting invitations."""
    campaigns = db.scalars(
        select(Campaign).where(
            Campaign.brand_id == brand_id,
            Campaign.status.in_(tuple(CAMPAIGN_LEAVING)),
        )
    ).all()
    for campaign in campaigns:
        campaign.status = CAMPAIGN_LEAVING[campaign.status]
        campaign.updated_at = now
    _end(applications, BRAND_LEAVING, now)


def end_for_creator(applications: list[Application], now: datetime) -> None:
    """Withdraw the creator's waiting applications, decline waiting invitations."""
    _end(applications, CREATOR_LEAVING, now)


def _end(applications: list[Application], moves: dict[str, str], now: datetime) -> None:
    for application in applications:
        new_status = moves.get(application.status)
        if new_status is None:
            continue
        application.status = new_status
        application.decline_reason = (
            LEAVING_DECLINE_REASON if new_status == "declined" else None
        )
        application.status_changed_at = now
        application.updated_at = now
