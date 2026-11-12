"""A direct offer: a creator's memo sent to a brand not on the platform (D-189).

The creator writes the terms a memo carries and names the brand and its
WhatsApp number. We give the creator a link, valid for 14 days, which they
send to the brand themselves; we send nothing to the number until its holder
asks for the code that accepts. Accepting makes the brand's account and
profile, a hidden campaign of type `direct`, an application of origin
`direct` and the memo, agreed by both, in one transaction
(`direct_offer_service.accept`). From then on the deal is an ordinary deal.

What is kept, and for how long (the privacy impact assessment in D-189):

- the link's token only as an HMAC (`token_hash`), as assistants' tokens
  are (D-138), so a copy of this table cannot open a single offer;
- the number in clear (`recipient_phone`) and the brand's name only while
  the offer waits: the code must reach that number, and the brand confirms
  that name. Once it ends, however it ends, both are emptied in the same
  statement that ends it (`ck_direct_offer_recipient_kept_only_while_waiting`);
- the number's keyed hash (`recipient_phone_hash`) for as long as the row
  lives: it counts the 3 offers a week one number may receive, and it is
  the block when the number's holder says "stop these" (`status = 'stopped'`).
  A row that ended any other way and never became a deal is deleted 30 days
  after it ended (`direct_offer_jobs`); a stopped row stays, as the block
  its holder asked for, until the creator's account is deleted.

The terms are the creator's own words, theirs to export and erased with
their account unless they became a deal, when the memo holds them as it
holds every deal's.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.taxonomy import CURRENCY
from app.db.base import Base
from app.modules.auth.models.account import PHONE_PATTERN
from app.modules.campaigns.deliverable_models import MAX_DELIVERABLES
from app.modules.deal_memo.models import (
    DELIVERABLES_MAX_LENGTH,
    MAX_USAGE_RIGHTS_DAYS,
    MAX_WINDOW_DAYS,
    TERMS_MAX_LENGTH,
)

# What is stored. "expired" is written by the job that empties an offer
# whose 14 days ran out; until it runs, a read works it out from
# `expires_at` (`direct_offer_rules.shown_status`).
DIRECT_OFFER_STATUSES: tuple[str, ...] = (
    "sent",
    "accepted",
    "withdrawn",
    "stopped",
    "expired",
)
# How long a link works (D-189).
DIRECT_OFFER_LIFETIME = timedelta(days=14)
# How long an offer that ended without a deal is kept, for its number's
# weekly count and the creator's list, before the job deletes it.
ENDED_OFFER_KEPT_FOR = timedelta(days=30)
BRAND_NAME_MAX_LENGTH = 150
HEX_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class DirectOffer(Base):
    __tablename__ = "direct_offer"
    __table_args__ = (
        CheckConstraint(
            f"status IN {tuple(DIRECT_OFFER_STATUSES)}", name="status_allowed"
        ),
        CheckConstraint(f"token_hash ~ '{HEX_SHA256_PATTERN}'", name="token_hash_format"),
        CheckConstraint(
            f"recipient_phone_hash ~ '{HEX_SHA256_PATTERN}'",
            name="recipient_phone_hash_format",
        ),
        CheckConstraint(
            f"terms_sha256 ~ '{HEX_SHA256_PATTERN}'", name="terms_sha256_format"
        ),
        CheckConstraint(
            f"recipient_phone IS NULL OR recipient_phone ~ '{PHONE_PATTERN}'",
            name="recipient_phone_format",
        ),
        CheckConstraint(
            "brand_name IS NULL OR char_length(btrim(brand_name)) > 0",
            name="brand_name_not_blank",
        ),
        # The number and the name are kept only while the offer waits, and
        # always while it does (the privacy impact assessment, D-189).
        CheckConstraint(
            "(status = 'sent') = (recipient_phone IS NOT NULL)"
            " AND (status = 'sent') = (brand_name IS NOT NULL)",
            name="recipient_kept_only_while_waiting",
        ),
        # Ended exactly when it is no longer waiting.
        CheckConstraint(
            "(status = 'sent') = (ended_at IS NULL)", name="ended_at_matches_status"
        ),
        # A deal exactly when accepted.
        CheckConstraint(
            "(status = 'accepted') = (deal_memo_id IS NOT NULL)",
            name="deal_only_when_accepted",
        ),
        CheckConstraint(
            "expires_at > created_at"
            f" AND expires_at <= created_at + interval '{DIRECT_OFFER_LIFETIME.days} days'",
            name="lifetime_within_limit",
        ),
        CheckConstraint(
            "opened_at IS NULL OR opened_at >= created_at", name="opened_after_sent"
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= created_at", name="ended_after_sent"
        ),
        # The same terms, and limits, as a memo's (D-189).
        CheckConstraint(
            "char_length(btrim(deliverables)) > 0"
            f" AND char_length(deliverables) <= {DELIVERABLES_MAX_LENGTH}",
            name="deliverables_length",
        ),
        CheckConstraint(
            "jsonb_typeof(deliverable_items) = 'array'"
            f" AND jsonb_array_length(deliverable_items) <= {MAX_DELIVERABLES}",
            name="deliverable_items_list",
        ),
        CheckConstraint("fee_amount_paise > 0", name="fee_positive"),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_allowed"),
        CheckConstraint(
            "cancellation_fee_paise >= 0", name="cancellation_fee_not_negative"
        ),
        CheckConstraint(
            f"approval_window_days BETWEEN 1 AND {MAX_WINDOW_DAYS}",
            name="approval_window_range",
        ),
        CheckConstraint(
            f"payment_due_days BETWEEN 1 AND {MAX_WINDOW_DAYS}", name="payment_due_range"
        ),
        CheckConstraint(
            "usage_rights_days IS NULL"
            f" OR usage_rights_days BETWEEN 1 AND {MAX_USAGE_RIGHTS_DAYS}",
            name="usage_rights_range",
        ),
        CheckConstraint(
            f"extra_terms IS NULL OR char_length(extra_terms) <= {TERMS_MAX_LENGTH}",
            name="extra_terms_length",
        ),
        # The creator's list, newest first; its leading column indexes the
        # foreign key, and it counts the creator's offers in a day.
        Index("ix_direct_offer_creator_id_created_at", "creator_id", "created_at", "id"),
        # One number's offers in a week, and whether it stopped a creator.
        Index(
            "ix_direct_offer_recipient_phone_hash_created_at",
            "recipient_phone_hash",
            "created_at",
        ),
        # The job's two questions: what ran out, and what ended long ago.
        Index(
            "ix_direct_offer_waiting_expires_at",
            "expires_at",
            postgresql_where=text("status = 'sent'"),
        ),
        Index(
            "ix_direct_offer_ended_without_deal_ended_at",
            "ended_at",
            postgresql_where=text("status IN ('withdrawn', 'expired')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # RESTRICT, as on an application: once accepted the offer is part of a
    # deal's history. Erasure deletes the creator's offers that never became
    # one (`direct_offer_service.erase_for_creator`).
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creator.id", ondelete="RESTRICT"), nullable=False
    )
    # HMAC-SHA256 of the link's token, under its own label. Unique, so the
    # link finds its offer by one index lookup.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    recipient_phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL once the offer ended: see the module docstring.
    recipient_phone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The brand's name as the creator typed it. NULL once the offer ended.
    brand_name: Mapped[str | None] = mapped_column(
        String(BRAND_NAME_MAX_LENGTH), nullable=True
    )
    # The terms, as a memo holds them (D-024 to D-027, D-127, D-140).
    deliverables: Mapped[str] = mapped_column(Text, nullable=False)
    deliverable_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    fee_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text(f"'{CURRENCY}'")
    )
    cancellation_fee_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approval_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_due_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL means the usage rights were not agreed, as on a memo.
    usage_rights_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    disclosure_required: Mapped[bool] = mapped_column(nullable=False)
    draft_review: Mapped[bool] = mapped_column(nullable=False)
    # NULL means none, as on a memo.
    extra_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The SHA-256 of the terms at sending, as the deal record will seal them
    # (`record_service.terms_fingerprint`, version 3). The brand accepts these
    # exact terms or none.
    terms_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'sent'")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When the link was first opened, for the creator's list. NULL until then.
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When it was accepted, withdrawn, stopped or expired. NULL while it waits.
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The deal it became. RESTRICT: a deal's history never vanishes as a side
    # effect. Unique, which is also the foreign key's index.
    deal_memo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
