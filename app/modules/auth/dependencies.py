"""FastAPI dependencies for the auth module."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.session import get_db
from app.modules.auth import agent_scopes, agent_tokens, sessions
from app.modules.auth.exceptions import (
    AccountSuspended,
    AdminNotFound,
    AgentScopeMissing,
    InvalidToken,
    RoleNotAllowed,
)
from app.modules.auth.models.account import Account
from app.modules.auth.step_up_service import STEP_UP_HEADER
from app.modules.auth.tokens import (
    AccessTokenClaims,
    account_id_for_scoping,
    decode_access_token,
)

# auto_error=False: a missing header raises our InvalidToken, so every auth
# failure comes back in the same shape instead of FastAPI's own error body.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token from login")
UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def idempotency_identity(request: Request) -> str | None:
    """Whose request this is, for grouping a retry with its original.

    Scoping by the account rather than the raw token means a client that
    refreshed its access token between the first attempt and the retry still
    gets its first answer back. The signature is verified inside
    `account_id_for_scoping`, so this cannot be pointed at someone else.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    if agent_tokens.is_agent_token(token):
        # An assistant's token (D-138): its keyed hash names it without a
        # lookup, and only its holder can produce it.
        return f"agent:{agent_tokens.hash_agent_token(token)}"
    account_id = account_id_for_scoping(token)
    return f"account:{account_id}" if account_id is not None else None


def get_now() -> datetime:
    """The current UTC time. Tests override this to control expiry and limits."""
    return datetime.now(UTC)


def get_current_account(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Account:
    """The account behind the request's access token.

    Every protected endpoint depends on this. Raises InvalidToken when the
    header is missing or the token is unusable. The account is loaded fresh,
    so a deleted account cannot keep using a token that has not expired yet.
    """
    return _authenticate(request, credentials, db, now)[0]


def _authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    now: datetime,
) -> tuple[Account, AccessTokenClaims]:
    """The account and the token's claims, for the checks that read both."""
    if credentials is None or not credentials.credentials:
        raise InvalidToken(headers=UNAUTHENTICATED_HEADERS)
    if agent_tokens.is_agent_token(credentials.credentials):
        return _authenticate_agent(request, credentials.credentials, db, now)

    claims = decode_access_token(credentials.credentials, now)
    account, session_live = sessions.account_for_token(
        db, claims.account_id, claims.session_id
    )
    if account is None or account.role != claims.role or account.deleted_at is not None:
        # Account gone or deleted (D-122), or its role changed after the token
        # was issued.
        raise InvalidToken(headers=UNAUTHENTICATED_HEADERS)
    if account.suspended_at is not None:
        # Checked here, on every request, so a suspension takes effect at once
        # even for a token that has not expired (D-061).
        raise AccountSuspended.because(account.suspension_reason)
    if not session_live:
        # Its session was ended: a logout, logging out everywhere, ending it
        # from another device, a phone number moved. Checked on every
        # request, so the token stops at once, not when it expires (D-114).
        raise InvalidToken(headers=UNAUTHENTICATED_HEADERS)
    # For logging and later ownership checks.
    request.state.account_id = account.id
    # For the checks that need the login to be old enough (D-109).
    request.state.authenticated_at = claims.authenticated_at
    # For telling this device's session from the others (D-114).
    request.state.session_id = claims.session_id
    return account, claims


def _authenticate_agent(
    request: Request, token: str, db: Session, now: datetime
) -> tuple[Account, AccessTokenClaims]:
    """An assistant's token (item 11, D-138): its account, only on a route of its scopes.

    Denied by default: the route that matched must be listed in
    `agent_scopes` under one of the token's scopes, by its path template.
    Deletion and suspension stop a token exactly as they stop a login.
    """
    try:
        account, agent_token = agent_tokens.account_for(db, token, now)
    except InvalidToken:
        raise InvalidToken(headers=UNAUTHENTICATED_HEADERS) from None
    if account.deleted_at is not None:
        raise InvalidToken(headers=UNAUTHENTICATED_HEADERS)
    if account.suspended_at is not None:
        raise AccountSuspended.because(account.suspension_reason)
    route = request.scope.get("route")
    # HEAD is answered by a GET route, and reads the same.
    method = "GET" if request.method == "HEAD" else request.method
    if not isinstance(route, APIRoute) or not agent_scopes.allows(
        agent_token.scopes, method, route.path
    ):
        raise AgentScopeMissing()
    claims = AccessTokenClaims(
        account_id=account.id, role=account.role, expires_at=agent_token.expires_at
    )
    request.state.account_id = account.id
    request.state.agent_token_id = agent_token.id
    # No login stands behind a token: it counts as one made just now, so no
    # check that wants an established login can pass with it.
    request.state.authenticated_at = now
    request.state.session_id = None
    # Last of all, so only a request that passed every check is a use.
    agent_tokens.mark_used(db, agent_token, now)
    return account, claims


CurrentAccount = Annotated[Account, Depends(get_current_account)]


def get_login_time(request: Request, account: CurrentAccount) -> datetime | None:
    """When the signed-in person's login was proven (the token's `auth_time`).

    None for a token signed before D-109, which counts as a login made just
    now. Depends on CurrentAccount, so the token is always checked first.
    """
    authenticated_at: datetime | None = request.state.authenticated_at
    return authenticated_at


LoginTime = Annotated[datetime | None, Depends(get_login_time)]


def get_session_id(request: Request, account: CurrentAccount) -> uuid.UUID | None:
    """Which session the signed-in person's token belongs to (its `sid`).

    None for a token signed before D-114. Depends on CurrentAccount, so the
    token is always checked first.
    """
    session_id: uuid.UUID | None = request.state.session_id
    return session_id


CurrentSessionId = Annotated[uuid.UUID | None, Depends(get_session_id)]


def require_role(role: str) -> Callable[[Account], Account]:
    """Dependency factory: only accounts with `role` may use the endpoint."""

    def check_role(account: CurrentAccount) -> Account:
        if account.role != role:
            raise RoleNotAllowed()
        return account

    return check_role


CurrentBrand = Annotated[Account, Depends(require_role("brand"))]
CurrentCreator = Annotated[Account, Depends(require_role("creator"))]


def get_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Account:
    """The signed-in admin, or 404 for anyone else (D-061).

    Here, beside every other access check, so any module may guard a route
    for admins without importing the admin API above it (D-099). An admin
    token must also say both factors were proven (D-105): one made from the
    phone code alone, by any route old or new, is a plain 404 too.
    """
    try:
        account, claims = _authenticate(request, credentials, db, now)
    except DomainError:
        raise AdminNotFound() from None
    if account.role != "admin" or not claims.is_multi_factor:
        raise AdminNotFound()
    return account


CurrentAdmin = Annotated[Account, Depends(get_admin)]


# The code a risky change carries (item 82, D-107): from POST /me/step-up,
# or an admin's authenticator. Optional here, so that leaving it out is
# answered by step_up_service as `step_up_required`, never a 422.
StepUpCode = Annotated[
    str | None,
    Header(
        alias=STEP_UP_HEADER,
        pattern=r"^[0-9]{6}$",
        description=(
            "The 6-digit code from `POST /api/v1/me/step-up` for exactly this "
            "change, or an admin's authenticator code. Without it the answer "
            "is 401 `step_up_required`."
        ),
    ),
]
