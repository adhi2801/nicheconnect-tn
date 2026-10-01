import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# The login identity. Holds the phone number, so it must never be embedded;
# brand and creator profiles point here by account_id instead.

# "admin" is created only by scripts/make_admin.py and never by login (D-061).
ACCOUNT_ROLES: tuple[str, ...] = ("brand", "creator", "admin")
# Why an account was suspended, and what a report is about: one list, so a
# suspension can always say which kind of report led to it (D-061).
REPORT_CATEGORIES: tuple[str, ...] = (
    "fake_profile",
    "spam",
    "abuse",
    "non_payment",
    "other",
)
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
        CheckConstraint(
            f"suspension_reason IS NULL OR suspension_reason IN {REPORT_CATEGORIES}",
            name="suspension_reason_allowed",
        ),
        # Suspended always says why; not suspended never carries a reason.
        CheckConstraint(
            "(suspended_at IS NULL) = (suspension_reason IS NULL)",
            name="suspension_has_reason",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    phone: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Set by an admin; checked on every request (D-061).
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspension_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
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
