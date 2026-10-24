import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Brand(Base):
    __tablename__ = "brand"
    __table_args__ = (
        # Emails are stored lowercase, so the plain unique rule on email
        # also blocks duplicates that differ only in capitals.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        # account_role is always 'brand'; paired with account_id it forces the
        # linked account to have that role, and stops one account owning both
        # profiles or changing role while a profile exists (D-014).
        CheckConstraint("account_role = 'brand'", name="account_role_fixed"),
        ForeignKeyConstraint(
            ["account_id", "account_role"],
            ["account.id", "account.role"],
            ondelete="RESTRICT",
        ),
        # A clearance is the exact name an admin cleared and when (D-119);
        # who cleared it may be forgotten (SET NULL), the fact never alone.
        CheckConstraint(
            "(name_cleared IS NULL) = (name_cleared_at IS NULL)",
            name="name_cleared_with_its_time",
        ),
        CheckConstraint(
            "name_cleared_by_account_id IS NULL OR name_cleared IS NOT NULL",
            name="name_cleared_by_only_with_a_clearance",
        ),
        # The foreign key's index (database.md section 5).
        Index("ix_brand_name_cleared_by_account_id", "name_cleared_by_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        # Unique: one profile per account. The unique index also serves as the FK index.
        unique=True,
    )
    # Always 'brand': see the constraints above (D-014).
    account_role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'brand'")
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    # An admin's review of a name that looks like a protected brand's (item 75,
    # D-119): the exact name cleared, so it counts only while the brand keeps
    # it, and a rename is looked at afresh. NULL means never cleared.
    name_cleared: Mapped[str | None] = mapped_column(String(150), nullable=True)
    name_cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # SET NULL: the clearance outlives the admin's account; the admin log
    # keeps who it was.
    name_cleared_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
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
