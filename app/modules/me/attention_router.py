"""GET /api/v1/me/attention: what is waiting on the signed-in account.

The pull side of the reminders D-029 planned: they wait on a job runner,
this answers whenever the app is opened. See app/core/attention.py.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, CurrentSessionId, get_now
from app.modules.me import attention_service
from app.modules.me.schemas import AttentionRead, to_attention_read

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/me", tags=["attention"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    409: problem_doc("The profile has not been created yet"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/attention",
    response_model=AttentionRead,
    summary="What needs my attention",
    description=(
        "Everything waiting on the signed-in brand or creator, the most urgent "
        "first: any `new_sign_in` (a session signed in during the last 7 days, "
        "other than this one: if it was not you, end it at `DELETE "
        "/api/v1/me/sessions/{session_id}`), then overdue, then soonest due, "
        "then anything without a date. For a "
        "brand: applications to review, memos to draft or revise, proof to "
        "review before it approves itself, creators to pay, and disputes to "
        "answer. For a creator: memos to answer, work to deliver or redo, "
        "payments to confirm, payments owed past their date, and disputes to "
        "answer. Worked out from the records each time, so an item disappears "
        "the moment it is done. Items carry a `kind` code and the facts; the "
        "wording belongs to the app. At most 50 items; `counts` and `total` "
        "always cover everything, except that at most 50 new sign-ins are counted."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_my_attention(
    request: Request,
    account: CurrentAccount,
    session_id: CurrentSessionId,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AttentionRead:
    return to_attention_read(attention_service.for_account(db, account, now, session_id))
