import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.taxonomy import CURRENCY, MAX_NICHES, NICHES, sql_text_array
from app.db.base import Base

# What a brand asks for (D-016). Money is whole paise (D-015); no float ever.

CAMPAIGN_TYPES: tuple[str, ...] = ("paid", "barter", "commission", "local_business")
# Types that must name a budget. Barter pays in goods, so it must not have one;
# commission is paid per sale, so a budget is optional.
BUDGETED_TYPES: tuple[str, ...] = ("paid", "local_business")
CAMPAIGN_STATUSES: tuple[str, ...] = ("draft", "open", "closed", "cancelled")

MAX_CITIES = 10
TITLE_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 4000
DELIVERABLES_MAX_LENGTH = 2000


class Campaign(Base):
    __tablename__ = "campaign"
    __table_args__ = (
        CheckConstraint(f"campaign_type IN {tuple(CAMPAIGN_TYPES)}", name="type_allowed"),
        CheckConstraint(f"status IN {tuple(CAMPAIGN_STATUSES)}", name="status_allowed"),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_allowed"),
        CheckConstraint("char_length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint(
            f"char_length(description) <= {DESCRIPTION_MAX_LENGTH}",
            name="description_length",
        ),
        CheckConstraint(
            "char_length(btrim(deliverables)) > 0", name="deliverables_not_blank"
        ),
        CheckConstraint(
            f"char_length(deliverables) <= {DELIVERABLES_MAX_LENGTH}",
            name="deliverables_length",
        ),
        # Either no budget at all, or both ends set and sensible, in paise.
        # Both "IS NOT NULL" tests are needed: a comparison with NULL is
        # unknown, and an unknown CHECK passes.
        CheckConstraint(
            "(budget_min_paise IS NULL AND budget_max_paise IS NULL)"
            " OR (budget_min_paise IS NOT NULL AND budget_max_paise IS NOT NULL"
            " AND budget_min_paise > 0 AND budget_max_paise >= budget_min_paise)",
            name="budget_range",
        ),
        # Barter never carries cash; paid and local-business campaigns must say
        # what they pay; commission may leave it open. Unknown types are the
        # type rule's job, so each constraint reports exactly one problem.
        CheckConstraint(
            f"campaign_type NOT IN {tuple(CAMPAIGN_TYPES)}"
            " OR (campaign_type = 'barter' AND budget_min_paise IS NULL)"
            f" OR (campaign_type IN {tuple(BUDGETED_TYPES)} AND budget_min_paise IS NOT NULL)"
            " OR campaign_type = 'commission'",
            name="budget_matches_type",
        ),
        CheckConstraint(
            f"cardinality(cities) BETWEEN 1 AND {MAX_CITIES}", name="cities_count"
        ),
        CheckConstraint(
            f"cardinality(niches) BETWEEN 1 AND {MAX_NICHES}", name="niches_count"
        ),
        CheckConstraint(f"niches <@ {sql_text_array(NICHES)}", name="niches_allowed"),
        # Discovery: open campaigns, newest first.
        Index(
            "ix_campaign_open_created_at",
            "created_at",
            postgresql_where=text("status = 'open'"),
        ),
        # No GIN indexes on niches or cities: measured at 20,000 campaigns,
        # the planner uses the index above and filters, so they were never
        # chosen (D-017). They return with the feature that needs them.
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # RESTRICT: a brand with campaigns cannot be deleted.
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Paise, never rupees and never a float (D-015).
    budget_min_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    budget_max_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text(f"'{CURRENCY}'")
    )
    cities: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    niches: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    deliverables: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable on purpose: a campaign need not have a closing date.
    applications_close_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'draft'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# A creator on a campaign (D-016): one row per creator per campaign, however
# it began. A creator applies (origin 'applied', with a pitch), or a brand
# invites them (origin 'invited', no pitch, D-084). A repeat of an earlier
# deal is an invitation that names the deal it repeats.

APPLICATION_ORIGINS: tuple[str, ...] = ("applied", "invited")
APPLICATION_STATUSES: tuple[str, ...] = (
    "submitted",
    "shortlisted",
    "accepted",
    "rejected",
    "withdrawn",
    # An invitation waiting for the creator's answer, and the creator's no.
    "invited",
    "declined",
)
# Why a creator said no to an invitation: the brand sees a clear reason, as a
# creator does when a brand rejects them (D-084).
DECLINE_REASONS: tuple[str, ...] = ("timing", "budget", "not_a_fit", "other")
INVITATION_NOTE_MAX_LENGTH = 500
# Why a brand said no. Stored as a code so the creator sees a clear reason and
# we can report on it, rather than free text nobody reads.
REJECTION_REASONS: tuple[str, ...] = (
    "budget_mismatch",
    "audience_mismatch",
    "timing",
    "chose_another_creator",
    "incomplete_profile",
    "other",
)
PITCH_MIN_LENGTH = 20
PITCH_MAX_LENGTH = 1000
REJECTION_NOTE_MAX_LENGTH = 500


class Application(Base):
    __tablename__ = "application"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "creator_id", name="uq_application_campaign_creator"
        ),
        CheckConstraint(
            f"status IN {tuple(APPLICATION_STATUSES)}", name="status_allowed"
        ),
        CheckConstraint(
            f"char_length(btrim(pitch)) BETWEEN {PITCH_MIN_LENGTH} AND {PITCH_MAX_LENGTH}",
            name="pitch_length",
        ),
        CheckConstraint(f"origin IN {tuple(APPLICATION_ORIGINS)}", name="origin_allowed"),
        # The creator who applied wrote a pitch; an invited creator did not.
        CheckConstraint(
            "(origin = 'applied') = (pitch IS NOT NULL)", name="pitch_matches_origin"
        ),
        # Only an invitation carries the brand's note, is ever waiting as
        # 'invited', can be declined, or repeats an earlier deal.
        CheckConstraint(
            "origin = 'invited' OR (invitation_note IS NULL"
            " AND status NOT IN ('invited', 'declined')"
            " AND repeat_of_application_id IS NULL)",
            name="invitation_fields_need_invitation",
        ),
        # An invitation is answered, or taken back; it is never shortlisted or
        # rejected, which are the brand's answers to an application.
        CheckConstraint(
            "origin = 'applied'"
            " OR status IN ('invited', 'accepted', 'declined', 'withdrawn')",
            name="invitation_status_allowed",
        ),
        CheckConstraint(
            f"invitation_note IS NULL OR char_length(invitation_note)"
            f" BETWEEN 1 AND {INVITATION_NOTE_MAX_LENGTH}",
            name="invitation_note_length",
        ),
        CheckConstraint(
            f"decline_reason IS NULL OR decline_reason IN {tuple(DECLINE_REASONS)}",
            name="decline_reason_allowed",
        ),
        # A decline always carries a reason; nothing else may.
        CheckConstraint(
            "(status = 'declined') = (decline_reason IS NOT NULL)",
            name="decline_reason_matches_status",
        ),
        # A deal repeats another deal, never itself.
        CheckConstraint(
            "repeat_of_application_id IS NULL OR repeat_of_application_id <> id",
            name="repeat_not_itself",
        ),
        CheckConstraint(
            "quoted_amount_paise IS NULL OR quoted_amount_paise > 0",
            name="quoted_amount_positive",
        ),
        CheckConstraint(
            f"rejection_reason IS NULL OR rejection_reason IN {tuple(REJECTION_REASONS)}",
            name="rejection_reason_allowed",
        ),
        # A rejection always carries a reason; nothing else may carry one.
        CheckConstraint(
            "(status = 'rejected') = (rejection_reason IS NOT NULL)",
            name="rejection_reason_matches_status",
        ),
        CheckConstraint(
            f"rejection_note IS NULL OR char_length(rejection_note) <= {REJECTION_NOTE_MAX_LENGTH}",
            name="rejection_note_length",
        ),
        # The brand's list for one campaign, newest first.
        Index("ix_application_campaign_created_at", "campaign_id", "created_at"),
        # The creator's own list, newest first.
        Index("ix_application_creator_created_at", "creator_id", "created_at"),
        # Every foreign key is indexed (database.md section 5); only repeats
        # carry one, so the index holds only those.
        Index(
            "ix_application_repeat_of_application_id",
            "repeat_of_application_id",
            postgresql_where=text("repeat_of_application_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # RESTRICT on both: an application is a record of what happened, so neither
    # side can be deleted out from under it.
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaign.id", ondelete="RESTRICT"),
        nullable=False,
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creator.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # How it began: 'applied' by the creator, or 'invited' by the brand.
    origin: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'applied'")
    )
    # NULL for an invitation: the brand chose the creator, so there is
    # nothing to pitch.
    pitch: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The brand's few words with an invitation. NULL when it said nothing,
    # and always for an application.
    invitation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The earlier deal this one repeats ("work together again", D-084). It
    # names that deal's application, which has exactly one memo. NULL for
    # everything else. RESTRICT: a record of what happened.
    repeat_of_application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("application.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # What the creator asks for, in paise (D-015). Optional: barter campaigns
    # and commission deals may have nothing to quote.
    quoted_amount_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'submitted'")
    )
    # Set only when the status is 'rejected'.
    rejection_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rejection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set only when the status is 'declined'.
    decline_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # When the status last changed, so the app can show "what happened when".
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
