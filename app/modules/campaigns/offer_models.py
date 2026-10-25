"""Counter-offers on a quote: a figure one side proposes and the other answers (item 44, D-123).

Before a deal is agreed, either side of a waiting application may name a
figure: the brand answering a creator's quote, or the creator answering
back. The other side accepts it, declines it, or makes its own, which
replaces it. One offer is open at a time (the partial unique index below),
and each side makes at most MAX_OFFERS_PER_SIDE on one application, so
nobody is ground down. An accepted figure is what the two agreed; it is
worked out from these rows, never copied onto the application, and
pre-fills the memo, which stays the contract (choice 2A).

The rows stay as the history of the negotiation, the record both sides
see and export (choice 3A). RESTRICT on the application: a record of what
happened, like the application itself.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.taxonomy import CURRENCY
from app.db.base import Base

OFFER_SIDES: tuple[str, ...] = ("brand", "creator")
# How an offer ended. NULL means it is open.
OFFER_OUTCOMES: tuple[str, ...] = (
    "accepted",
    # The other side said no; the application waits on, as it was.
    "declined",
    # The other side answered with an offer of its own.
    "replaced",
    # Taken back by its maker, or closed when the application itself ended.
    "withdrawn",
)
MAX_OFFERS_PER_SIDE = 3
OFFER_NOTE_MAX_LENGTH = 500


class QuoteOffer(Base):
    __tablename__ = "quote_offer"
    __table_args__ = (
        CheckConstraint(f"side IN {OFFER_SIDES}", name="side_allowed"),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_allowed"),
        CheckConstraint(
            f"note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND {OFFER_NOTE_MAX_LENGTH}",
            name="note_length",
        ),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN {OFFER_OUTCOMES}", name="outcome_allowed"
        ),
        # An answer always has its time, and nothing else does.
        CheckConstraint(
            "(outcome IS NULL) = (answered_at IS NULL)", name="answered_with_its_time"
        ),
        CheckConstraint(
            "answered_at IS NULL OR answered_at >= made_at", name="answered_after_made"
        ),
        # One open offer per application: a counter replaces the open one.
        Index(
            "uq_quote_offer_one_open",
            "application_id",
            unique=True,
            postgresql_where=text("outcome IS NULL"),
        ),
        # The history of one application, oldest first, and the foreign key's index.
        Index("ix_quote_offer_application_id_made_at", "application_id", "made_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("application.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Who named the figure.
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text(f"'{CURRENCY}'")
    )
    # A few words beside the figure. NULL when its maker said nothing.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    made_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL while open; see OFFER_OUTCOMES.
    outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # When it was answered or ended. NULL while open.
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
