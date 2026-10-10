"""Brands invite creators; work together again (D-084).

Until 10 October 2026 every deal began with a creator applying. A brand that
found the right creator in search, or wanted the creator from its last deal
again, could only hope they applied. Now a brand invites a creator to one of
its open campaigns, and the creator accepts or declines in one tap.

An invitation is an `application` row with origin 'invited', so the rule of
one row per creator per campaign holds, and the memo, its stage and the
export work on it unchanged. Accepting needs nothing more from the creator:
the brand already chose them, so the row goes straight to accepted, as
impact.com's marketplace does (help.impact.com, read 10 October 2026).

A repeat ("work together again") is an invitation that names the earlier
deal. When the creator accepts it, the memo is drafted from that deal's
terms, ready for the brand to set the new date and send.

There is no expiry: an invitation lasts while its campaign is open, and
closing the campaign ends it, as accepting needs an open campaign. Some
platforms expire them after three days; a creator who answers on day four
should not find the offer gone while the campaign still runs.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.suspension import is_suspended
from app.modules.campaigns import service as campaigns
from app.modules.campaigns.exceptions import (
    AlreadyOnCampaign,
    CampaignNotOpen,
    CreatorNotFound,
    InvitationLimitReached,
)
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import service as deal_memos
from app.modules.notifications import service as notifications

# Unanswered invitations one campaign may have at once. Enough to invite a
# real shortlist; too few to spray every creator in a city, which is what
# makes creators stop reading invitations. A brand withdraws one to send
# another. A policy number, not a law: change it with a decision.
MAX_WAITING_INVITATIONS = 25


def invite_creator(
    db: Session,
    campaign: Campaign,
    creator_id: uuid.UUID,
    note: str | None,
    now: datetime,
    *,
    repeat_of_application_id: uuid.UUID | None = None,
) -> Application:
    """Invite one creator to one of the brand's own open campaigns.

    The campaign's row is locked first, so the count of waiting invitations
    and a close or cancel of the campaign cannot interleave with the write.
    Raises CampaignNotOpen, CreatorNotFound, InvitationLimitReached and
    AlreadyOnCampaign.
    """
    db.refresh(campaign, attribute_names=["status"], with_for_update=True)
    if campaign.status != "open":
        db.rollback()
        raise CampaignNotOpen()
    creator = db.get(Creator, creator_id)
    if creator is None or is_suspended(db, creator.account_id):
        db.rollback()
        raise CreatorNotFound()
    waiting = db.scalar(
        select(func.count()).where(
            Application.campaign_id == campaign.id, Application.status == "invited"
        )
    )
    if waiting is not None and waiting >= MAX_WAITING_INVITATIONS:
        db.rollback()
        raise InvitationLimitReached()

    invitation = Application(
        campaign_id=campaign.id,
        creator_id=creator.id,
        origin="invited",
        pitch=None,
        invitation_note=note,
        repeat_of_application_id=repeat_of_application_id,
        status="invited",
        status_changed_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(invitation)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if "uq_application_campaign_creator" in str(error):
            raise AlreadyOnCampaign() from error
        raise

    brand_name = db.scalar(select(Brand.name).where(Brand.id == campaign.brand_id))
    notifications.record(
        db,
        account_id=creator.account_id,
        notification_type="invitation_received",
        now=now,
        campaign_id=campaign.id,
        application_id=invitation.id,
        details={
            "campaign_title": campaign.title,
            "brand_name": brand_name,
            "repeat": repeat_of_application_id is not None,
        },
    )
    db.commit()
    db.refresh(invitation)
    return invitation


def accept_invitation(db: Session, invitation: Application, now: datetime) -> Application:
    """The creator says yes: accepted at once, and a repeat's memo drafted.

    One transaction: the acceptance, the brand's notification and the
    drafted memo exist together or not at all. Raises
    ApplicationStatusConflict and CampaignNotOpen.
    """
    campaigns.move_application(db, invitation, "accepted", now, actor="creator")
    if invitation.repeat_of_application_id is not None:
        deal_memos.draft_repeat_memo(db, invitation, now)
    db.commit()
    db.refresh(invitation)
    return invitation


def decline_invitation(
    db: Session, invitation: Application, reason: str, now: datetime
) -> Application:
    """The creator says no, with a reason the brand sees."""
    return campaigns.change_application_status(
        db, invitation, "declined", now, actor="creator", decline_reason=reason
    )


def withdraw_invitation(
    db: Session, invitation: Application, now: datetime
) -> Application:
    """The brand takes back an invitation not yet answered."""
    return campaigns.change_application_status(
        db, invitation, "withdrawn", now, actor="brand"
    )
