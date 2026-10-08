"""How each account arrived, and the codes people invite others with (D-080).

Attribution not recorded at sign-up can never be recovered (D-071): the
pilot's whole question is which channel brings brands and creators. So the
answer is written once, in the same transaction that creates the account,
and never changed afterwards.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Eight characters with nothing that reads as something else: no 0 or O, no
# 1 or I, so a code read aloud or copied from a photo survives.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
CODE_PATTERN = f"^[{CODE_ALPHABET}]{{{CODE_LENGTH}}}$"

# Where a new account says it heard of us. `invite` is set only by a valid
# invite code; `not_given` when the app sent nothing.
ARRIVAL_SOURCES: tuple[str, ...] = (
    "invite",
    "passport_link",
    "instagram",
    "whatsapp",
    "event",
    "search",
    "other",
    "not_given",
)
CAMPAIGN_TAG_PATTERN = "^[a-z0-9-]{1,40}$"


class InviteCode(Base):
    """One code per account, made the first time the person asks for it."""

    __tablename__ = "invite_code"
    __table_args__ = (CheckConstraint(f"code ~ '{CODE_PATTERN}'", name="code_format"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: the code is the person's own; it goes with their account, and
    # the attributions that used it keep their source but lose the link.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    code: Mapped[str] = mapped_column(String(CODE_LENGTH), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccountAttribution(Base):
    """How one account arrived. Written once, at sign-up."""

    __tablename__ = "account_attribution"
    __table_args__ = (
        CheckConstraint(f"source IN {ARRIVAL_SOURCES}", name="source_allowed"),
        CheckConstraint(
            f"campaign_tag IS NULL OR campaign_tag ~ '{CAMPAIGN_TAG_PATTERN}'",
            name="campaign_tag_format",
        ),
        # A code means an invitation. The reverse need not hold: the inviter's
        # account may since have gone, taking the link but not the history.
        CheckConstraint(
            "invite_code_id IS NULL OR source = 'invite'", name="code_means_invite"
        ),
        # "Who joined with my code?" and the foreign key both need it.
        Index("ix_account_attribution_invite_code_id", "invite_code_id"),
        # The admin's sign-ups by source and week.
        Index("ix_account_attribution_source_created_at", "source", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: how a person arrived is about them; it goes with them.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # SET NULL: the inviter leaving must not erase that this account was invited.
    invite_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invite_code.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    # A label the founders put on a link or a poster, such as "codissia-oct".
    campaign_tag: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
