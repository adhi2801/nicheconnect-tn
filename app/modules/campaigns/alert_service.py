"""Campaign alerts (item 43, D-130): the rules.

A creator keeps up to MAX_ALERTS_PER_CREATOR alerts, counted under the
creator's row lock so two saved at once cannot both pass the cap; the
same terms twice are refused by the database's unique index.

Publishing a campaign queues it (`queue`, inside the publishing
transaction), and the every-minute job (`alert_jobs`) sends what is due
(`send_due`). Sending is batched, BATCH_SIZE creators a transaction, each
transaction under one advisory lock, so batches never run side by side:
the daily cap (MAX_ALERTS_A_DAY) is then counted from what earlier
batches committed, and cannot be passed by two campaigns sent at once. A
batch records a notification only for a creator not yet told about this
campaign, so a run cut short, or run twice, never tells anyone twice.

Nobody is told about a campaign they could not act on (trust-and-safety.md
rule 7): not by a suspended, deleted or withheld brand, nor of a campaign
withheld, closed or cancelled before its turn; not a suspended, deleted or
withheld creator; not across a block either way; and never the brand's
own other side (D-126), whose deals with it are refused anyway.
"""

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy import (
    ColumnElement,
    delete,
    exists,
    func,
    insert,
    literal,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.core.clock import IST, india_date
from app.core.export import ExportedSection, allow, build_section
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.suspension import account_is_active, brand_is_active
from app.modules.campaigns.alert_models import (
    MAX_ALERTS_A_DAY,
    MAX_ALERTS_PER_CREATOR,
    CampaignAlert,
    CampaignAlertSend,
)
from app.modules.campaigns.exceptions import (
    CampaignAlertExists,
    CampaignAlertNotFound,
    CampaignAlertsFull,
)
from app.modules.campaigns.models import Campaign
from app.modules.notifications.models import Notification
from app.modules.safety.blocks import not_blocked_with_brand
from app.modules.safety.takedowns import campaign_not_withheld, not_withheld

logger = logging.getLogger(__name__)

ALERT_TYPE = "campaign_alert"
BATCH_SIZE = 500
# Sends started in one run; the rest wait for the next minute.
SENDS_PER_RUN = 20
LOCK_KEY = "campaign_alerts.send"

EXPORTED_TABLES = frozenset({"campaign_alert"})
EXPORT_FIELDS = allow(
    "id",
    "city",
    "niche",
    "campaign_type",
    "min_budget_paise",
    "currency",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class AlertRun:
    sends: int
    notified: int


# --- the creator's alerts ---------------------------------------------------


def alerts_of(db: Session, creator: Creator) -> list[CampaignAlert]:
    """The creator's alerts, newest first. Whole: at most MAX_ALERTS_PER_CREATOR."""
    return list(
        db.scalars(
            select(CampaignAlert)
            .where(CampaignAlert.creator_id == creator.id)
            .order_by(CampaignAlert.created_at.desc(), CampaignAlert.id.desc())
        ).all()
    )


def create(
    db: Session,
    creator: Creator,
    *,
    city: str | None,
    niche: str | None,
    campaign_type: str | None,
    min_budget_paise: int | None,
    now: datetime,
) -> CampaignAlert:
    """Save an alert. Commits. Raises CampaignAlertsFull and CampaignAlertExists."""
    db.scalars(select(Creator.id).where(Creator.id == creator.id).with_for_update()).one()
    count = db.scalar(select(func.count()).where(CampaignAlert.creator_id == creator.id))
    if count is not None and count >= MAX_ALERTS_PER_CREATOR:
        db.rollback()
        raise CampaignAlertsFull()
    alert = CampaignAlert(
        creator_id=creator.id,
        city=city,
        niche=niche,
        campaign_type=campaign_type,
        min_budget_paise=min_budget_paise,
        created_at=now,
        updated_at=now,
    )
    db.add(alert)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if "uq_campaign_alert_terms" not in str(error):
            raise
        raise CampaignAlertExists() from None
    db.commit()
    db.refresh(alert)
    return alert


def remove(db: Session, creator: Creator, alert_id: uuid.UUID) -> None:
    """Remove one of the creator's alerts. Commits. Raises CampaignAlertNotFound."""
    removed = db.execute(
        delete(CampaignAlert)
        .where(CampaignAlert.id == alert_id, CampaignAlert.creator_id == creator.id)
        .returning(CampaignAlert.id)
    ).first()
    if removed is None:
        raise CampaignAlertNotFound()
    db.commit()


# --- publishing and sending -------------------------------------------------


def queue(db: Session, campaign: Campaign, now: datetime) -> None:
    """Mark the campaign's alerts due. Inside the publishing transaction; never commits."""
    db.add(CampaignAlertSend(campaign_id=campaign.id, queued_at=now))


def send_due(
    session_factory: Callable[[], AbstractContextManager[Session]], now: datetime
) -> AlertRun:
    """One run of the job: send up to SENDS_PER_RUN due campaigns, oldest first."""
    with session_factory() as db:
        due = list(
            db.scalars(
                select(CampaignAlertSend.id)
                .where(CampaignAlertSend.sent_at.is_(None))
                .order_by(CampaignAlertSend.queued_at, CampaignAlertSend.id)
                .limit(SENDS_PER_RUN)
            ).all()
        )
    notified = 0
    for send_id in due:
        notified += send_one(session_factory, send_id, now)
    logger.info("campaign_alerts.run sends=%d notified=%d", len(due), notified)
    return AlertRun(sends=len(due), notified=notified)


def send_one(
    session_factory: Callable[[], AbstractContextManager[Session]],
    send_id: uuid.UUID,
    now: datetime,
) -> int:
    """Send one campaign's alerts, a batch a transaction, until none is left."""
    told = 0
    while True:
        with session_factory() as db:
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": LOCK_KEY},
            )
            send = db.scalars(
                select(CampaignAlertSend)
                .where(CampaignAlertSend.id == send_id)
                # Read afresh: a run that held the lock first may have sent it.
                .execution_options(populate_existing=True)
            ).one()
            if send.sent_at is not None:
                db.rollback()
                return told
            campaign = db.get_one(Campaign, send.campaign_id)
            batch = _notify_batch(db, campaign, now) if _still_fits(db, campaign) else 0
            told += batch
            if batch < BATCH_SIZE:
                send.recipients = db.scalar(
                    select(func.count()).where(
                        Notification.campaign_id == campaign.id,
                        Notification.notification_type == ALERT_TYPE,
                    )
                )
                send.sent_at = now
                send.updated_at = now
                logger.info(
                    "campaign_alerts.sent campaign_id=%s recipients=%d",
                    campaign.id,
                    send.recipients,
                )
            db.commit()
            if batch < BATCH_SIZE:
                return told


def _still_fits(db: Session, campaign: Campaign) -> bool:
    """Still open, from a brand neither suspended, deleted nor withheld."""
    return (
        db.scalar(
            select(Campaign.id).where(
                Campaign.id == campaign.id,
                Campaign.status == "open",
                brand_is_active(Campaign.brand_id),
                campaign_not_withheld(Campaign.id, Campaign.brand_id),
            )
        )
        is not None
    )


def _notify_batch(db: Session, campaign: Campaign, now: datetime) -> int:
    """Tell up to BATCH_SIZE more creators whose alert fits. One statement."""
    brand_account_id, brand_phone = db.execute(
        select(Brand.account_id, Account.phone)
        .join(Account, Account.id == Brand.account_id)
        .where(Brand.id == campaign.brand_id)
    ).one()
    told = aliased(Notification)
    today = aliased(Notification)
    # Aliased, so the EXISTS checks below on `account` stay their own.
    creator_account = aliased(Account)
    day_start = datetime.combine(india_date(now), time.min, tzinfo=IST)
    conditions = [
        *fits(campaign),
        account_is_active(Creator.account_id),
        not_withheld("creator", Creator.id),
        not_blocked_with_brand(Creator.account_id, literal(campaign.brand_id)),
        # Never the brand's own other side (D-126).
        Creator.account_id != brand_account_id,
        or_(
            literal(brand_phone).is_(None),
            creator_account.phone.is_distinct_from(brand_phone),
        ),
        # Once per campaign, however often this runs.
        ~exists().where(
            told.account_id == Creator.account_id,
            told.campaign_id == campaign.id,
            told.notification_type == ALERT_TYPE,
        ),
        # At most MAX_ALERTS_A_DAY a Tamil Nadu day.
        select(func.count())
        .where(
            today.account_id == Creator.account_id,
            today.notification_type == ALERT_TYPE,
            today.created_at >= day_start,
        )
        .scalar_subquery()
        < MAX_ALERTS_A_DAY,
    ]
    recipients = (
        select(
            Creator.account_id,
            literal(ALERT_TYPE),
            literal(campaign.id),
            func.jsonb_build_object("alert_id", CampaignAlert.id),
            literal(now),
            literal(now),
        )
        .select_from(CampaignAlert)
        .join(Creator, Creator.id == CampaignAlert.creator_id)
        .join(creator_account, creator_account.id == Creator.account_id)
        .where(*conditions)
        .ext(distinct_on(Creator.id))
        .order_by(Creator.id, CampaignAlert.created_at, CampaignAlert.id)
        .limit(BATCH_SIZE)
    )
    added = db.execute(
        insert(Notification)
        .from_select(
            [
                "account_id",
                "notification_type",
                "campaign_id",
                "details",
                "created_at",
                "updated_at",
            ],
            recipients,
        )
        .returning(Notification.id)
    ).all()
    return len(added)


def fits(campaign: Campaign) -> list[ColumnElement[bool]]:
    """`alert_rules.matches`, asked in SQL of every alert at once."""
    budget = (
        CampaignAlert.min_budget_paise.is_(None)
        if campaign.budget_max_paise is None
        else or_(
            CampaignAlert.min_budget_paise.is_(None),
            CampaignAlert.min_budget_paise <= campaign.budget_max_paise,
        )
    )
    return [
        or_(
            CampaignAlert.city.is_(None),
            func.lower(CampaignAlert.city).in_(
                [func.lower(literal(city)) for city in campaign.cities]
            ),
        ),
        or_(CampaignAlert.niche.is_(None), CampaignAlert.niche.in_(campaign.niches)),
        or_(
            CampaignAlert.campaign_type.is_(None),
            CampaignAlert.campaign_type == campaign.campaign_type,
        ),
        budget,
    ]


# --- the export and deletion ------------------------------------------------


def erase_for_creator(db: Session, creator_id: uuid.UUID) -> None:
    """On deleting the account (D-122): the creator's alerts. Never commits."""
    db.execute(delete(CampaignAlert).where(CampaignAlert.creator_id == creator_id))


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """A creator's alerts; a brand has none."""
    alerts = list(
        db.scalars(
            select(CampaignAlert)
            .join(Creator, Creator.id == CampaignAlert.creator_id)
            .where(Creator.account_id == account_id)
            .order_by(CampaignAlert.created_at, CampaignAlert.id)
        ).all()
    )
    return [
        build_section(
            "campaign_alerts",
            table="campaign_alert",
            purpose="The alerts you saved, to hear when a campaign fits them.",
            objects=alerts,
            fields=EXPORT_FIELDS,
        )
    ]
