"""An account's authenticator-app factor: the codes it shows (item 101, D-105).

Admins log in with two factors: the code sent to their phone, and the
6-digit code an authenticator app shows (TOTP, RFC 6238). A SIM swap or a
stolen WhatsApp then gives no admin session. The table is not specific to
admins, so a later second factor for brands and creators, and passkeys
(item 79), build on it.

A row is in one of two states, and the database holds which:

- **waiting**: a founder issued a setup ticket (`scripts/make_admin.py`); only
  the ticket's SHA-256 is kept, and it expires;
- **enrolled**: the ticket was redeemed for a secret. The secret is kept only
  encrypted (AES-256-GCM under SECOND_FACTOR_KEY, `second_factor_secrets.py`),
  so a copy of the database alone yields none.

`last_used_step` makes each code usable once (NIST SP 800-63B-4 section
3.1.4.2; ASVS 5.0 6.5.1). After MAX_CONSECUTIVE_FAILURES wrong codes in a row
the factor locks, and only a new ticket unlocks it.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# NIST allows up to 100; an admin who mistypes ten times in a row should be
# looked at by the other founder anyway.
MAX_CONSECUTIVE_FAILURES = 10
# 160 bits, RFC 4226's recommended length for an HMAC-SHA1 key.
SECRET_BYTES = 20
# AES-GCM's 12-byte nonce, the secret, and its 16-byte tag.
SECRET_CIPHERTEXT_BYTES = 12 + SECRET_BYTES + 16
TICKET_HASH_PATTERN = r"^[0-9a-f]{64}$"


class TotpFactor(Base):
    __tablename__ = "totp_factor"
    __table_args__ = (
        # Waiting for setup or enrolled, never both and never neither.
        CheckConstraint(
            "(secret_ciphertext IS NULL) <> (ticket_hash IS NULL)",
            name="waiting_or_enrolled",
        ),
        CheckConstraint(
            "(ticket_hash IS NULL) = (ticket_expires_at IS NULL)",
            name="ticket_has_an_expiry",
        ),
        CheckConstraint(
            "(secret_ciphertext IS NULL) = (enrolled_at IS NULL)",
            name="enrolled_when_it_has_a_secret",
        ),
        CheckConstraint(
            f"ticket_hash IS NULL OR ticket_hash ~ '{TICKET_HASH_PATTERN}'",
            name="ticket_hash_format",
        ),
        CheckConstraint(
            "secret_ciphertext IS NULL"
            f" OR octet_length(secret_ciphertext) = {SECRET_CIPHERTEXT_BYTES}",
            name="secret_ciphertext_length",
        ),
        CheckConstraint(
            "last_used_step IS NULL OR last_used_step >= 0",
            name="last_used_step_not_negative",
        ),
        CheckConstraint(
            f"consecutive_failures BETWEEN 0 AND {MAX_CONSECUTIVE_FAILURES}",
            name="consecutive_failures_range",
        ),
        # Locked exactly when the failures reached the limit.
        CheckConstraint(
            "(locked_at IS NOT NULL)"
            f" = (consecutive_failures = {MAX_CONSECUTIVE_FAILURES})",
            name="locked_at_the_limit",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a factor means nothing without its account. Unique: one each,
    # and the index the foreign key needs.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # NULL means waiting for setup: a ticket has been issued, not redeemed.
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # SHA-256 hex of the setup ticket. NULL once it is redeemed.
    ticket_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # NULL with the ticket.
    ticket_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL until the ticket is redeemed.
    enrolled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The 30-second step of the last code accepted. NULL means none yet.
    last_used_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    # NULL means not locked.
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
