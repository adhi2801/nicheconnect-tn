"""A person's tokens for assistants: making, listing and revoking them (item 11, D-138).

The rules and the threat model are `auth.agent_tokens`, and what each scope
reaches is `auth.agent_scopes`. Here, in `me`, because making one tells the
owner, and notifications sit a layer above auth (D-099).

Only a person manages their tokens: these routes are in no scope, so a token
can never make, list or revoke one, nor step up for anything.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.export import ExportedSection, allow, build_section
from app.core.pagination import Slice
from app.modules.auth import agent_tokens
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.exceptions import RoleNotAllowed
from app.modules.auth.models.account import Account
from app.modules.auth.models.agent_token import AgentToken
from app.modules.notifications import service as notifications

AGENT_TOKEN_ROLES = ("brand", "creator")
EXPORTED_TABLES = frozenset({"agent_token"})
# What a person can recognise each token by; never its hash.
EXPORT_FIELDS = allow(
    "id",
    "name",
    "scopes",
    "expires_at",
    "last_used_at",
    "revoked_at",
    "created_at",
    "updated_at",
)


def ensure_may_have_tokens(account: Account) -> None:
    """Raises RoleNotAllowed for an admin: no admin token exists (D-138)."""
    if account.role not in AGENT_TOKEN_ROLES:
        raise RoleNotAllowed(
            "An admin's every act is their own; no token can act for one."
        )


def create(
    db: Session,
    account: Account,
    name: str,
    scopes: list[str],
    expires_in_days: int,
    step_up_code: str | None,
    now: datetime,
) -> tuple[AgentToken, str]:
    """Make a token, proven by a code for exactly these scopes. Commits.

    The owner is told by a notice nobody can mute, so a token made by
    someone else holding the account is seen. Raises RoleNotAllowed and what
    step_up_service.consume raises.
    """
    ensure_may_have_tokens(account)
    step_ups.consume(
        db,
        account,
        "create_agent_token",
        agent_tokens.scopes_value(scopes),
        step_up_code,
        now,
    )
    agent_token, value = agent_tokens.add(
        db, account, name, scopes, now + timedelta(days=expires_in_days), now
    )
    notifications.record(
        db,
        account_id=account.id,
        notification_type="agent_token_created",
        now=now,
        details={
            "agent_token_id": str(agent_token.id),
            "name": agent_token.name,
            "scopes": agent_token.scopes,
            "expires_at": agent_token.expires_at.isoformat(),
        },
    )
    db.commit()
    return agent_token, value


def list_mine(
    db: Session, account: Account, now: datetime, *, limit: int, cursor: str | None
) -> Slice[AgentToken]:
    """The account's working tokens, newest first. Raises InvalidCursor."""
    return agent_tokens.list_live(db, account.id, now, limit=limit, cursor=cursor)


def revoke(db: Session, account: Account, token_id: uuid.UUID, now: datetime) -> None:
    """Revoke one of the account's tokens: it stops on its next request. Commits.

    No code is needed: revoking only ever takes access away. Raises
    AgentTokenNotFound.
    """
    agent_tokens.revoke_one(db, account.id, token_id, now)
    db.commit()


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """Every token the account made, working or not, without its value or hash."""
    tokens = list(
        db.scalars(
            select(AgentToken)
            .where(AgentToken.account_id == account_id)
            .order_by(AgentToken.created_at, AgentToken.id)
        )
    )
    return [
        build_section(
            "agent_tokens",
            table="agent_token",
            purpose=(
                "The tokens you gave assistants: what you called each, what it "
                "could do, when it was last used, and when it ended. We keep only "
                "a keyed fingerprint of each token, never the token."
            ),
            objects=tokens,
            fields=EXPORT_FIELDS,
        )
    ]
