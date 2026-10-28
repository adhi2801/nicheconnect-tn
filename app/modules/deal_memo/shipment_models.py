"""A barter deal's shipment, on the record (item 68, D-131).

On an agreed barter deal the brand says how it sent the goods: the courier
and the tracking number, sealed onto the deal record as `product_shipped`.
Only the creator says they arrived (`product_received`), the way only the
creator confirms a payment arrived (D-027). "I sent it" and "I never got
it" then stand on the record, each dated, neither side able to rewrite the
other's.

We never hold an address: the brand and the creator settle that between
them, and a tracking number names no one. ON DELETE RESTRICT on the memo:
evidence of a deal must never vanish as a side effect.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# The couriers Tamil Nadu brands ship barter goods with; "other" for the
# rest. A carrier names how to read the number, never a promise about it.
CARRIERS: tuple[str, ...] = (
    "india_post",
    "delhivery",
    "blue_dart",
    "dtdc",
    "ecom_express",
    "xpressbees",
    "shadowfax",
    "ekart",
    "other",
)
# Couriers' own numbers vary (Delhivery and Blue Dart are given as 10 to 15
# digits by different guides), so only letters and digits, 8 to 20, are
# held to; India Post's is fixed: two letters, nine digits, then IN.
TRACKING_PATTERN = "^[A-Z0-9]{8,20}$"
INDIA_POST_PATTERN = "^[A-Z]{2}[0-9]{9}IN$"
TRACKING_MAX_LENGTH = 20


class BarterShipment(Base):
    __tablename__ = "barter_shipment"
    __table_args__ = (
        CheckConstraint(f"carrier IN {CARRIERS}", name="carrier_allowed"),
        CheckConstraint(
            f"tracking_number ~ '{TRACKING_PATTERN}'", name="tracking_number_shape"
        ),
        CheckConstraint(
            f"carrier <> 'india_post' OR tracking_number ~ '{INDIA_POST_PATTERN}'",
            name="india_post_number_shape",
        ),
        CheckConstraint(
            "received_at IS NULL OR received_at >= shipped_at",
            name="received_after_shipped",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # One shipment a deal; also the foreign key's index.
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    carrier: Mapped[str] = mapped_column(String(20), nullable=False)
    tracking_number: Mapped[str] = mapped_column(
        String(TRACKING_MAX_LENGTH), nullable=False
    )
    # When the brand said it shipped; a correction before arrival moves it.
    shipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When the creator said it arrived. NULL means they have not said so.
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
