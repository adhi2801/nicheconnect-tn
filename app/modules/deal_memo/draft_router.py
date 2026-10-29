"""Drafts shown before posting (HTTP; item 27, D-140). The rules: draft_service."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.links import ContentLink
from app.core.literals import ensure_same_values
from app.core.rate_limit import per_account, rate_limit, shared_rate_limit
from app.core.storage import FileStore, get_file_store
from app.core.text_flags import FieldFlag, field_flags
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.campaigns.dependencies import CurrentCreatorProfile
from app.modules.deal_memo import draft_service as service
from app.modules.deal_memo import proof_file_service
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
from app.modules.deal_memo.proof_models import (
    MAX_FILES_PER_PROOF,
    MAX_PROOF_FILE_BYTES,
    PROOF_FILE_REJECTIONS,
    PROOF_FILE_STATUSES,
    PROOF_FILE_TYPES,
    ProofFile,
)
from app.modules.deal_memo.proof_router import UPLOAD_LIMIT, UPLOAD_SCOPE

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
DraftFileType = Literal["image/jpeg", "image/png", "image/webp"]
DraftFileStatus = Literal["pending", "attached", "cleaned", "rejected"]
DraftFileRejection = Literal[
    "fingerprint_mismatch", "not_an_image", "too_many_pixels", "missing"
]
ensure_same_values("DraftFileType", DraftFileType, PROOF_FILE_TYPES)
ensure_same_values("DraftFileStatus", DraftFileStatus, PROOF_FILE_STATUSES)
ensure_same_values("DraftFileRejection", DraftFileRejection, PROOF_FILE_REJECTIONS)
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
    file_ids: Annotated[
        list[uuid.UUID],
        Field(
            max_length=MAX_FILES_PER_PROOF,
            description=(
                f"Up to {MAX_FILES_PER_PROOF} finished image uploads from "
                "`POST /deal-memos/{memo_id}/drafts/uploads`, in the order to show "
                "them: stills of a Reel, carousel slides, a Story frame. A video "
                "goes in `content_url`"
            ),
        ),
    ] = []

    @model_validator(mode="after")
    def each_file_once(self) -> DraftCreate:
        if len(set(self.file_ids)) != len(self.file_ids):
            raise ValueError("each file may appear once")
        return self


class DraftUploadCreate(BaseModel):
    """The image the creator is about to upload for a draft, described first."""

    model_config = ConfigDict(extra="forbid")

    content_type: DraftFileType
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


class DraftUploadRead(BaseModel):
    """Where and how to upload: POST every one of `fields`, then the file, to `url`."""

    upload_id: uuid.UUID = Field(
        description="Give this in `file_ids` when showing the draft"
    )
    url: str
    fields: dict[str, str] = Field(
        description="Send each as a form field, unchanged, before the file itself"
    )
    expires_at: datetime


class DraftFileSummary(BaseModel):
    """An image on a draft. `cleaned` is the only state either side can open."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_type: DraftFileType
    size_bytes: int = Field(
        description="The cleaned copy's size once cleaned, the upload's before"
    )
    status: DraftFileStatus


class DraftFileView(BaseModel):
    """An image on a draft, and a link to open it once it has been cleaned."""

    id: uuid.UUID
    content_type: DraftFileType
    size_bytes: int = Field(description="The size of what the link opens")
    status: DraftFileStatus
    rejection_reason: DraftFileRejection | None = Field(
        description="Why a rejected image cannot be shown"
    )
    url: str | None = Field(
        description=(
            "Opens the cleaned image. Only cleaned images have one. It works for "
            "a few minutes and must not be stored: ask again for a fresh one"
        )
    )
    url_expires_at: datetime | None


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
    files: list[DraftFileSummary] = Field(
        default_factory=list,
        description="The images shown with the draft, in the creator's order",
    )
    answer_by: date | None = Field(
        default=None,
        description=(
            "While it waits: the last day the brand has to answer, in Tamil "
            "Nadu; after it, the draft approves itself. Null once answered, "
            "once the deal has ended, and while its images are being cleaned "
            "(the brand's time starts once it can open them)"
        ),
    )
    images_ready_at: datetime | None = Field(
        description=(
            "When every image was cleaned or refused, so the brand could open "
            "them; the moment it was shown for a draft without images. Null "
            "while any is still being cleaned, usually under a minute: until "
            "then it cannot be approved"
        )
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


def _read(
    memo: DealMemo,
    draft: ContentDraft,
    history: list[ContentDraft],
    files: list[ProofFile],
) -> DraftRead:
    waiting = draft.status == "submitted" and memo.status == "accepted"
    answer_by = answer_last_day(memo, draft, history) if waiting else None
    return DraftRead.model_validate(draft).model_copy(
        update={
            "answer_by": answer_by,
            "files": [
                DraftFileSummary(
                    id=file.id,
                    content_type=file.content_type,
                    size_bytes=file.clean_size_bytes or file.size_bytes,
                    status=file.status,
                )
                for file in files
            ],
        }
    )


def _read_one(db: Session, memo: DealMemo, draft: ContentDraft) -> DraftRead:
    files = service.files_by_draft(db, [draft])[draft.id]
    return _read(memo, draft, service.drafts_of(db, memo), files)


@router.post(
    "/{memo_id}/drafts/uploads",
    status_code=status.HTTP_201_CREATED,
    response_model=DraftUploadRead,
    summary="Start uploading an image for a draft",
    description=(
        "Describe an image (type, exact size, SHA-256) and get a signed form to "
        "upload it **straight to storage**, valid for 10 minutes. Storage refuses "
        "any file that does not match the description. Then give `upload_id` in "
        "`file_ids` when showing the draft."
        "\n\nJPEG, PNG or WebP, up to 10 MB. Only the creator, only on an "
        "accepted memo whose terms include draft review and whose draft is not "
        "yet approved; at most 20 unfinished uploads per memo and 30 an hour "
        "per account, both counted with proof uploads. A draft upload joins only "
        "a draft. Every image is cleaned of location and hidden data before "
        "anyone can open it. A video goes in `content_url`."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "`memo_status_conflict`: the memo is not accepted; "
            "`too_many_pending_uploads`: 20 uploads are unfinished; "
            "`draft_review_not_agreed`; or `draft_already_decided`: a draft is approved"
        ),
        422: problem_doc("The type, size or fingerprint is invalid"),
        503: problem_doc("File uploads are not available right now"),
    },
)
@shared_rate_limit(UPLOAD_LIMIT, scope=UPLOAD_SCOPE, key=per_account)
def start_draft_upload(
    request: Request,
    body: DraftUploadCreate,
    memo: CreatorMemo,
    creator: CurrentCreatorProfile,
    store: Annotated[FileStore, Depends(get_file_store)],
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DraftUploadRead:
    requested = service.request_upload(
        db,
        store,
        memo,
        creator.account_id,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        sha256=body.sha256,
        now=now,
    )
    return DraftUploadRead(
        upload_id=requested.file.id,
        url=requested.form.url,
        fields=requested.form.fields,
        expires_at=requested.form.expires_at,
    )


@router.post(
    "/{memo_id}/drafts",
    status_code=status.HTTP_201_CREATED,
    response_model=DraftRead,
    summary="Show the brand a draft before posting",
    description=(
        "Only on a memo whose agreed terms include `draft_review`. The brand "
        "has the memo's approval window to approve it or ask for changes; if "
        "it does not answer, the draft approves itself (D-025), never sooner "
        "than 2 whole days after it is shown. If it is shown by the date the work "
        "is due, every calendar day the brand holds it, the day it answers "
        "included, is added to that date once (`work_due_on` on the deal); a "
        "draft shown late moves nothing. Images uploaded through "
        "`POST .../drafts/uploads` go in `file_ids`, and their fingerprints are "
        "sealed with the draft. Proof can be "
        "submitted once a draft is approved. One draft waits at a time; each "
        "is sealed onto the deal record by its fingerprints. Showing a draft "
        "counts as work started. Limits: 30 a minute, 200 a day."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "The memo is not accepted; `draft_review_not_agreed`: its terms have "
            "no draft review; `draft_already_decided`: a draft waits or is "
            "already approved; or `proof_file_not_uploaded`: an image has not "
            "finished uploading"
        ),
        422: problem_doc(
            "The draft is empty, too long, or its link is not usable; or "
            "`proof_file_not_found`: an image is not one of your unused draft "
            "uploads for this deal (image errors keep proof's codes, as both "
            "share one upload pipeline)"
        ),
        503: problem_doc("File uploads are not available right now"),
    },
)
@rate_limit(WRITE_LIMIT)
def submit_draft(
    request: Request,
    response: Response,
    body: DraftCreate,
    memo: CreatorMemo,
    creator: CurrentCreatorProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DraftRead:
    fields = body.model_dump(exclude={"file_ids"})
    if body.file_ids:
        # The store is asked for only when there are images, so a draft
        # without any still works on a server whose uploads are unavailable.
        draft = service.submit_draft(
            db,
            memo,
            fields,
            now,
            store=get_file_store(),
            file_ids=body.file_ids,
            uploader_account_id=creator.account_id,
        )
    else:
        draft = service.submit_draft(db, memo, fields, now)
    response.headers["Location"] = f"/api/v1/deal-memos/{memo.id}/drafts/{draft.id}"
    return _read_one(db, memo, draft)


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
    files = service.files_by_draft(db, drafts)
    return [_read(memo, draft, drafts, files[draft.id]) for draft in drafts]


@router.get(
    "/{memo_id}/drafts/{draft_id}/files",
    response_model=list[DraftFileView],
    summary="Open the images on a draft",
    description=(
        "Every image on the draft, in the order the creator chose, each cleaned "
        "one with a link to open it, valid for 5 minutes. Only the brand and the "
        "creator on the deal can ask. An image still being cleaned has no link "
        "yet; it is usually ready within a minute. Only the cleaned copy is ever "
        "shown, to either side: the original, with its location data, is never "
        "served. Limit: 60 requests per minute."
    ),
    responses={**_COMMON, 503: problem_doc("File uploads are not available right now")},
)
@rate_limit(READ_LIMIT, key=per_account)
def view_draft_files(
    request: Request,
    response: Response,
    memo_id: MemoId,
    draft_id: DraftId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> list[DraftFileView]:
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    draft = service.get_for_memo(db, memo, draft_id, now)
    files = service.files_by_draft(db, [draft])[draft.id]
    # Asked for only when something can be opened.
    store = get_file_store() if proof_file_service.has_viewable(files) else None
    # Each link opens a private file on its own: never kept by a browser or a proxy.
    response.headers["Cache-Control"] = "no-store"
    return [
        DraftFileView.model_validate(
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
    "/{memo_id}/drafts/{draft_id}/approve",
    response_model=DraftRead,
    summary="Approve the draft",
    description=(
        "The brand approves what will be posted, and the creator may post and "
        "submit proof. Limits: 30 a minute, 200 a day."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "`draft_already_decided`: this draft has already been answered; or "
            "`draft_images_not_ready`: its images are still being cleaned, so "
            "the brand could not yet open them"
        ),
    },
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
    return _read_one(db, memo, approved)


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
    return _read_one(db, memo, changed)
