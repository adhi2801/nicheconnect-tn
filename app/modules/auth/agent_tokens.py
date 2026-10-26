"""Tokens for assistants and agents: making, checking and ending them (item 11, D-138).

A token is `nct_` and 256 random bits. The prefix lets a request be told
from a login's access token without a lookup, and lets secret scanners
(GitHub's, Gitleaks) recognise one that leaked. Only an HMAC of it is kept,
keyed by OTP_HASH_KEY under its own label, as step-up values are: a copy of
the table alone cannot even confirm a guess. Rotating that key ends every
token, which is the safe failure.

What a token may reach is `agent_scopes`; it is checked on every request
in `dependencies._authenticate`, with the account's suspension and deletion,
exactly as a login's token is. Making one, telling the owner and revoking
one live in `me.agent_token_service`, a layer up, because the owner is told.

Threat model (security.md section 4):

- **A token stolen from an assistant**: it reaches only its scopes, never
  money, identity or the account's control, for at most 90 days, and its
  owner sees it and when it was last used, and revokes it in one call.
- **Someone holding the phone or a session making one to keep access**:
  making one needs a code for exactly its scopes, the owner is told by a
  notice nobody can mute, and logging out everywhere ends every token too.
- **An assistant that misbehaves**: it shares its owner's rate limits and
  daily ceilings, so it can do no more than the person could.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth.exceptions import AgentTokenNotFound, InvalidToken
from app.modules.auth.models.account import Account
from app.modules.auth.models.agent_token import AgentToken

AGENT_TOKEN_PREFIX = "nct_"  # noqa: S105 - the prefix every token carries, not a secret
AGENT_TOKEN_BYTES = 32
# How stale `last_used_at` may get before a request writes it again: a busy
# assistant costs one write a minute, not one per request.
LAST_USED_STEP = timedelta(minutes=1)


def is_agent_token(token: str) -> bool:
    return token.startswith(AGENT_TOKEN_PREFIX)


def new_agent_token() -> str:
    """A fresh token, shown to its owner once and never stored."""
    return AGENT_TOKEN_PREFIX + secrets.token_urlsafe(AGENT_TOKEN_BYTES)


def scopes_value(scopes: list[str]) -> str:
    """The scopes as one value, for the step-up code that allows exactly them."""
    return ",".join(sorted(set(scopes)))


def hash_agent_token(token: str) -> str:
    """HMAC-SHA256 hex of a token, as stored in agent_token.token_hash."""
    key = settings.otp_hash_key.get_secret_value().encode()
    return hmac.new(key, b"agent-token\x00" + token.encode(), hashlib.sha256).hexdigest()


def account_for(db: Session, token: str, now: datetime) -> tuple[Account, AgentToken]:
    """The token's account and its row, if it still works. One query.

    Raises InvalidToken for a token that is unknown, revoked or expired, all
    alike, so nobody learns which. Writes `last_used_at` at most once per
    LAST_USED_STEP, and commits that alone: it runs before the route's own
    work, so nothing else is in the transaction.
    """
    found = db.execute(
        select(Account, AgentToken)
        .join(AgentToken, AgentToken.account_id == Account.id)
        .where(
            AgentToken.token_hash == hash_agent_token(token),
            AgentToken.revoked_at.is_(None),
            AgentToken.expires_at > now,
        )
    ).first()
    if found is None:
        raise InvalidToken()
    account, agent_token = found
    last_used = agent_token.last_used_at
    if last_used is None or now - last_used >= LAST_USED_STEP:
        db.execute(
            update(AgentToken)
            .where(AgentToken.id == agent_token.id)
            .values(last_used_at=now)
        )
        db.commit()
    return account, agent_token


def add(
    db: Session,
    account: Account,
    name: str,
    scopes: list[str],
    expires_at: datetime,
    now: datetime,
) -> tuple[AgentToken, str]:
    """Keep a new token for the account, returning it and its value. The caller commits."""
    value = new_agent_token()
    agent_token = AgentToken(
        account_id=account.id,
        name=name,
        token_hash=hash_agent_token(value),
        scopes=sorted(set(scopes)),
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    db.add(agent_token)
    db.flush()
    return agent_token, value


def list_live(
    db: Session,
    account_id: uuid.UUID,
    now: datetime,
    *,
    limit: int,
    cursor: str | None = None,
) -> Slice[AgentToken]:
    """The account's working tokens, newest first, a keyset page. One query.

    Raises InvalidCursor for a cursor that was not ours.
    """
    statement = (
        select(AgentToken)
        .where(
            AgentToken.account_id == account_id,
            AgentToken.revoked_at.is_(None),
            AgentToken.expires_at > now,
        )
        .order_by(AgentToken.created_at.desc(), AgentToken.id.desc())
    )
    if cursor is not None:
        statement = statement.where(
            older_than_cursor(AgentToken.created_at, AgentToken.id, cursor)
        )
    found = list(db.scalars(statement.limit(limit + 1)))
    return build_slice(found, limit, key=lambda item: (item.created_at, item.id))


def revoke_one(
    db: Session, account_id: uuid.UUID, token_id: uuid.UUID, now: datetime
) -> AgentToken:
    """Revoke one of the account's working tokens. The caller commits.

    Another account's token reads exactly as one that never existed, as an
    expired or revoked one does. Raises AgentTokenNotFound.
    """
    found = db.scalars(
        select(AgentToken)
        .where(
            AgentToken.id == token_id,
            AgentToken.account_id == account_id,
            AgentToken.revoked_at.is_(None),
            AgentToken.expires_at > now,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if found is None:
        db.rollback()
        raise AgentTokenNotFound()
    found.revoked_at = now
    found.updated_at = now
    return found


def revoke_all(db: Session, account_id: uuid.UUID, now: datetime) -> int:
    """Revoke every working token of the account. Returns how many. The caller commits."""
    result = cast(
        "CursorResult[Any]",
        db.execute(
            update(AgentToken)
            .where(
                AgentToken.account_id == account_id,
                AgentToken.revoked_at.is_(None),
                AgentToken.expires_at > now,
            )
            .values(revoked_at=now, updated_at=now)
        ),
    )
    return result.rowcount
