"""Campaign alerts (item 43, D-130): a creator hears first when a campaign fits.

A creator saves up to MAX_ALERTS_PER_CREATOR alerts, each any mix of a
city, a niche, a campaign type and a least budget; a term left empty
matches anything, but an alert names at least one. When a campaign is
published, a row in `campaign_alert_send` (an outbox, written in the
publishing transaction) tells the job that its alerts are due; the job
records a `campaign_alert` notification for every creator whose alert
fits (`alert_rules.matches` says what fits; `alert_service` asks the same
in SQL).

CASCADE on the creator: an alert is the creator's own thing. CASCADE on
the campaign: the send row is only the campaign's job state.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.taxonomy import CURRENCY, NICHES
from app.db.base import Base
from app.modules.campaigns.models import CAMPAIGN_TYPES

MAX_ALERTS_PER_CREATOR = 5
# Past this many in a Tamil Nadu day, a creator is told of no more
# campaigns until the next; each is still in discovery.
MAX_ALERTS_A_DAY = 20
CITY_MIN_LENGTH = 2
CITY_MAX_LENGTH = 60


class CampaignAlert(Base):
    __tablename__ = "campaign_alert"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(city, niche, campaign_type, min_budget_paise) >= 1",
            name="names_a_term",
        ),
        CheckConstraint(
            "city IS NULL OR char_length(btrim(city)) "
            f"BETWEEN {CITY_MIN_LENGTH} AND {CITY_MAX_LENGTH}",
            name="city_length",
        ),
        CheckConstraint(
            f"niche IS NULL OR niche IN {tuple(NICHES)}", name="niche_allowed"
        ),
        CheckConstraint(
            f"campaign_type IS NULL OR campaign_type IN {tuple(CAMPAIGN_TYPES)}",
            name="type_allowed",
        ),
        CheckConstraint(
            "min_budget_paise IS NULL OR min_budget_paise > 0", name="budget_positive"
        ),
        # Barter carries no cash, so a least budget could never fit one.
        CheckConstraint(
            "campaign_type IS DISTINCT FROM 'barter' OR min_budget_paise IS NULL",
            name="no_budget_on_barter",
        ),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_allowed"),
        # The same terms once per creator, a city in any case; NULLs equal,
        # so two "any city" alerts are the same. Also the foreign key's index.
        Index(
            "uq_campaign_alert_terms",
            "creator_id",
            func.lower(text("city")),
            "niche",
            "campaign_type",
            "min_budget_paise",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creator.id", ondelete="CASCADE"), nullable=False
    )
    # NULL in any term means "any": any city, any niche, any type, any budget.
    city: Mapped[str | None] = mapped_column(String(CITY_MAX_LENGTH), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(20), nullable=True)
    campaign_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Paise (D-015): fits a campaign whose budget reaches it.
    min_budget_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text(f"'{CURRENCY}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CampaignAlertSend(Base):
    """One per published campaign: its alerts are due until `sent_at`."""

    __tablename__ = "campaign_alert_send"
    __table_args__ = (
        # Sent and counted together, or neither.
        CheckConstraint(
            "(sent_at IS NULL) = (recipients IS NULL)", name="sent_with_recipients"
        ),
        CheckConstraint(
            "recipients IS NULL OR recipients >= 0", name="recipients_counted"
        ),
        # The job's queue: only what is still due, oldest first.
        Index(
            "ix_campaign_alert_send_due",
            "queued_at",
            postgresql_where=text("sent_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # A campaign opens once (draft to open), so one row each; also the
    # foreign key's index.
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL means still due.
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # How many creators were told; NULL until sent.
    recipients: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
