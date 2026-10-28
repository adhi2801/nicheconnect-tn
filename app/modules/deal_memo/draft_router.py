"""Drafts shown before posting (HTTP; item 27, D-140). The rules: draft_service."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, computed_field
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.links import ContentLink
from app.core.literals import ensure_same_values
from app.core.rate_limit import rate_limit
from app.core.text_flags import FieldFlag, field_flags
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.deal_memo import draft_service as service
from app.modules.deal_memo.dependencies import (
    BrandMemo,
    CreatorMemo,
    visible_memo_for_account,
)
from app.modules.deal_memo.draft_models import (
    BODY_MAX_LENGTH,
    DRAFT_STATUSES,
    NOTE_MAX_LENGTH,
    URL_MAX_LENGTH,
    ContentDraft,
)
from app.modules.deal_memo.draft_rules import answer_last_day
from app.modules.deal_memo.models import DealMemo

READ_LIMIT = "60 per minute"
# Each draft and each answer reaches the other side, so each has a daily
# ceiling per account (trust-and-safety.md rule 2).
WRITE_LIMIT = "30 per minute;200 per day"

router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["drafts"], route_class=IdempotentRoute
)

DraftStatus = Literal["submitted", "approved", "changes_requested"]
ensure_same_values("DraftStatus", DraftStatus, DRAFT_STATUSES)
DraftId = Annotated[uuid.UUID, Path(description="The draft's id")]
MemoId = Annotated[uuid.UUID, Path(description="The memo's id")]

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type cannot use this endpoint"),
    404: problem_doc("No such memo or draft, or it is not yours"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


class DraftCreate(BaseModel):
    """What the creator shows the brand before posting."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(
        min_length=1,
        max_length=BODY_MAX_LENGTH,
        description="The caption or the script, as it will be posted",
        examples=["Pongal at home, the Madurai way. Our new sweet box, ad. #pongal"],
    )
    content_url: Annotated[
        ContentLink | None,
        Field(
            pattern=r"^https://.+",
            max_length=URL_MAX_LENGTH,
            description="A link to the draft itself, such as a video to watch",
        ),
    ] = None
    note: Annotated[str | None, Field(max_length=NOTE_MAX_LENGTH)] = None


class ChangesRequest(BaseModel):
    """What the brand wants changed, so the creator can show a new draft."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: Annotated[
        str,
        Field(
            min_length=5,
            max_length=NOTE_MAX_LENGTH,
            examples=["Please say the box is for 6 people, and add the ad label."],
        ),
    ]


class DraftRead(BaseModel):
    """A draft, as both sides see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_memo_id: uuid.UUID
    round: int = Field(description="Which attempt this is, from 1")
    body: str
    content_url: str | None
    note: str | None
    status: DraftStatus
    changes_note: str | None = Field(description="What the brand asked to change")
    approved_at: datetime | None
    answered_at: datetime | None = Field(
        description="When the brand answered, or the clock did; null while it waits"
    )
    auto_approved: bool = Field(
        description="Approved because the brand did not answer in time (D-025)"
    )
    answer_by: date | None = Field(
        default=None,
        description=(
            "While it waits: the last day the brand has to answer, in Tamil "
            "Nadu; after it, the draft approves itself. Null once answered, "
            "and once the deal has ended"
        ),
    )
    created_at: datetime
    updated_at: datetime

    @computed_field(  # type: ignore[prop-decorator]  # pydantic documents this
        description=(
            "Warnings on the brand's note, worked out on every read: a request "
            "for money (item 60). Show each beside its field; never hide the text"
        )
    )
    @property
    def text_flags(self) -> list[FieldFlag]:
        return field_flags({"changes_note": self.changes_note}, money=True, contact=False)


def _read(memo: DealMemo, draft: ContentDraft, history: list[ContentDraft]) -> DraftRead:
    waiting = draft.status == "submitted" and memo.status == "accepted"
    answer_by = answer_last_day(memo, draft, history) if waiting else None
    return DraftRead.model_validate(draft).model_copy(update={"answer_by": answer_by})


@router.post(
    "/{memo_id}/drafts",
    status_code=status.HTTP_201_CREATED,
    response_model=DraftRead,
    summary="Show the brand a draft before posting",
    description=(
        "Only on a memo whose agreed terms include `draft_review`. The brand "
        "has the memo's approval window to approve it or ask for changes; if "
        "it does not answer, the draft approves itself (D-025), never sooner "
        "than 2 whole days after it is shown. Every calendar day the brand holds "
        "it, the day it answers included, is added to the date the work is due "
        "(`work_due_on` on the deal). Proof can be "
        "submitted once a draft is approved. One draft waits at a time; each "
        "is sealed onto the deal record by its fingerprints. Showing a draft "
        "counts as work started. Limits: 30 a minute, 200 a day."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "The memo is not accepted; `draft_review_not_agreed`: its terms have "
            "no draft review; or `draft_already_decided`: a draft waits or is "
            "already approved"
        ),
        422: problem_doc("The draft is empty, too long, or its link is not usable"),
    },
)
@rate_limit(WRITE_LIMIT)
def submit_draft(
    request: Request,
    response: Response,
    body: DraftCreate,
    memo: CreatorMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DraftRead:
    draft = service.submit_draft(db, memo, body.model_dump(), now)
    response.headers["Location"] = f"/api/v1/deal-memos/{memo.id}/drafts/{draft.id}"
    return _read(memo, draft, service.drafts_of(db, memo))


@router.get(
    "/{memo_id}/drafts",
    response_model=list[DraftRead],
    summary="The drafts shown on a deal",
    description=(
        "Both sides see the same drafts, newest first. A draft whose window "
        "has passed is settled as approved by the clock when read. Every draft "
        "gives the brand at least 2 whole days, however late it is shown. "
        "Limit: 60 requests per minute."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def list_drafts(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> list[DraftRead]:
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    drafts = service.list_for_memo(db, memo, now)
    return [_read(memo, draft, drafts) for draft in drafts]


@router.post(
    "/{memo_id}/drafts/{draft_id}/approve",
    response_model=DraftRead,
    summary="Approve the draft",
    description=(
        "The brand approves what will be posted, and the creator may post and "
        "submit proof. Limits: 30 a minute, 200 a day."
    ),
    responses={**_COMMON, 409: problem_doc("This draft has already been answered")},
)
@rate_limit(WRITE_LIMIT)
def approve_draft(
    request: Request,
    draft_id: DraftId,
    memo: BrandMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DraftRead:
    draft = service.get_for_memo(db, memo, draft_id, now)
    approved = service.approve_draft(db, memo, draft, now)
    return _read(memo, approved, service.drafts_of(db, memo))


@router.post(
    "/{memo_id}/drafts/{draft_id}/request-changes",
    response_model=DraftRead,
    summary="Ask for changes to the draft",
    description=(
        "Sends it back with a reason, so the creator can show a new draft. "
        "Only the first request restarts the approval window (D-025). Limits: "
        "30 a minute, 200 a day."
    ),
    responses={
        **_COMMON,
        409: problem_doc("This draft has already been answered"),
        422: problem_doc("The note is missing or too short"),
    },
)
@rate_limit(WRITE_LIMIT)
def request_changes(
    request: Request,
    body: ChangesRequest,
    draft_id: DraftId,
    memo: BrandMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DraftRead:
    draft = service.get_for_memo(db, memo, draft_id, now)
    changed = service.request_changes(db, memo, draft, body.note, now)
    return _read(memo, changed, service.drafts_of(db, memo))
