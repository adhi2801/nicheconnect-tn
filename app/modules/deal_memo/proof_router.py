"""Proof endpoints: the creator shows the work, the brand reviews it (D-024, D-025)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.literals import ensure_same_values
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.deal_memo import proof_service
from app.modules.deal_memo.dependencies import (
    BrandMemo,
    CreatorMemo,
    visible_memo_for_account,
)
from app.modules.deal_memo.proof_models import (
    NOTE_MAX_LENGTH,
    PROOF_FORMATS,
    PROOF_STATUSES,
    URL_MAX_LENGTH,
)

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["proof"], route_class=IdempotentRoute
)

ProofFormat = Literal["post", "reel", "story", "video", "other"]
ProofStatus = Literal["submitted", "approved", "revision_requested"]

ensure_same_values("ProofFormat", ProofFormat, PROOF_FORMATS)
ensure_same_values("ProofStatus", ProofStatus, PROOF_STATUSES)

MemoId = Annotated[uuid.UUID, Path(description="The memo's id")]
ProofId = Annotated[uuid.UUID, Path(description="The proof submission's id")]

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type cannot use this endpoint"),
    404: problem_doc("No such memo, or it is not yours"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


class ProofCreate(BaseModel):
    """What the creator submits. The link is the evidence that lasts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content_url: Annotated[
        str,
        Field(
            pattern=r"^https://.+",
            max_length=URL_MAX_LENGTH,
            description="Public link to the live post",
            examples=["https://www.instagram.com/reel/abc123/"],
        ),
    ]
    format: ProofFormat
    note: Annotated[str | None, Field(max_length=NOTE_MAX_LENGTH)] = None
    disclosure_confirmed: bool = False


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: Annotated[
        str,
        Field(
            min_length=5,
            max_length=NOTE_MAX_LENGTH,
            examples=["The ad label is missing from the caption."],
        ),
    ]


class ProofRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_memo_id: uuid.UUID
    content_url: str
    format: ProofFormat
    note: str | None
    disclosure_confirmed: bool
    status: ProofStatus
    approved_at: datetime | None
    auto_approved: bool
    revision_note: str | None
    content_removed_on: datetime | None
    created_at: datetime
    updated_at: datetime


@router.post(
    "/{memo_id}/proof",
    status_code=status.HTTP_201_CREATED,
    response_model=ProofRead,
    summary="Submit proof of the work",
    description=(
        "The creator gives the public link to the live post. Submitting also "
        "marks that work has started, which decides how a later cancellation "
        "counts. One submission waits for review at a time."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("The memo is not accepted, or proof is already waiting"),
        422: problem_doc("A field is missing or invalid"),
    },
)
@rate_limit(WRITE_LIMIT)
def submit_proof(
    request: Request,
    response: Response,
    body: ProofCreate,
    memo: CreatorMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ProofRead:
    proof = proof_service.submit_proof(db, memo, body.model_dump(), now)
    response.headers["Location"] = f"/api/v1/deal-memos/{memo.id}/proof/{proof.id}"
    return ProofRead.model_validate(proof)


@router.get(
    "/{memo_id}/proof",
    response_model=list[ProofRead],
    summary="List proof for a memo",
    description=(
        "Both sides see the same submissions, newest first. A submission whose "
        "approval window has passed is settled as automatically approved when read."
    ),
    responses=_COMMON_ERRORS,
)
@rate_limit(READ_LIMIT)
def list_proof(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> list[ProofRead]:
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    return [
        ProofRead.model_validate(proof)
        for proof in proof_service.list_for_memo(db, memo, now)
    ]


@router.post(
    "/{memo_id}/proof/{proof_id}/approve",
    response_model=ProofRead,
    summary="Approve the proof",
    description=(
        "The brand accepts the work. Approval starts the payment clock: payment "
        "is due the agreed number of days after this moment (D-027)."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This proof has already been reviewed"),
    },
)
@rate_limit(WRITE_LIMIT)
def approve_proof(
    request: Request,
    proof_id: ProofId,
    memo: BrandMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ProofRead:
    proof = proof_service.get_for_memo(db, memo, proof_id, now)
    return ProofRead.model_validate(proof_service.approve_proof(db, memo, proof, now))


@router.post(
    "/{memo_id}/proof/{proof_id}/request-revision",
    response_model=ProofRead,
    summary="Ask the creator to fix the proof",
    description=(
        "Sends it back with a reason, so the creator can submit again. Only the "
        "first request restarts the approval window (D-025)."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This proof has already been reviewed"),
        422: problem_doc("The note is missing or too short"),
    },
)
@rate_limit(WRITE_LIMIT)
def request_revision(
    request: Request,
    body: RevisionRequest,
    proof_id: ProofId,
    memo: BrandMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ProofRead:
    proof = proof_service.get_for_memo(db, memo, proof_id, now)
    return ProofRead.model_validate(
        proof_service.request_revision(db, memo, proof, body.note, now)
    )
