import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# A token a person gives one assistant or agent (item 11, D-138): it reaches
# only the routes of its scopes (`auth.agent_scopes`), for at most
# AGENT_TOKEN_MAX_LIFETIME, until its owner revokes it. Only a keyed hash of
# the token is stored, never the token itself, which is shown once.
#
# The scopes never reach money, identity or the account's own control: no
# UPI ID, payment, phone number, passkey, session, export or deletion. Those
# stay with the person, behind a code from their phone.
AGENT_SCOPES: tuple[str, ...] = (
    "deals:read",
    "campaigns:read",
    "applications:write",
    "notes:write",
    "alerts:write",
)
AGENT_TOKEN_MAX_LIFETIME = timedelta(days=90)
AGENT_TOKEN_NAME_MAX_LENGTH = 60
AGENT_TOKEN_HASH_PATTERN = r"^[0-9a-f]{64}$"  # noqa: S105 - a format check, not a secret


def _sql_array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


class AgentToken(Base):
    __tablename__ = "agent_token"
    __table_args__ = (
        CheckConstraint(
            f"token_hash ~ '{AGENT_TOKEN_HASH_PATTERN}'", name="token_hash_format"
        ),
        CheckConstraint(
            f"char_length(name) BETWEEN 1 AND {AGENT_TOKEN_NAME_MAX_LENGTH}"
            " AND name = btrim(name) AND name !~ '[[:cntrl:]]'",
            name="name_shape",
        ),
        CheckConstraint(
            f"cardinality(scopes) >= 1 AND scopes <@ {_sql_array(AGENT_SCOPES)}",
            name="scopes_allowed",
        ),
        CheckConstraint(
            "expires_at > created_at"
            f" AND expires_at <= created_at + interval '{AGENT_TOKEN_MAX_LIFETIME.days} days'",
            name="lifetime_within_limit",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at", name="revoked_after_made"
        ),
        # The owner's list, newest first; its leading column indexes the
        # foreign key.
        Index("ix_agent_token_account_id_created_at", "account_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a token means nothing without its account. Erasure deletes
    # them first in any case (`auth.erasure`).
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    # What its owner called it, to tell one assistant from another.
    name: Mapped[str] = mapped_column(String(AGENT_TOKEN_NAME_MAX_LENGTH), nullable=False)
    # Unique, so one request finds its token by one index lookup.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Written at most once a minute (`auth.agent_tokens.LAST_USED_STEP`), so
    # a busy assistant is not a write per request.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Its owner revoked it, or logged out everywhere, moved to a new number or
    # deleted the account (D-138). NULL while it works.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set from the service's clock, so the lifetime check holds in tests too.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
