"""Passkeys: a key pair on the person's own device, bound to our domain (item 79, D-113).

We keep only the public half. A passkey answers a challenge we made, signed
by a private key that never leaves the phone, unlocked by its fingerprint,
face or screen lock; nothing a fake page or a SIM swapper can capture.

Three tables:
- `passkey`: one per key a person added, at most MAX_PASSKEYS each;
- `passkey_challenge`: each challenge we sent, used once, for 5 minutes,
  and, for a change, bound to exactly that change (its action and value, as
  for step-up codes, D-107);
- `passkey_reset`: someone who lost every passkey asks to remove them; it
  waits PASSKEY_RESET_WAIT, and any passkey login meanwhile cancels it.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.auth.models.step_up_challenge import STEP_UP_ACTIONS, VALUE_HASH_PATTERN

# Enough for a phone, a laptop, a tablet and spares, with every one listed.
MAX_PASSKEYS = 10
PASSKEY_NAME_MAX_LENGTH = 60
# WebAuthn allows a credential id of up to 1023 bytes; ours are random.
CREDENTIAL_ID_MAX_BYTES = 1023
PUBLIC_KEY_MAX_BYTES = 1024
CHALLENGE_BYTES = 32
PASSKEY_CHALLENGE_TTL = timedelta(minutes=5)
CHALLENGE_PURPOSES: tuple[str, ...] = ("register", "login", "step_up")
# As long as a lost number's change (D-110), and for the same reason: the
# owner, if it was not them, signs in once with a passkey to cancel it.
PASSKEY_RESET_WAIT = timedelta(days=7)


class Passkey(Base):
    __tablename__ = "passkey"
    __table_args__ = (
        CheckConstraint(
            f"octet_length(credential_id) BETWEEN 16 AND {CREDENTIAL_ID_MAX_BYTES}",
            name="credential_id_length",
        ),
        CheckConstraint(
            f"octet_length(public_key) BETWEEN 1 AND {PUBLIC_KEY_MAX_BYTES}",
            name="public_key_length",
        ),
        CheckConstraint("sign_count >= 0", name="sign_count_not_negative"),
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        # A key cannot report itself backed up unless it may be (WebAuthn's
        # BE and BS flags).
        CheckConstraint(
            "backup_eligible OR NOT backup_state", name="backed_up_only_if_eligible"
        ),
        CheckConstraint(
            "last_used_at IS NULL OR last_used_at >= created_at",
            name="used_after_added",
        ),
        Index("ix_passkey_account_id", "account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a key means nothing without its account.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    # The public key, as the authenticator gave it (COSE, CBOR-encoded).
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # The authenticator's own counter; synced passkeys keep it at 0.
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Which kind of authenticator made it (a password manager, a security
    # key), as it says; never who the person is.
    aaguid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Whether it may be synced to the person's other devices, and is.
    backup_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    backup_state: Mapped[bool] = mapped_column(Boolean, nullable=False)
    name: Mapped[str] = mapped_column(String(PASSKEY_NAME_MAX_LENGTH), nullable=False)
    # NULL until it is first used to sign in or approve a change.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PasskeyChallenge(Base):
    __tablename__ = "passkey_challenge"
    __table_args__ = (
        CheckConstraint(f"purpose IN {CHALLENGE_PURPOSES}", name="purpose_allowed"),
        CheckConstraint(
            f"octet_length(challenge) = {CHALLENGE_BYTES}", name="challenge_length"
        ),
        # A login's challenge is sent before anyone is known; every other
        # one is the signed-in account's.
        CheckConstraint(
            "purpose = 'login' OR account_id IS NOT NULL", name="account_unless_login"
        ),
        # A change's challenge names the change and its value; no other does.
        CheckConstraint(
            "(purpose = 'step_up') = (action IS NOT NULL)"
            " AND (action IS NULL) = (value_hash IS NULL)",
            name="change_only_for_step_up",
        ),
        CheckConstraint(
            f"action IS NULL OR action IN {STEP_UP_ACTIONS}", name="action_allowed"
        ),
        CheckConstraint(
            f"value_hash IS NULL OR value_hash ~ '{VALUE_HASH_PATTERN}'",
            name="value_hash_format",
        ),
        CheckConstraint(
            "expires_at = created_at + interval '5 minutes'",
            name="expires_five_minutes_after_created",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="consumed_after_created",
        ),
        # The account's challenges; its first column serves the foreign key.
        Index(
            "ix_passkey_challenge_account_id_created_at",
            "account_id",
            text("created_at DESC"),
        ),
        # The job's tidy-up of expired challenges.
        Index("ix_passkey_challenge_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a challenge means nothing without its account. NULL for a
    # login's, sent before anyone is known.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    # Random, from the operating system; a nonce, not a secret, and useless
    # without the private key that must sign it.
    challenge: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    # For a change only: which, and an HMAC of its value (step_up_service).
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    value_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL until answered (single use).
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PasskeyReset(Base):
    __tablename__ = "passkey_reset"
    __table_args__ = (
        CheckConstraint(
            "takes_effect_at = requested_at + interval '7 days'",
            name="takes_effect_seven_days_after_request",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a waiting reset means nothing without its account. Unique:
    # one waits at a time, and its first column serves the foreign key.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    takes_effect_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
