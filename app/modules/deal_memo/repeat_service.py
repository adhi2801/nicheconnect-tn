"""Work together again: a deal repeated in one tap (D-084).

Repeat deals are where a marketplace's value compounds, and "this creator
delivered on time" is already our own record (D-038). The brand picks a
finished or running deal and one of its open campaigns; the creator gets an
invitation saying it is a repeat; accepting drafts the memo from the earlier
deal's terms (`service.draft_repeat_memo`). Nothing is copied before the
creator says yes, so a declined repeat leaves nothing behind.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models.brand import Brand
from app.modules.campaigns import invitation_service as invitations
from app.modules.campaigns.exceptions import CampaignNotFound
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import service as deal_memos
from app.modules.deal_memo.models import DealMemo


def repeat_deal(
    db: Session,
    memo: DealMemo,
    brand: Brand,
    campaign_id: uuid.UUID,
    note: str | None,
    now: datetime,
) -> Application:
    """Invite the creator of `memo` to `campaign_id`, as a repeat of it.

    `memo` is already known to be on one of this brand's campaigns. The new
    campaign must be the brand's own too: another brand's gives 404, never
    403, so its existence stays private. Raises CampaignNotFound,
    MemoStatusConflict, the fee errors, and everything invite_creator raises.
    """
    campaign = db.scalars(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.brand_id == brand.id)
    ).first()
    if campaign is None:
        raise CampaignNotFound()
    deal_memos.check_repeatable(memo, campaign)
    earlier = db.get_one(Application, memo.application_id)
    return invitations.invite_creator(
        db,
        campaign,
        earlier.creator_id,
        note,
        now,
        repeat_of_application_id=earlier.id,
    )
