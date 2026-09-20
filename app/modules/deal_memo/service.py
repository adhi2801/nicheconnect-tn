"""Deal memo rules (D-024 to D-027).

The memo is what the two sides agreed. It exists only for an accepted
application, and once accepted its terms stop changing: a creator who says yes
must be able to rely on what they said yes to.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
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
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.exceptions import (
    ApplicationNotAccepted,
    BarterMemoHasNoFee,
    MemoAlreadyExists,
    MemoNotEditable,
    MemoStatusConflict,
    PaidMemoNeedsFee,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.notifications import service as notifications

# Tables this module answers for in a data export (see
# tests/modules/auth/test_export_api.py, which fails if one is missed).
EXPORTED_TABLES = frozenset({"deal_memo", "deliverable_proof"})

MEMO_EXPORT_FIELDS = allow(
    "id",
    "application_id",
    "deliverables",
    "fee_amount_paise",
    "currency",
    "cancellation_fee_paise",
    "approval_window_days",
    "payment_due_days",
    "usage_rights_days",
    "content_due_on",
    "disclosure_required",
    "extra_terms",
    "status",
    "revision_count",
    "sent_at",
    "accepted_at",
    "work_started_at",
    "cancelled_at",
    "cancellation_kind",
    "created_at",
    "updated_at",
)

PROOF_EXPORT_FIELDS = allow(
    "id",
    "deal_memo_id",
    "content_url",
    "format",
    "note",
    "disclosure_confirmed",
    "status",
    "approved_at",
    "auto_approved",
    "revision_note",
    "content_removed_on",
    "last_checked_at",
    "created_at",
    "updated_at",
)

# Who may make each move, and where it leads.
BRAND_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"sent", "cancelled"}),
    "sent": frozenset({"cancelled"}),
    "change_requested": frozenset({"sent", "cancelled"}),
    "accepted": frozenset({"cancelled"}),
    "declined": frozenset(),
    "cancelled": frozenset(),
}
CREATOR_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset(),
    "sent": frozenset({"accepted", "declined", "change_requested"}),
    "change_requested": frozenset(),
    "accepted": frozenset({"cancelled"}),
    "declined": frozenset(),
    "cancelled": frozenset(),
}
# Who hears about each move, and as what.
STATUS_NOTIFICATIONS: dict[str, tuple[str, str]] = {
    "sent": ("creator", "memo_sent"),
    "accepted": ("brand", "memo_accepted"),
    "declined": ("brand", "memo_declined"),
    "change_requested": ("brand", "memo_change_requested"),
}

# Terms may change while the brand still holds the memo.
EDITABLE_STATUSES = frozenset({"draft", "change_requested"})
# Types whose memo must name a fee (barter pays in goods).
FEE_REQUIRED_TYPES = frozenset({"paid", "local_business"})


def _campaign_of(db: Session, application: Application) -> Campaign:
    return db.get(Campaign, application.campaign_id)


def _brand_account_id(db: Session, campaign: Campaign) -> uuid.UUID | None:
    return db.scalar(select(Brand.account_id).where(Brand.id == campaign.brand_id))


def _creator_account_id(db: Session, application: Application) -> uuid.UUID | None:
    return db.scalar(
        select(Creator.account_id).where(Creator.id == application.creator_id)
    )


def _check_fee_against_campaign(campaign: Campaign, fee_amount_paise: int | None) -> None:
    """Barter memos carry no fee; paid and local-business memos must."""
    if campaign.campaign_type == "barter" and fee_amount_paise is not None:
        raise BarterMemoHasNoFee()
    if campaign.campaign_type in FEE_REQUIRED_TYPES and fee_amount_paise is None:
        raise PaidMemoNeedsFee()


def create_memo(
    db: Session, application: Application, fields: dict, now: datetime
) -> DealMemo:
    """Draft a memo for an accepted application.

    Raises ApplicationNotAccepted, MemoAlreadyExists, and the fee errors.
    """
    if application.status != "accepted":
        db.rollback()
        raise ApplicationNotAccepted()
    existing = db.scalars(
        select(DealMemo).where(DealMemo.application_id == application.id)
    ).first()
    if existing is not None:
        db.rollback()
        raise MemoAlreadyExists()

    campaign = _campaign_of(db, application)
    _check_fee_against_campaign(campaign, fields.get("fee_amount_paise"))

    memo = DealMemo(
        application_id=application.id,
        status="draft",
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(memo)
    db.commit()
    db.refresh(memo)
    return memo


def update_memo(db: Session, memo: DealMemo, changes: dict, now: datetime) -> DealMemo:
    """Change a memo the brand still holds (draft, or a change was requested)."""
    if memo.status not in EDITABLE_STATUSES:
        db.rollback()
        raise MemoNotEditable()

    if "fee_amount_paise" in changes:
        application = db.get(Application, memo.application_id)
        _check_fee_against_campaign(_campaign_of(db, application), changes["fee_amount_paise"])

    for field, value in changes.items():
        setattr(memo, field, value)
    memo.updated_at = now
    db.commit()
    db.refresh(memo)
    return memo


def _notify_other_side(
    db: Session,
    memo: DealMemo,
    *,
    to: str,
    notification_type: str,
    now: datetime,
    message: str | None = None,
) -> None:
    application = db.get(Application, memo.application_id)
    campaign = _campaign_of(db, application)
    account_id = (
        _creator_account_id(db, application)
        if to == "creator"
        else _brand_account_id(db, campaign)
    )
    if account_id is None:
        return
    details: dict[str, object] = {"campaign_title": campaign.title}
    if message is not None:
        # The creator's own words, so the brand knows what to change.
        details["message"] = message
    notifications.record(
        db,
        account_id=account_id,
        notification_type=notification_type,
        now=now,
        campaign_id=campaign.id,
        application_id=application.id,
        details=details,
    )


def change_status(
    db: Session,
    memo: DealMemo,
    new_status: str,
    now: datetime,
    *,
    actor: str,
    cancellation_kind: str | None = None,
    message: str | None = None,
) -> DealMemo:
    """Move a memo on, as `actor` ("brand" or "creator").

    Raises MemoStatusConflict when that side may not make that move from here.
    """
    allowed = BRAND_TRANSITIONS if actor == "brand" else CREATOR_TRANSITIONS
    if new_status not in allowed[memo.status]:
        db.rollback()
        raise MemoStatusConflict(
            f"A {actor} cannot move a {memo.status} memo to {new_status}."
        )

    if new_status == "sent":
        memo.sent_at = now
    elif new_status == "accepted":
        memo.accepted_at = now
    elif new_status == "change_requested":
        # Only the first request restarts the approval clock (D-025); the
        # count is what the UI uses to say so before a second one.
        memo.revision_count += 1
    elif new_status == "cancelled":
        memo.cancelled_at = now
        memo.cancellation_kind = cancellation_kind or (
            # Before any work was submitted a cancellation costs nothing (D-026).
            f"cancelled_by_{actor}" if memo.work_started_at is not None else "withdrawn_early"
        )

    memo.status = new_status
    memo.updated_at = now

    # Tell the other side, in the same transaction as the change itself.
    if new_status == "cancelled":
        _notify_other_side(
            db,
            memo,
            to="creator" if actor == "brand" else "brand",
            notification_type="memo_cancelled",
            now=now,
        )
    elif new_status in STATUS_NOTIFICATIONS:
        side, notification_type = STATUS_NOTIFICATIONS[new_status]
        _notify_other_side(
            db,
            memo,
            to=side,
            notification_type=notification_type,
            now=now,
            message=message,
        )

    db.commit()
    db.refresh(memo)
    return memo


def _paginate(db: Session, query, limit: int, cursor: str | None) -> Slice[DealMemo]:
    if cursor is not None:
        created_at, row_id = decode_cursor(cursor)
        query = query.where((DealMemo.created_at, DealMemo.id) < (created_at, row_id))
    rows = list(
        db.scalars(
            query.order_by(DealMemo.created_at.desc(), DealMemo.id.desc()).limit(limit + 1)
        ).all()
    )
    return build_slice(rows, limit, key=lambda row: (row.created_at, row.id))


def list_for_brand(
    db: Session, brand: Brand, *, limit: int, cursor: str | None = None, status: str | None = None
) -> Slice[DealMemo]:
    """Memos on the brand's own campaigns."""
    query = (
        select(DealMemo)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(Campaign.brand_id == brand.id)
    )
    if status is not None:
        query = query.where(DealMemo.status == status)
    return _paginate(db, query, limit, cursor)


def list_for_creator(
    db: Session,
    creator: Creator,
    *,
    limit: int,
    cursor: str | None = None,
    status: str | None = None,
) -> Slice[DealMemo]:
    """Memos sent to this creator. Drafts are not theirs to see yet."""
    query = (
        select(DealMemo)
        .join(Application, Application.id == DealMemo.application_id)
        .where(Application.creator_id == creator.id, DealMemo.status != "draft")
    )
    if status is not None:
        query = query.where(DealMemo.status == status)
    return _paginate(db, query, limit, cursor)


def memos_for_account(db: Session, account_id: uuid.UUID, *, limit: int) -> list[DealMemo]:
    """Every memo this account is a party to, oldest first.

    Both sides agreed the same terms, so the query reaches the memo from
    whichever side the account is on. Shared so that other modules keep one
    definition of "a memo of mine" rather than each rebuilding the join.
    """
    brand = db.scalars(select(Brand).where(Brand.account_id == account_id)).first()
    creator = db.scalars(select(Creator).where(Creator.account_id == account_id)).first()
    if brand is None and creator is None:
        return []

    query = (
        select(DealMemo)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
    )
    if brand is not None:
        query = query.where(Campaign.brand_id == brand.id)
    else:
        query = query.where(Application.creator_id == creator.id)

    return list(
        db.scalars(query.order_by(DealMemo.created_at, DealMemo.id).limit(limit)).all()
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """Deal memos this account is a party to, and the proof filed against them.

    Both sides of a memo agreed to the same terms, so both sides may keep a
    copy. The query reaches the memo from whichever side this account is on.
    """
    memos = memos_for_account(db, account_id, limit=MAX_ROWS_PER_SECTION + 1)

    memo_ids = {memo.id for memo in memos}
    proofs: list[DeliverableProof] = []
    if memo_ids:
        proofs = list(
            db.scalars(
                select(DeliverableProof)
                .where(DeliverableProof.deal_memo_id.in_(memo_ids))
                .order_by(DeliverableProof.created_at, DeliverableProof.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )

    return [
        build_section(
            "deal_memos",
            table="deal_memo",
            purpose=(
                "What each side agreed: deliverables, fee, deadlines and how "
                "the memo ended. Money is recorded, never held by us."
            ),
            objects=memos,
            fields=MEMO_EXPORT_FIELDS,
        ),
        build_section(
            "deliverable_proofs",
            table="deliverable_proof",
            purpose="Proof of published work filed against those memos, and its review.",
            objects=proofs,
            fields=PROOF_EXPORT_FIELDS,
        ),
    ]
