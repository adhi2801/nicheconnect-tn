"""A person's deals still in progress, which hold their account's deletion (item 6, D-122).

Deleting an account mid-deal would leave the other side without the person
they were working with, and would let a brand delete itself to avoid paying
(D-122, choice 1A, as Upwork requires closing contracts first). A deal is
finished when its stage (`stage.stage_of`) is finished, declined or
cancelled and no dispute about its payment is open. A draft or a memo
waiting for an answer counts as unfinished: someone is waiting on it, and
either side can cancel or decline it in one step.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import stage
from app.modules.deal_memo.models import DealMemo

DONE = frozenset({stage.FINISHED, stage.DECLINED, stage.CANCELLED})


def unfinished_deals(
    db: Session,
    now: datetime,
    *,
    brand_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """The ids of the brand's or the creator's unfinished deals. Four queries at most."""
    statement = select(DealMemo).join(
        Application, Application.id == DealMemo.application_id
    )
    if brand_id is not None:
        statement = statement.join(
            Campaign, Campaign.id == Application.campaign_id
        ).where(Campaign.brand_id == brand_id)
    elif creator_id is not None:
        statement = statement.where(Application.creator_id == creator_id)
    else:
        return []
    memos = list(db.scalars(statement).all())
    stages = stage.stages_for(db, memos, now)
    return sorted(
        (
            memo.id
            for memo in memos
            if stages[memo.id].stage not in DONE or stages[memo.id].has_open_dispute
        ),
        key=str,
    )
