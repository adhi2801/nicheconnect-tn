"""Deal notes on the record (HTTP, item 17, D-128). The rules: note_service."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.deal_memo import note_service as service
from app.modules.deal_memo.dependencies import MemoId, party_memo
from app.modules.deal_memo.schemas import NoteCreate, NoteRead

READ_LIMIT = "60 per minute"
# A ceiling per day as well as per minute: a note reaches the other side
# (trust-and-safety.md rule 2).
WRITE_LIMIT = "30 per minute;200 per day"

# route_class: a retry with the same Idempotency-Key gets the first answer,
# and no second note is written (backend.md section 2).
router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["deal memos"], route_class=IdempotentRoute
)

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Notes per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    404: problem_doc("No such deal, or it is not yours"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/{memo_id}/notes",
    response_model=Page[NoteRead],
    summary="A deal's notes",
    description=(
        "Every note either side wrote on this deal, newest first; pass "
        "`next_cursor` back as `cursor` for older ones. Each is sealed onto the "
        "deal's record (`GET /api/v1/deal-memos/{memo_id}/record`, "
        "`notes_unchanged`). The brand and the creator of this deal only."
    ),
    responses={**_COMMON, 422: problem_doc("A query parameter or the cursor is invalid")},
)
@rate_limit(READ_LIMIT)
def list_notes(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
) -> Page[NoteRead]:
    memo = party_memo(db, request, memo_id, account)
    result = service.page(db, memo, limit=limit, cursor=cursor)
    return Page[NoteRead](
        items=[NoteRead.model_validate(note) for note in result.rows],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/{memo_id}/notes",
    status_code=status.HTTP_201_CREATED,
    response_model=NoteRead,
    summary="Write a note on a deal",
    description=(
        "A plain note, at most 1,000 characters, from the memo being sent until "
        "the deal ends. It is sealed onto the deal's record by its fingerprint, "
        "so either side can prove later what was said, and it never changes: "
        "a correction is another note. The other side is told. Limits: 30 a "
        "minute and 200 a day."
    ),
    responses={
        **_COMMON,
        409: problem_doc("`notes_closed`: the memo is a draft, or the deal has ended"),
        422: problem_doc("The note is empty or too long"),
    },
)
@rate_limit(WRITE_LIMIT)
def write_note(
    request: Request,
    response: Response,
    memo_id: MemoId,
    body: NoteCreate,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> NoteRead:
    memo = party_memo(db, request, memo_id, account)
    note = service.add(db, memo, account.role, body.body, now)
    response.headers["Location"] = f"/api/v1/deal-memos/{memo.id}/notes"
    return NoteRead.model_validate(note)
