"""Proof files: asking to upload, attaching, and opening them (D-065).

The order matters and is enforced, not hoped for:

1. `request_upload` checks the deal and the limits, saves a `pending` row and
   hands back a signed form. The form, not this code, is what stops a
   different file reaching S3: it pins the exact size, type and fingerprint.
2. The phone uploads straight to S3. We are not involved.
3. `attach` runs inside a proof submission. Each file must be this
   creator's, on this deal, still pending, and present in storage at the
   declared size. Only then does it join the proof, and its fingerprint is
   sealed into the deal record with it.

Cleaning (removing location and hidden data) happens afterwards, in a job;
nothing here reads the bytes.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.storage import FileStore, UploadForm
from app.modules.deal_memo.exceptions import (
    MemoStatusConflict,
    ProofFileNotFound,
    ProofFileNotUploaded,
    TooManyPendingUploads,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof, ProofFile

# Long enough for a slow mobile connection to send 10 MB, short enough that a
# leaked form is useless soon after.
UPLOAD_FORM_LIFETIME = timedelta(minutes=10)
# Unfinished uploads one deal may hold at once: a proof takes at most 10
# files, so 20 leaves room for retries without letting anyone fill a bucket.
MAX_PENDING_UPLOADS_PER_MEMO = 20
# Long enough to open a proof and look at it; a link copied out of a page or
# a log is useless soon after (D-065). Asking again gives fresh links.
VIEW_LINK_LIFETIME = timedelta(minutes=5)
INCOMING_PREFIX = "proof-files/incoming"


@dataclass(frozen=True)
class RequestedUpload:
    file: ProofFile
    form: UploadForm


def request_upload(
    db: Session,
    store: FileStore,
    memo: DealMemo,
    uploader_account_id: uuid.UUID,
    *,
    content_type: str,
    size_bytes: int,
    sha256: str,
    now: datetime,
) -> RequestedUpload:
    """A pending file and the signed form to upload it with."""
    if memo.status != "accepted":
        raise MemoStatusConflict("Files can only be uploaded for an accepted memo.")
    pending = db.scalar(
        select(func.count(ProofFile.id)).where(
            ProofFile.deal_memo_id == memo.id, ProofFile.status == "pending"
        )
    )
    if (pending or 0) >= MAX_PENDING_UPLOADS_PER_MEMO:
        raise TooManyPendingUploads()

    # A random key, not the row's id: the key is visible in the form, and
    # nothing about it should be guessable from another one.
    file = ProofFile(
        deal_memo_id=memo.id,
        uploader_account_id=uploader_account_id,
        storage_key=f"{INCOMING_PREFIX}/{uuid.uuid4().hex}",
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        created_at=now,
        updated_at=now,
    )
    db.add(file)
    db.flush()
    form = store.upload_form(
        file.storage_key,
        content_type=content_type,
        size=size_bytes,
        sha256_hex=sha256,
        expires_in=UPLOAD_FORM_LIFETIME,
        now=now,
    )
    db.commit()
    db.refresh(file)
    return RequestedUpload(file=file, form=form)


def attach(
    db: Session,
    store: FileStore,
    memo: DealMemo,
    proof: DeliverableProof,
    file_ids: list[uuid.UUID],
    uploader_account_id: uuid.UUID,
    now: datetime,
) -> list[ProofFile]:
    """Join these uploads to the proof, in the order given. Does not commit.

    The rows are locked first, so two submissions racing for the same file
    cannot both take it.
    """
    if not file_ids:
        return []
    found = {
        file.id: file
        for file in db.scalars(
            select(ProofFile)
            .where(
                ProofFile.id.in_(file_ids),
                ProofFile.deal_memo_id == memo.id,
                ProofFile.uploader_account_id == uploader_account_id,
                ProofFile.status == "pending",
            )
            .with_for_update()
        ).all()
    }
    files = []
    for file_id in file_ids:
        file = found.get(file_id)
        if file is None:
            raise ProofFileNotFound()
        stored = store.describe(file.storage_key)
        # S3 enforced the size on upload; checking again costs one request
        # and means nothing rests on that check alone.
        if stored is None or stored.size != file.size_bytes:
            raise ProofFileNotUploaded()
        file.status = "attached"
        file.proof_id = proof.id
        file.attached_at = now
        file.updated_at = now
        files.append(file)
    return files


@dataclass(frozen=True)
class FileView:
    """A file on a proof, with a link to open it when there is one to open."""

    file: ProofFile
    url: str | None
    expires_at: datetime | None


def has_viewable(files: list[ProofFile]) -> bool:
    """Whether any file is cleaned, so opening it needs the store at all."""
    return any(file.status == "cleaned" for file in files)


def view_links(
    store: FileStore | None, files: list[ProofFile], now: datetime
) -> list[FileView]:
    """A short-lived link for each cleaned file; none for anything else.

    Only the clean copy is ever linked, for the creator too: the original,
    location and all, is never served, and is deleted once cleaned. Signing
    happens here, on our side, with no request to storage.
    """
    views = []
    for file in files:
        if file.status != "cleaned" or file.clean_key is None or store is None:
            views.append(FileView(file=file, url=None, expires_at=None))
            continue
        url = store.view_url(
            file.clean_key,
            expires_in=VIEW_LINK_LIFETIME,
            filename=file.clean_key.rsplit("/", 1)[-1],
        )
        views.append(FileView(file=file, url=url, expires_at=now + VIEW_LINK_LIFETIME))
    return views


def record_facts(files: list[ProofFile]) -> list[dict[str, object]]:
    """What the deal record seals about each attached file."""
    return [
        {
            "file_id": str(file.id),
            "sha256": file.sha256,
            "size_bytes": file.size_bytes,
            "content_type": file.content_type,
        }
        for file in files
    ]
