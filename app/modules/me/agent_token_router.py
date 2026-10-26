"""Tokens for assistants and agents (HTTP; item 11, D-138).

The rules: agent_token_service, auth.agent_tokens and auth.agent_scopes.

Not an IdempotentRoute: the answer to making a token carries the token,
which must never be kept, and a replay store keeps answers. A retry is
refused instead, since its code is spent; ask for another.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, StepUpCode, get_now
from app.modules.me import agent_token_service as service
from app.modules.me.agent_token_schemas import (
    AgentTokenCreate,
    AgentTokenCreated,
    AgentTokenRead,
)

READ_LIMIT = "60 per minute"
# A code from the phone stands behind each, with the phone's own caps.
CREATE_LIMIT = "5 per minute;10 per day"
REVOKE_LIMIT = "30 per minute"

router = APIRouter(prefix="/api/v1/me", tags=["auth"])

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc(
        "`agent_scope_missing`: an assistant's token cannot manage tokens; only you can"
    ),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.post(
    "/agent-tokens",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentTokenCreated,
    summary="Make a token for an assistant",
    description=(
        "Makes a token for one assistant or agent (Claude, ChatGPT, an MCP "
        "client) that may do only what its `scopes` allow, for at most 90 days, "
        "until you revoke it. No scope reaches money, your phone, passkeys, "
        "sessions, exports or deletion. Needs **a code** for exactly these "
        "scopes: ask at `POST /api/v1/me/step-up` with `create_agent_token` and "
        "the same `scopes`, then send it in the `Step-Up-Code` header. You are "
        "told in the app, in a notice that cannot be turned off. **The token is "
        "in this answer only**: we keep no copy we could show again. Logging "
        "out everywhere, moving to a new number or deleting your account ends "
        "every token. Brands and creators only. Limits: 5 a minute, 10 a day."
    ),
    responses={
        **_COMMON,
        400: problem_doc("The code is wrong, expired, used, or for other scopes"),
        401: problem_doc(
            "No access token, or it is invalid or expired; or `step_up_required`: "
            "no code was sent"
        ),
        403: problem_doc(
            "`role_not_allowed`: an admin cannot make one; or "
            "`agent_scope_missing`: an assistant's token cannot make another"
        ),
        422: problem_doc(
            "The name, a scope or the number of days is not usable, or the code "
            "is not 6 digits"
        ),
    },
)
@rate_limit(CREATE_LIMIT)
def create_agent_token(
    request: Request,
    body: AgentTokenCreate,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    step_up_code: StepUpCode = None,
) -> AgentTokenCreated:
    agent_token, value = service.create(
        db,
        account,
        body.name,
        list(body.scopes),
        body.expires_in_days,
        step_up_code,
        now,
    )
    return AgentTokenCreated(
        **AgentTokenRead.model_validate(agent_token).model_dump(), token=value
    )


@router.get(
    "/agent-tokens",
    response_model=Page[AgentTokenRead],
    summary="My assistants' tokens",
    description=(
        "Every token of yours that still works, newest first, with its scopes, "
        "its end and when it was last used (to within a minute), never its "
        "value. Paginated: `limit` (default 20, at most 100) and `cursor`. "
        "Limit: 60 requests per minute."
    ),
    responses={
        **_COMMON,
        422: problem_doc("`limit` is out of range, or `cursor` is not one of ours"),
    },
)
@rate_limit(READ_LIMIT)
def list_agent_tokens(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(description="From a previous page")] = None,
) -> Page[AgentTokenRead]:
    page = service.list_mine(db, account, now, limit=limit, cursor=cursor)
    return Page(
        items=[AgentTokenRead.model_validate(found) for found in page.rows],
        next_cursor=page.next_cursor,
    )


@router.delete(
    "/agent-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an assistant's token",
    description=(
        "The token stops working on its next request. No code is needed: "
        "revoking only takes access away. Limit: 30 requests per minute."
    ),
    responses={
        **_COMMON,
        204: {"description": "The token is revoked"},
        404: problem_doc(
            "`agent_token_not_found`: no working token of yours has this id "
            "(another account's reads the same, as does one revoked or expired)"
        ),
        422: problem_doc("The id is not a UUID"),
    },
)
@rate_limit(REVOKE_LIMIT)
def revoke_agent_token(
    request: Request,
    token_id: uuid.UUID,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    service.revoke(db, account, token_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
