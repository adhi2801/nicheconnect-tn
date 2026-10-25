import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint, text
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
    # Item 51: the IT Rules give these two a 2-hour clock (rule 3(2)(b)), so a
    # report of either must be told apart from the others when it is filed.
    "impersonation",
    "intimate_content",
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
        # Deleting the account (item 6, D-122): asked for, then 30 days in
        # which it can be cancelled, then done. Only a deleted account lacks
        # a phone number, and a deleted one never has one, so the number is
        # free for whoever holds it next.
        CheckConstraint(
            "(deletion_requested_at IS NULL) = (deletion_takes_effect_at IS NULL)",
            name="deletion_requested_with_its_date",
        ),
        CheckConstraint(
            "deletion_takes_effect_at = deletion_requested_at + interval '30 days'",
            name="deletion_takes_effect_thirty_days_after",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR deletion_requested_at IS NOT NULL",
            name="deleted_only_after_a_request",
        ),
        CheckConstraint(
            "(deleted_at IS NULL) = (phone IS NOT NULL)", name="phone_until_deleted"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # NULL only once the account is deleted (D-122).
    phone: Mapped[str | None] = mapped_column(String(16), nullable=True, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Set by an admin; checked on every request (D-061).
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspension_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # When the person confirmed they are 18 or over, by giving a date of
    # birth we checked and did not keep (D-086). NULL for accounts made
    # before the rule, and until a profile is created.
    adult_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # "Passkey only" sign-in (item 79, D-113): when true, a phone code no
    # longer logs in; it can only start a passkey reset. Turned on and off
    # with a passkey.
    passkey_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Deleting the account (D-122): when its owner asked, when it takes
    # effect unless cancelled, and when it was done. NULL means never asked,
    # or cancelled; a deleted account keeps the first two as its history.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deletion_takes_effect_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
