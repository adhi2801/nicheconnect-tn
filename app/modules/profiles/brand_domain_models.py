"""A brand's claim to control a website's domain (item 74, D-106).

Fake brands are the scam that starts most others (trust-and-safety.md
section 2). A brand proves it controls the DNS of the domain it names by
publishing a token we gave it in a TXT record at
`_nicheconnect-challenge.<domain>`, as the IETF's draft best practice for
DNS domain verification describes (draft-ietf-dnsop-domain-verification-
techniques-13). Creators then see the domain itself, since when, and when
the registry says it was registered: a fact they can check, never the word
"verified" on its own (legal.md rule 3).

A claim is **pending** until a check finds the token, **verified** after,
and **lapsed** once three daily checks in a row find it gone. A lapsed claim
is never revived: the brand claims again and gets a new token, so a domain
that changed hands never inherits an old verification (the draft, 9.13).

One claim per brand; one verified holder per domain, held by the database.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

DOMAIN_STATUSES: tuple[str, ...] = ("pending", "verified", "lapsed")
# found: both resolvers saw the token. absent: both answered, and not both
# saw it. unknown: a resolver could not be asked. taken: found, but another
# brand already holds the domain.
CHECK_RESULTS: tuple[str, ...] = ("found", "absent", "unknown", "taken")
DOMAIN_MAX_LENGTH = 253
# Lower-case letters, digits and hyphens, at least two labels, none starting
# or ending with a hyphen. Punycode (xn--) is refused separately.
DOMAIN_PATTERN = (
    r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])?$"
)
TOKEN_LENGTH = 26  # 128 bits, base32, lower case
TOKEN_PATTERN = r"^[a-z2-7]{26}$"  # noqa: S105 - a format check, not a secret
# Three daily checks in a row without the token, and a verified domain
# lapses: a DNS outage of a day or two never costs a brand its mark.
MAX_ABSENT_CHECKS = 3


class BrandDomain(Base):
    __tablename__ = "brand_domain"
    __table_args__ = (
        CheckConstraint(f"status IN {DOMAIN_STATUSES}", name="status_allowed"),
        CheckConstraint(
            f"last_result IS NULL OR last_result IN {CHECK_RESULTS}",
            name="last_result_allowed",
        ),
        CheckConstraint(
            "domain = lower(domain)"
            f" AND char_length(domain) <= {DOMAIN_MAX_LENGTH}"
            f" AND domain ~ '{DOMAIN_PATTERN}'"
            " AND domain NOT LIKE '%xn--%'",
            name="domain_format",
        ),
        CheckConstraint(f"token ~ '{TOKEN_PATTERN}'", name="token_format"),
        # The token is good for 7 days of trying (GitHub's span too).
        CheckConstraint(
            "token_expires_at = claimed_at + interval '7 days'",
            name="token_lasts_seven_days",
        ),
        CheckConstraint(
            "(last_checked_at IS NULL) = (last_result IS NULL)",
            name="checked_with_a_result",
        ),
        # Verified once means verified_at stays, lapsed or not.
        CheckConstraint(
            "(status = 'pending') = (verified_at IS NULL)",
            name="verified_at_once_verified",
        ),
        CheckConstraint(
            "(status = 'lapsed') = (lapsed_at IS NOT NULL)",
            name="lapsed_at_when_lapsed",
        ),
        CheckConstraint(
            "verified_at IS NULL OR verified_at >= claimed_at",
            name="verified_after_claimed",
        ),
        CheckConstraint(
            "lapsed_at IS NULL OR lapsed_at >= verified_at",
            name="lapsed_after_verified",
        ),
        CheckConstraint(
            f"consecutive_absent BETWEEN 0 AND {MAX_ABSENT_CHECKS}",
            name="consecutive_absent_range",
        ),
        # One verified holder per domain.
        Index(
            "uq_brand_domain_verified_domain",
            "domain",
            unique=True,
            postgresql_where=text("status = 'verified'"),
        ),
        # What the checking job reads: checks asked for, and verified
        # domains by when they were last checked.
        Index(
            "ix_brand_domain_check_requested_at",
            "check_requested_at",
            postgresql_where=text("check_requested_at IS NOT NULL"),
        ),
        Index(
            "ix_brand_domain_verified_last_checked_at",
            "last_checked_at",
            postgresql_where=text("status = 'verified'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: the claim is the brand's own thing. Unique: one per brand,
    # and the index the foreign key needs.
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    domain: Mapped[str] = mapped_column(String(DOMAIN_MAX_LENGTH), nullable=False)
    # Public by design: the brand publishes it in DNS for anyone to read.
    token: Mapped[str] = mapped_column(String(TOKEN_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'pending'")
    )
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # NULL means no check is waiting.
    check_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When a check run took this claim, so another run leaves it; NULL when
    # none has. A run that died leaves it stale, and a later one retakes it.
    checking_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL until the first check.
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_result: Mapped[str | None] = mapped_column(String(10), nullable=True)
    consecutive_absent: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    # NULL while pending.
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL unless lapsed.
    lapsed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Whether both resolvers said the answer was DNSSEC-signed and checked,
    # at the last check that found the token. NULL until one has.
    dnssec_validated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # When the registry says the domain was registered (RDAP). NULL when it
    # did not say, or has not been asked yet.
    registered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
