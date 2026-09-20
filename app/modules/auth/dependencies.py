"""FastAPI dependencies for the auth module."""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.exceptions import InvalidToken, RoleNotAllowed
from app.modules.auth.models.account import Account
from app.modules.auth.tokens import account_id_for_scoping, decode_access_token

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
    account_id = account_id_for_scoping(token)
    return f"account:{account_id}" if account_id is not None else None


def get_now() -> datetime:
    """The current UTC time. Tests override this to control expiry and limits."""
    return datetime.now(timezone.utc)


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
    if credentials is None or not credentials.credentials:
        raise InvalidToken(headers=UNAUTHENTICATED_HEADERS)

    claims = decode_access_token(credentials.credentials, now)
    account = db.get(Account, claims.account_id)
    if account is None or account.role != claims.role:
        # Account deleted, or its role changed after the token was issued.
        raise InvalidToken(headers=UNAUTHENTICATED_HEADERS)
    # For logging and later ownership checks.
    request.state.account_id = account.id
    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]


def require_role(role: str) -> Callable[[Account], Account]:
    """Dependency factory: only accounts with `role` may use the endpoint."""

    def check_role(account: CurrentAccount) -> Account:
        if account.role != role:
            raise RoleNotAllowed()
        return account

    return check_role


CurrentBrand = Annotated[Account, Depends(require_role("brand"))]
CurrentCreator = Annotated[Account, Depends(require_role("creator"))]
