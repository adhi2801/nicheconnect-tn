"""A campaign at a glance: its applicants, its deals by stage, and whether it is done (D-076).

The campaign board in the website wireframes heads every campaign with "2 of
6 deals finished" and a Complete badge, and the Campaigns list shows the
same per row. Without this, both would read every application and every
deal and count them on the device.

Complete is worked out, never stored: the campaign is closed, at least one
deal was agreed, and every agreed deal has finished, with no memo still
waiting for an answer. A deal cancelled after it was agreed has ended
without finishing, so it does not count towards either side.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.campaigns.models import APPLICATION_STATUSES, Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.stage import (
    AGREED,
    DEAL_STAGES,
    DRAFT,
    FINISHED,
    IN_PROGRESS,
    MEMO_SENT,
    PAYMENT,
    stages_for,
)

# Agreed and not cancelled: the deals "n of m finished" counts.
AGREED_STAGES = frozenset({AGREED, IN_PROGRESS, PAYMENT, FINISHED})
# A memo nobody has finished answering keeps a campaign from being complete.
UNANSWERED_STAGES = frozenset({DRAFT, MEMO_SENT})


@dataclass(frozen=True)
class CampaignSummary:
    campaign_id: uuid.UUID
    status: str
    applications: dict[str, int]
    deals_by_stage: dict[str, int]
    deals_agreed: int
    deals_finished: int
    deals_waiting_on_brand: int
    complete: bool


def summarise(db: Session, campaign: Campaign, now: datetime) -> CampaignSummary:
    """One campaign's counts, in a fixed number of queries whatever its size."""
    applications = dict.fromkeys(APPLICATION_STATUSES, 0)
    for status, count in db.execute(
        select(Application.status, func.count())
        .where(Application.campaign_id == campaign.id)
        .group_by(Application.status)
    ):
        applications[status] = count

    memos = list(
        db.scalars(
            select(DealMemo)
            .join(Application, Application.id == DealMemo.application_id)
            .where(Application.campaign_id == campaign.id)
        )
    )
    stages = stages_for(db, memos, now).values()

    by_stage = dict.fromkeys(DEAL_STAGES, 0)
    for found in stages:
        by_stage[found.stage] += 1
    agreed = sum(by_stage[stage] for stage in AGREED_STAGES)
    finished = by_stage[FINISHED]
    unanswered = sum(by_stage[stage] for stage in UNANSWERED_STAGES)

    return CampaignSummary(
        campaign_id=campaign.id,
        status=campaign.status,
        applications=applications,
        deals_by_stage=by_stage,
        deals_agreed=agreed,
        deals_finished=finished,
        deals_waiting_on_brand=sum(1 for found in stages if found.waiting_on == "brand"),
        complete=(
            campaign.status == "closed"
            and agreed > 0
            and finished == agreed
            and unanswered == 0
        ),
    )
