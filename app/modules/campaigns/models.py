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
        CheckConstraint(
            f"campaign_type IN {tuple(CAMPAIGN_TYPES)}", name="type_allowed"
        ),
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
        CheckConstraint(
            f"niches <@ {sql_text_array(NICHES)}", name="niches_allowed"
        ),
        # Discovery: open campaigns, newest first.
        Index(
            "ix_campaign_open_created_at",
            "created_at",
            postgresql_where=text("status = 'open'"),
        ),
        # Filters on the discovery list.
        Index("ix_campaign_niches", "niches", postgresql_using="gin"),
        Index("ix_campaign_cities", "cities", postgresql_using="gin"),
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
