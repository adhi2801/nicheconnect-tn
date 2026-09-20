"""Campaign rules (D-016). One service call is one unit of work.

Status flow:

    draft ──publish──> open ──close──> closed
      │                  │
      └────cancel────────┴──> cancelled

Nothing reopens a closed or cancelled campaign; posting again means a new
campaign, so a creator's application history always points at what they saw.
"""

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ExportedSection,
    allow,
    build_section,
)
from app.core.pagination import Slice, build_slice, decode_cursor
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.exceptions import (
    AlreadyApplied,
    ApplicationsClosed,
    ApplicationStatusConflict,
    BrandProfileRequired,
    CampaignNotEditable,
    CampaignNotFound,
    CampaignNotOpen,
    CampaignStatusConflict,
    CreatorProfileRequired,
    FieldNotEditableNow,
)
from app.modules.campaigns.models import Application, Campaign
from app.modules.notifications import service as notifications

# Tables this module answers for in a data export (see
# tests/modules/auth/test_export_api.py, which fails if one is missed).
EXPORTED_TABLES = frozenset({"campaign", "application"})

CAMPAIGN_EXPORT_FIELDS = allow(
    "id",
    "title",
    "description",
    "campaign_type",
    "budget_min_paise",
    "budget_max_paise",
    "currency",
    "cities",
    "niches",
    "deliverables",
    "applications_close_on",
    "status",
    "created_at",
    "updated_at",
)

APPLICATION_EXPORT_FIELDS = allow(
    "id",
    "campaign_id",
    "pitch",
    "quoted_amount_paise",
    "status",
    "rejection_reason",
    "rejection_note",
    "status_changed_at",
    "created_at",
    "updated_at",
)

# What each status allows next. Empty means the campaign is finished.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"open", "cancelled"}),
    "open": frozenset({"closed", "cancelled"}),
    "closed": frozenset(),
    "cancelled": frozenset(),
}
# Once creators can apply, the deal on offer must not change under them.
EDITABLE_WHILE_OPEN = frozenset({"description", "deliverables", "applications_close_on"})


def get_brand_for_account(db: Session, account_id: uuid.UUID) -> Brand:
    """The brand profile of a signed-in brand account.

    Raises BrandProfileRequired when the account has not created one yet.
    """
    brand = db.scalars(select(Brand).where(Brand.account_id == account_id)).first()
    if brand is None:
        raise BrandProfileRequired()
    return brand


def create_campaign(db: Session, brand: Brand, fields: dict, now: datetime) -> Campaign:
    """Create a campaign as a draft. Only publishing makes it visible."""
    campaign = Campaign(
        brand_id=brand.id,
        status="draft",
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def update_campaign(
    db: Session, campaign: Campaign, changes: dict, now: datetime
) -> Campaign:
    """Change a campaign the brand owns.

    A draft can be changed completely. An open campaign only allows the fields
    in EDITABLE_WHILE_OPEN. A closed or cancelled campaign allows nothing.
    Raises CampaignNotEditable and FieldNotEditableNow.
    """
    if campaign.status in ("closed", "cancelled"):
        db.rollback()
        raise CampaignNotEditable()
    if campaign.status == "open":
        blocked = set(changes) - EDITABLE_WHILE_OPEN
        if blocked:
            db.rollback()
            raise FieldNotEditableNow(
                f"Cannot change {', '.join(sorted(blocked))} while the campaign is open."
            )

    for field, value in changes.items():
        setattr(campaign, field, value)
    campaign.updated_at = now
    db.commit()
    db.refresh(campaign)
    return campaign


def change_status(
    db: Session, campaign: Campaign, new_status: str, now: datetime
) -> Campaign:
    """Move a campaign to `new_status`, or raise CampaignStatusConflict."""
    if new_status not in ALLOWED_TRANSITIONS[campaign.status]:
        db.rollback()
        raise CampaignStatusConflict(
            f"A {campaign.status} campaign cannot become {new_status}."
        )
    campaign.status = new_status
    campaign.updated_at = now
    db.commit()
    db.refresh(campaign)
    return campaign


def _paginate(db: Session, query: Select, limit: int, cursor: str | None) -> Slice[Campaign]:
    """Newest first, one row past the limit to know whether more exist."""
    if cursor is not None:
        created_at, row_id = decode_cursor(cursor)
        query = query.where(
            (Campaign.created_at, Campaign.id) < (created_at, row_id)
        )
    rows = list(
        db.scalars(
            query.order_by(Campaign.created_at.desc(), Campaign.id.desc()).limit(limit + 1)
        ).all()
    )
    return build_slice(rows, limit, key=lambda row: (row.created_at, row.id))


def list_brand_campaigns(
    db: Session,
    brand: Brand,
    *,
    limit: int,
    cursor: str | None = None,
    status: str | None = None,
) -> Slice[Campaign]:
    """A brand's own campaigns, in every status."""
    query = select(Campaign).where(Campaign.brand_id == brand.id)
    if status is not None:
        query = query.where(Campaign.status == status)
    return _paginate(db, query, limit, cursor)


def discover_campaigns(
    db: Session,
    *,
    limit: int,
    cursor: str | None = None,
    city: str | None = None,
    niche: str | None = None,
    campaign_type: str | None = None,
    min_budget_paise: int | None = None,
) -> Slice[Campaign]:
    """Open campaigns for creators to browse, with optional filters."""
    query = select(Campaign).where(Campaign.status == "open")
    if city is not None:
        query = query.where(Campaign.cities.any(city))
    if niche is not None:
        query = query.where(Campaign.niches.any(niche))
    if campaign_type is not None:
        query = query.where(Campaign.campaign_type == campaign_type)
    if min_budget_paise is not None:
        # "Pays at least this much": the top of the range must reach it.
        query = query.where(Campaign.budget_max_paise >= min_budget_paise)
    return _paginate(db, query, limit, cursor)


# --- applications --------------------------------------------------------
#
# Status flow:
#
#     submitted ──shortlist──> shortlisted ──accept──> accepted
#         │  │                   │  │
#         │  └────reject─────────┘  └────reject───────> rejected
#         └────withdraw────────────────withdraw───────> withdrawn
#
# The brand shortlists, accepts and rejects; the creator withdraws. Accepted,
# rejected and withdrawn are final: a new attempt means a new campaign.
APPLICATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "submitted": frozenset({"shortlisted", "rejected", "withdrawn"}),
    "shortlisted": frozenset({"accepted", "rejected", "withdrawn"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
}


def get_creator_for_account(db: Session, account_id: uuid.UUID) -> Creator:
    """The creator profile of a signed-in creator account."""
    creator = db.scalars(select(Creator).where(Creator.account_id == account_id)).first()
    if creator is None:
        raise CreatorProfileRequired()
    return creator


def _brand_account_id(db: Session, campaign: Campaign) -> uuid.UUID | None:
    """The account behind a campaign's brand, to notify it."""
    return db.scalar(select(Brand.account_id).where(Brand.id == campaign.brand_id))


def _creator_account_id(db: Session, application: Application) -> uuid.UUID | None:
    return db.scalar(
        select(Creator.account_id).where(Creator.id == application.creator_id)
    )


# Which status change tells whom. The brand hears about withdrawals; the
# creator hears the brand's decisions (D-023).
STATUS_NOTIFICATIONS: dict[str, tuple[str, str]] = {
    "shortlisted": ("creator", "application_shortlisted"),
    "accepted": ("creator", "application_accepted"),
    "rejected": ("creator", "application_rejected"),
    "withdrawn": ("brand", "application_withdrawn"),
}


def apply_to_campaign(
    db: Session,
    campaign_id: uuid.UUID,
    creator: Creator,
    fields: dict,
    now: datetime,
) -> Application:
    """Apply to an open campaign.

    Raises CampaignNotFound (unknown or not open to this creator),
    ApplicationsClosed (past the closing date) and AlreadyApplied.
    """
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        db.rollback()
        raise CampaignNotFound()
    if campaign.status != "open":
        db.rollback()
        raise CampaignNotOpen()
    if campaign.applications_close_on is not None and now.date() > campaign.applications_close_on:
        db.rollback()
        raise ApplicationsClosed()

    application = Application(
        campaign_id=campaign.id,
        creator_id=creator.id,
        status="submitted",
        status_changed_at=now,
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(application)
    try:
        # Flush here so the notification can reference the new row; a second
        # application from the same creator fails on the unique rule now.
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if "uq_application_campaign_creator" in str(error):
            raise AlreadyApplied() from error
        raise

    brand_account_id = _brand_account_id(db, campaign)
    if brand_account_id is not None:
        notifications.record(
            db,
            account_id=brand_account_id,
            notification_type="application_received",
            now=now,
            campaign_id=campaign.id,
            application_id=application.id,
            details={"campaign_title": campaign.title, "creator_handle": creator.handle},
        )
    db.commit()
    db.refresh(application)
    return application


def change_application_status(
    db: Session,
    application: Application,
    new_status: str,
    now: datetime,
    *,
    rejection_reason: str | None = None,
    rejection_note: str | None = None,
) -> Application:
    """Move an application on, or raise ApplicationStatusConflict."""
    if new_status not in APPLICATION_TRANSITIONS[application.status]:
        db.rollback()
        raise ApplicationStatusConflict(
            f"A {application.status} application cannot become {new_status}."
        )
    application.status = new_status
    application.rejection_reason = rejection_reason if new_status == "rejected" else None
    application.rejection_note = rejection_note if new_status == "rejected" else None
    application.status_changed_at = now
    application.updated_at = now

    # Tell the other side what happened, in the same transaction: a record
    # that exists only if the change itself succeeded.
    side, notification_type = STATUS_NOTIFICATIONS[new_status]
    campaign = db.get(Campaign, application.campaign_id)
    account_id = (
        _creator_account_id(db, application)
        if side == "creator"
        else _brand_account_id(db, campaign)
    )
    if account_id is not None:
        details: dict[str, object] = {"campaign_title": campaign.title}
        if rejection_reason is not None:
            details["reason"] = rejection_reason
        notifications.record(
            db,
            account_id=account_id,
            notification_type=notification_type,
            now=now,
            campaign_id=campaign.id,
            application_id=application.id,
            details=details,
        )

    db.commit()
    db.refresh(application)
    return application


def _paginate_applications(
    db: Session, query: Select, limit: int, cursor: str | None
) -> Slice[Application]:
    if cursor is not None:
        created_at, row_id = decode_cursor(cursor)
        query = query.where((Application.created_at, Application.id) < (created_at, row_id))
    rows = list(
        db.scalars(
            query.order_by(Application.created_at.desc(), Application.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    return build_slice(rows, limit, key=lambda row: (row.created_at, row.id))


def list_campaign_applications(
    db: Session,
    campaign: Campaign,
    *,
    limit: int,
    cursor: str | None = None,
    status: str | None = None,
) -> Slice[Application]:
    """Applications to one of the brand's own campaigns."""
    query = select(Application).where(Application.campaign_id == campaign.id)
    if status is not None:
        query = query.where(Application.status == status)
    return _paginate_applications(db, query, limit, cursor)


def list_creator_applications(
    db: Session,
    creator: Creator,
    *,
    limit: int,
    cursor: str | None = None,
    status: str | None = None,
) -> Slice[Application]:
    """A creator's own applications, across every campaign."""
    query = select(Application).where(Application.creator_id == creator.id)
    if status is not None:
        query = query.where(Application.status == status)
    return _paginate_applications(db, query, limit, cursor)


def _campaign_titles(db: Session, campaign_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Titles for a set of campaigns, in one query rather than one each."""
    if not campaign_ids:
        return {}
    rows = db.execute(
        select(Campaign.id, Campaign.title).where(Campaign.id.in_(campaign_ids))
    ).all()
    return {row.id: row.title for row in rows}


def _creator_handles(db: Session, creator_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Public handles for a set of creators, in one query.

    A handle is already public (it is what the Creator Passport is keyed on),
    so it is the one thing about the other side that may appear in an export.
    Nothing else about them does.
    """
    if not creator_ids:
        return {}
    rows = db.execute(
        select(Creator.id, Creator.handle).where(Creator.id.in_(creator_ids))
    ).all()
    return {row.id: row.handle for row in rows}


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """Campaigns and applications belonging to this account.

    A brand gets the campaigns it posted and the applications it received; a
    creator gets the applications it sent. Either side sees the other only by
    internal id and public handle.
    """
    sections: list[ExportedSection] = []

    brand = db.scalars(select(Brand).where(Brand.account_id == account_id)).first()
    if brand is not None:
        campaigns = list(
            db.scalars(
                select(Campaign)
                .where(Campaign.brand_id == brand.id)
                .order_by(Campaign.created_at, Campaign.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )
        sections.append(
            build_section(
                "campaigns",
                table="campaign",
                purpose="The campaigns you posted, including ones still in draft.",
                objects=campaigns,
                fields=CAMPAIGN_EXPORT_FIELDS,
            )
        )

        received = list(
            db.scalars(
                select(Application)
                .join(Campaign, Application.campaign_id == Campaign.id)
                .where(Campaign.brand_id == brand.id)
                .order_by(Application.created_at, Application.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )
        handles = _creator_handles(db, {row.creator_id for row in received})
        titles = _campaign_titles(db, {row.campaign_id for row in received})
        sections.append(
            build_section(
                "applications_received",
                table="application",
                purpose=(
                    "Applications creators sent to your campaigns. The creator "
                    "is identified by their public handle only."
                ),
                objects=received,
                fields=APPLICATION_EXPORT_FIELDS,
                extra=lambda row: {
                    "creator_handle": handles.get(row.creator_id),
                    "campaign_title": titles.get(row.campaign_id),
                },
            )
        )

    creator = db.scalars(select(Creator).where(Creator.account_id == account_id)).first()
    if creator is not None:
        sent = list(
            db.scalars(
                select(Application)
                .where(Application.creator_id == creator.id)
                .order_by(Application.created_at, Application.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )
        titles = _campaign_titles(db, {row.campaign_id for row in sent})
        sections.append(
            build_section(
                "applications_sent",
                table="application",
                purpose="Applications you sent to campaigns, and how each ended.",
                objects=sent,
                fields=APPLICATION_EXPORT_FIELDS,
                extra=lambda row: {"campaign_title": titles.get(row.campaign_id)},
            )
        )

    return sections
