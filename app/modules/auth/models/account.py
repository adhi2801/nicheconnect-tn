import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# The login identity. Holds the phone number, so it must never be embedded;
# brand and creator profiles point here by account_id instead.

ACCOUNT_ROLES: tuple[str, ...] = ("brand", "creator")
# Indian mobile numbers in E.164: +91, then 10 digits starting 6-9.
PHONE_PATTERN = r"^\+91[6-9][0-9]{9}$"


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint(f"phone ~ '{PHONE_PATTERN}'", name="phone_format"),
        CheckConstraint(
            "role IN (" + ", ".join(f"'{role}'" for role in ACCOUNT_ROLES) + ")",
            name="role_allowed",
        ),
        # Lets brand and creator reference (id, role) together, so a profile
        # can only belong to an account of its own role (D-014).
        # Full name given: the uq naming convention covers only the first column.
        UniqueConstraint("id", "role", name="uq_account_id_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    phone: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
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
