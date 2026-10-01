"""Proof endpoints: the creator shows the work, the brand reviews it (D-024, D-025)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.literals import ensure_same_values
from app.core.rate_limit import per_account, rate_limit
from app.core.storage import FileStore, get_file_store
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.campaigns.dependencies import CurrentCreatorProfile
from app.modules.deal_memo import proof_file_service, proof_service
from app.modules.deal_memo.dependencies import (
    BrandMemo,
    CreatorMemo,
    visible_memo_for_account,
)
from app.modules.deal_memo.proof_models import (
    MAX_FILES_PER_PROOF,
    MAX_PROOF_FILE_BYTES,
    NOTE_MAX_LENGTH,
    PROOF_FILE_REJECTIONS,
    PROOF_FILE_STATUSES,
    PROOF_FILE_TYPES,
    PROOF_FORMATS,
    PROOF_STATUSES,
    URL_MAX_LENGTH,
)

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"
# Per person, not per address (D-065): a proof takes at most 10 files, so 30
# an hour covers three full attempts and stops anyone filling the bucket.
UPLOAD_LIMIT = "30 per hour"

router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["proof"], route_class=IdempotentRoute
)

ProofFormat = Literal["post", "reel", "story", "video", "other"]
ProofStatus = Literal["submitted", "approved", "revision_requested"]

ensure_same_values("ProofFormat", ProofFormat, PROOF_FORMATS)
ensure_same_values("ProofStatus", ProofStatus, PROOF_STATUSES)
ProofFileType = Literal["image/jpeg", "image/png", "image/webp"]
ProofFileStatus = Literal["pending", "attached", "cleaned", "rejected"]
ensure_same_values("ProofFileType", ProofFileType, PROOF_FILE_TYPES)
ensure_same_values("ProofFileStatus", ProofFileStatus, PROOF_FILE_STATUSES)
ProofFileRejection = Literal[
    "fingerprint_mismatch", "not_an_image", "too_many_pixels", "missing"
]
ensure_same_values("ProofFileRejection", ProofFileRejection, PROOF_FILE_REJECTIONS)

MemoId = Annotated[uuid.UUID, Path(description="The memo's id")]
ProofId = Annotated[uuid.UUID, Path(description="The proof submission's id")]

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type cannot use this endpoint"),
    404: problem_doc("No such memo, or it is not yours"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


class ProofCreate(BaseModel):
    """What the creator submits: a link, files, or both (D-065).

    A link proves the post is live; files survive it being deleted and show
    reach and insights, which have no link.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content_url: Annotated[
        str | None,
        Field(
            pattern=r"^https://.+",
            max_length=URL_MAX_LENGTH,
            description="Public link to the live post",
            examples=["https://www.instagram.com/reel/abc123/"],
        ),
    ] = None
    file_ids: Annotated[
        list[uuid.UUID],
        Field(
            max_length=MAX_FILES_PER_PROOF,
            description=(
                f"Up to {MAX_FILES_PER_PROOF} finished uploads from "
                "`POST /deal-memos/{memo_id}/proof/uploads`, in the order to show them"
            ),
        ),
    ] = []
    format: ProofFormat
    note: Annotated[str | None, Field(max_length=NOTE_MAX_LENGTH)] = None
    disclosure_confirmed: bool = False

    @model_validator(mode="after")
    def some_evidence(self) -> "ProofCreate":
        if not self.content_url and not self.file_ids:
            raise ValueError("give content_url, file_ids, or both")
        if len(set(self.file_ids)) != len(self.file_ids):
            raise ValueError("each file may appear once")
        return self


class ProofUploadCreate(BaseModel):
    """The file the creator is about to upload, described before it is sent."""

    model_config = ConfigDict(extra="forbid")

    content_type: ProofFileType
    size_bytes: Annotated[
        int,
        Field(ge=1, le=MAX_PROOF_FILE_BYTES, description="Exact size, in bytes"),
    ]
    sha256: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{64}$",
            description="SHA-256 of the file, lowercase hex. Storage refuses any other file",
            examples=["9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"],
        ),
    ]


class ProofUploadRead(BaseModel):
    """Where and how to upload: POST every one of `fields`, then the file, to `url`."""

    upload_id: uuid.UUID = Field(description="Give this in `file_ids` when submitting")
    url: str
    fields: dict[str, str] = Field(
        description="Send each as a form field, unchanged, before the file itself"
    )
    expires_at: datetime


class ProofFileSummary(BaseModel):
    """A file on a proof. `cleaned` is the only state a brand can open."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_type: ProofFileType
    size_bytes: int
    status: ProofFileStatus


class ProofFileView(BaseModel):
    """A file on a proof, and a link to open it once it has been cleaned."""

    id: uuid.UUID
    content_type: ProofFileType
    size_bytes: int = Field(description="The size of what the link opens")
    status: ProofFileStatus
    rejection_reason: ProofFileRejection | None = Field(
        description="Why a rejected file cannot be shown"
    )
    url: str | None = Field(
        description=(
            "Opens the cleaned image. Only cleaned files have one. It works for "
            "a few minutes and must not be stored: ask again for a fresh one"
        )
    )
    url_expires_at: datetime | None


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
    content_url: str | None
    files: list[ProofFileSummary]
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
    "/{memo_id}/proof/uploads",
    status_code=status.HTTP_201_CREATED,
    response_model=ProofUploadRead,
    summary="Start uploading a proof file",
    description=(
        "Describe a screenshot or photo (type, exact size, SHA-256) and get a "
        "signed form to upload it **straight to storage**, valid for 10 "
        "minutes. Storage refuses any file that does not match the "
        "description. Then give `upload_id` in `file_ids` when submitting proof."
        "\n\nJPEG, PNG or WebP, up to 10 MB. Only the creator, only on an "
        "accepted memo, at most 20 unfinished uploads per memo, 30 an hour per "
        "account. Every image is cleaned of location and hidden data before a "
        "brand can see it."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("The memo is not accepted, or too many uploads are unfinished"),
        422: problem_doc("The type, size or fingerprint is invalid"),
        503: problem_doc("File uploads are not available right now"),
    },
)
@rate_limit(UPLOAD_LIMIT, key=per_account)
def start_proof_upload(
    request: Request,
    body: ProofUploadCreate,
    memo: CreatorMemo,
    creator: CurrentCreatorProfile,
    store: Annotated[FileStore, Depends(get_file_store)],
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ProofUploadRead:
    requested = proof_file_service.request_upload(
        db,
        store,
        memo,
        creator.account_id,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        sha256=body.sha256,
        now=now,
    )
    return ProofUploadRead(
        upload_id=requested.file.id,
        url=requested.form.url,
        fields=requested.form.fields,
        expires_at=requested.form.expires_at,
    )


@router.post(
    "/{memo_id}/proof",
    status_code=status.HTTP_201_CREATED,
    response_model=ProofRead,
    summary="Submit proof of the work",
    description=(
        "The creator gives the public link to the live post, files uploaded "
        "through `POST .../proof/uploads`, or both. Each file's fingerprint is "
        "sealed into the deal record with the proof. Submitting also marks "
        "that work has started, which decides how a later cancellation counts. "
        "One submission waits for review at a time."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc(
            "The memo is not accepted, proof is already waiting, or a file has "
            "not finished uploading"
        ),
        422: problem_doc(
            "A field is missing or invalid, there is neither a link nor a file, "
            "or a file is not one of your uploads for this deal"
        ),
        503: problem_doc("File uploads are not available right now"),
    },
)
@rate_limit(WRITE_LIMIT)
def submit_proof(
    request: Request,
    response: Response,
    body: ProofCreate,
    memo: CreatorMemo,
    creator: CurrentCreatorProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ProofRead:
    fields = body.model_dump(exclude={"file_ids"})
    if body.file_ids:
        # The store is asked for only when there are files, so a link-only
        # proof still works on a server whose uploads are unavailable.
        proof = proof_service.submit_proof(
            db,
            memo,
            fields,
            now,
            store=get_file_store(),
            file_ids=body.file_ids,
            uploader_account_id=creator.account_id,
        )
    else:
        proof = proof_service.submit_proof(db, memo, fields, now)
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


@router.get(
    "/{memo_id}/proof/{proof_id}/files",
    response_model=list[ProofFileView],
    summary="Open the files on a proof",
    description=(
        "Every file on the proof, in upload order, each cleaned one with a link "
        "to open it, valid for 5 minutes. Only the brand and the creator on the "
        "deal can ask. A file still being cleaned has no link yet; it is usually "
        "ready within a minute. Only the cleaned copy is ever shown, to either "
        "side: the original, with its location data, is never served."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such memo or proof, or it is not yours"),
        503: problem_doc("File uploads are not available right now"),
    },
)
@rate_limit(READ_LIMIT, key=per_account)
def view_proof_files(
    request: Request,
    response: Response,
    memo_id: MemoId,
    proof_id: ProofId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> list[ProofFileView]:
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    proof = proof_service.get_for_memo(db, memo, proof_id, now)
    files = list(proof.files)
    # Asked for only when something can be opened, as when submitting.
    store = get_file_store() if proof_file_service.has_viewable(files) else None
    # Each link opens a private file on its own: never kept by a browser
    # or a proxy.
    response.headers["Cache-Control"] = "no-store"
    return [
        ProofFileView.model_validate(
            {
                "id": view.file.id,
                "content_type": view.file.content_type,
                "size_bytes": view.file.clean_size_bytes or view.file.size_bytes,
                "status": view.file.status,
                "rejection_reason": view.file.rejection_reason,
                "url": view.url,
                "url_expires_at": view.expires_at,
            }
        )
        for view in proof_file_service.view_links(store, files, now)
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
