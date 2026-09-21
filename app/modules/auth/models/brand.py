import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, String, text
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
