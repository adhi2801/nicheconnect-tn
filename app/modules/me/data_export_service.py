"""The data export: asked for, built in the background, handed over once (D-111).

Building the file reads every table an account appears in, so its cost
grows with the account's whole history: measured at 300 to 400 ms p95 for a
busy account, over the 300 ms a request may take, and only growing. As
GitHub and Google do, the person asks (`request`), a job builds the file
(`run_exports`) and tells them, and they download it once (`download`).

The privacy rules for the copy this leaves in storage:

- **Encrypted at rest** by the bucket's own KMS key, under a random key
  (`export_models.object_key`), in a prefix only this code reaches.
- **Handed over once**: the download reads it under the row's lock, destroys
  every version of it, and only then answers, so a second download, or two
  at once, find nothing to give.
- **Never kept long**: one not downloaded is destroyed EXPORT_KEPT_FOR
  (24 hours) after it was ready; the bucket's own rule removes anything left
  a day later still.
- **A code where the data leaves**: downloading needs a `download_export`
  code for that exact export (its id is the code's value), so a code tricked
  out of someone for one cannot release another. Asking needs none (D-112):
  it releases nothing, and the owner is told when the file is ready.
- **A failure retries**, up to MAX_BUILD_ATTEMPTS runs a minute apart, then
  is marked failed and the owner told (D-112).
- **Never cached**: the download is not replayed for a retried request, so
  no copy sits in the idempotency store (`export_router`).
"""

import json
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import delete, exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.storage import FileStore
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.models.account import Account
from app.modules.me import export_service
from app.modules.me.exceptions import (
    ExportAlreadyDownloaded,
    ExportAlreadyPreparing,
    ExportExpired,
    ExportFailed,
    ExportNotFound,
    ExportNotReady,
)
from app.modules.me.export_models import (
    EXPORT_KEPT_FOR,
    MAX_BUILD_ATTEMPTS,
    DataExport,
    object_key,
)
from app.modules.notifications import service as notifications

logger = logging.getLogger(__name__)

# Far above any account's file today (a busy one is under 1 MB); a file
# above it fails rather than filling the process's memory.
MAX_EXPORT_BYTES = 50 * 1024 * 1024
# The read lists the newest few: a bound by rule (backend.md section 2).
RECENT_EXPORTS = 5
# Built in one run of the job; any more are built a minute later.
MAX_BUILDS_PER_RUN = 10

ExportStatus = Literal["preparing", "failed", "ready", "downloaded", "expired"]
BuildOutcome = Literal["built", "retrying", "failed", "settled"]


@dataclass(frozen=True)
class ExportRun:
    """What one run of the job did."""

    built: int
    # Failed this run, to be tried again next run (D-112).
    retrying: int
    # Failed its last try: marked failed and the owner told.
    failed: int
    expired: int


def status_of(export: DataExport, now: datetime) -> ExportStatus:
    """Where an export stands, worked out from its times."""
    if export.failed_at is not None:
        return "failed"
    if export.ready_at is None or export.expires_at is None:
        return "preparing"
    if export.downloaded_at is not None:
        return "downloaded"
    if now >= export.expires_at:
        return "expired"
    return "ready"


def request(db: Session, account: Account, now: datetime) -> DataExport:
    """Ask for a new export, built in the background. Commits.

    No code is asked for here (D-112): asking releases nothing, and tells
    the owner when the file is ready, so a stolen session asking is itself
    an alarm. The download, where the data leaves, needs a code for that
    exact export. Raises ExportAlreadyPreparing (one is being prepared: the
    database's partial unique index is the check).
    """
    export = DataExport(
        account_id=account.id, requested_at=now, created_at=now, updated_at=now
    )
    db.add(export)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ExportAlreadyPreparing() from None
    db.commit()
    return export


def get_own(db: Session, account: Account, export_id: uuid.UUID) -> DataExport:
    """One of the account's own exports. Raises ExportNotFound otherwise."""
    export = db.scalars(
        select(DataExport)
        .where(DataExport.id == export_id, DataExport.account_id == account.id)
        .execution_options(populate_existing=True)
    ).first()
    if export is None:
        raise ExportNotFound()
    return export


def recent(db: Session, account: Account) -> list[DataExport]:
    """The account's RECENT_EXPORTS newest exports."""
    return list(
        db.scalars(
            select(DataExport)
            .where(DataExport.account_id == account.id)
            .order_by(DataExport.requested_at.desc(), DataExport.id.desc())
            .limit(RECENT_EXPORTS)
        ).all()
    )


def ensure_downloadable(
    db: Session, account: Account, export_id: uuid.UUID, now: datetime
) -> None:
    """Refuse, before a code is sent for it, an export that cannot be downloaded.

    Raises ExportNotFound and what `_refuse_unless_ready` raises.
    """
    _refuse_unless_ready(get_own(db, account, export_id), now)


def download(
    db: Session,
    account: Account,
    store: FileStore,
    export_id: uuid.UUID,
    step_up_code: str | None,
    now: datetime,
) -> bytes:
    """The export's file, handed over once and destroyed. Commits.

    Spends a `download_export` code asked for with this export's id. The row
    is locked first, so two downloads at once give the file once. A refused
    download spends no code. Raises ExportNotFound, ExportNotReady,
    ExportFailed, ExportAlreadyDownloaded, ExportExpired, and what
    step_up_service.consume raises.
    """
    get_own(db, account, export_id)
    step_ups.consume(db, account, "download_export", str(export_id), step_up_code, now)
    export = db.scalars(
        select(DataExport)
        .where(DataExport.id == export_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    try:
        _refuse_unless_ready(export, now)
    except Exception:
        db.rollback()
        raise
    data = store.read(object_key(export_id), max_bytes=MAX_EXPORT_BYTES)
    store.destroy(object_key(export_id))
    export.downloaded_at = now
    export.file_deleted_at = now
    export.updated_at = now
    notifications.record(
        db, account_id=account.id, notification_type="data_exported", now=now
    )
    db.commit()
    return data


def run_exports(
    session_factory: Callable[[], AbstractContextManager[Session]],
    store: FileStore,
    now: datetime,
) -> ExportRun:
    """One run of the job: build what was asked for, destroy what expired.

    Each export in its own transaction. A file is written to storage with no
    transaction open, then marked ready only if it still waits, so even an
    overlapping run cannot mark one twice.
    """
    with session_factory() as db:
        waiting = list(
            db.scalars(
                select(DataExport.id)
                .where(DataExport.ready_at.is_(None), DataExport.failed_at.is_(None))
                .order_by(DataExport.requested_at, DataExport.id)
                .limit(MAX_BUILDS_PER_RUN)
            ).all()
        )
    outcomes = [_build(session_factory, store, export_id, now) for export_id in waiting]
    expired = _destroy_expired(session_factory, store, now)
    run = ExportRun(
        built=outcomes.count("built"),
        retrying=outcomes.count("retrying"),
        failed=outcomes.count("failed"),
        expired=expired,
    )
    logger.info(
        "data_export.run built=%d retrying=%d failed=%d expired=%d",
        run.built,
        run.retrying,
        run.failed,
        run.expired,
    )
    return run


def _build(
    session_factory: Callable[[], AbstractContextManager[Session]],
    store: FileStore,
    export_id: uuid.UUID,
    now: datetime,
) -> BuildOutcome:
    """Build one export's file and mark it ready, or count a failed try."""
    try:
        with session_factory() as db:
            export = db.get_one(DataExport, export_id)
            account = db.get_one(Account, export.account_id)
            data = json.dumps(
                export_service.build_export(db, account, now), ensure_ascii=False
            ).encode("utf-8")
            db.commit()
        if len(data) > MAX_EXPORT_BYTES:
            raise ValueError("export larger than MAX_EXPORT_BYTES")
        store.write(object_key(export_id), data, content_type="application/json")
    except Exception as error:
        # Its type only: a message could carry personal data (backend.md 9).
        logger.error(
            "data_export.build_failed export_id=%s error_type=%s",
            export_id,
            type(error).__name__,
        )
        return _count_failed_try(session_factory, export_id, now)

    expires_at = now + EXPORT_KEPT_FOR
    with session_factory() as db:
        marked = db.execute(
            update(DataExport)
            .where(
                DataExport.id == export_id,
                DataExport.ready_at.is_(None),
                DataExport.failed_at.is_(None),
            )
            .values(
                ready_at=now, expires_at=expires_at, size_bytes=len(data), updated_at=now
            )
            .returning(DataExport.account_id)
        ).scalar_one_or_none()
        if marked is not None:
            notifications.record(
                db,
                account_id=marked,
                notification_type="data_export_ready",
                now=now,
                details={
                    "export_id": str(export_id),
                    "expires_at": expires_at.isoformat(),
                },
            )
        db.commit()
    return "built"


def _count_failed_try(
    session_factory: Callable[[], AbstractContextManager[Session]],
    export_id: uuid.UUID,
    now: datetime,
) -> BuildOutcome:
    """One more failed try; on the last, mark it failed and tell the owner (D-112).

    Counted only while it still waits, so an overlapping run never counts a
    try twice past the last.
    """
    with session_factory() as db:
        tried = db.execute(
            update(DataExport)
            .where(
                DataExport.id == export_id,
                DataExport.ready_at.is_(None),
                DataExport.failed_at.is_(None),
                DataExport.attempts < MAX_BUILD_ATTEMPTS,
            )
            .values(attempts=DataExport.attempts + 1, updated_at=now)
            .returning(DataExport.attempts, DataExport.account_id)
        ).first()
        if tried is None:
            # Made ready, or failed, by an overlapping run meanwhile.
            db.commit()
            return "settled"
        attempts, account_id = tried
        if attempts < MAX_BUILD_ATTEMPTS:
            db.commit()
            return "retrying"
        db.execute(
            update(DataExport)
            .where(DataExport.id == export_id)
            .values(failed_at=now, updated_at=now)
        )
        notifications.record(
            db,
            account_id=account_id,
            notification_type="data_export_failed",
            now=now,
            details={"export_id": str(export_id)},
        )
        db.commit()
    logger.error("data_export.failed export_id=%s", export_id)
    return "failed"


def _destroy_expired(
    session_factory: Callable[[], AbstractContextManager[Session]],
    store: FileStore,
    now: datetime,
) -> int:
    """Destroy every file whose 24 hours passed undownloaded."""
    with session_factory() as db:
        due = list(
            db.scalars(
                select(DataExport.id).where(
                    DataExport.expires_at <= now,
                    DataExport.downloaded_at.is_(None),
                    DataExport.file_deleted_at.is_(None),
                )
            ).all()
        )
    for export_id in due:
        store.destroy(object_key(export_id))
        with session_factory() as db:
            db.execute(
                update(DataExport)
                .where(DataExport.id == export_id, DataExport.file_deleted_at.is_(None))
                .values(file_deleted_at=now, updated_at=now)
            )
            db.commit()
    return len(due)


def destroy_files_of(
    session_factory: Callable[[], AbstractContextManager[Session]],
    store: FileStore,
    account_id: uuid.UUID,
    now: datetime,
) -> int:
    """On deleting the account (D-122): destroy every file of its still stored.

    With no transaction open while storage is called, as for expired files.
    Returns how many were destroyed.
    """
    with session_factory() as db:
        stored = list(
            db.scalars(
                select(DataExport.id).where(
                    DataExport.account_id == account_id,
                    DataExport.ready_at.is_not(None),
                    DataExport.file_deleted_at.is_(None),
                )
            ).all()
        )
    for export_id in stored:
        store.destroy(object_key(export_id))
        with session_factory() as db:
            db.execute(
                update(DataExport)
                .where(DataExport.id == export_id, DataExport.file_deleted_at.is_(None))
                .values(file_deleted_at=now, updated_at=now)
            )
            db.commit()
    return len(stored)


def blocks_erasure(db: Session, account_id: uuid.UUID) -> bool:
    """True while an export is being prepared, or a file of one is still stored.

    The erasure waits for both (D-122): one being prepared would write a
    file after its row was gone, and a stored one is destroyed first, by
    `destroy_files_of`, outside the erasure's transaction.
    """
    return bool(
        db.scalar(
            select(
                exists().where(
                    DataExport.account_id == account_id,
                    DataExport.file_deleted_at.is_(None),
                    DataExport.failed_at.is_(None),
                )
            )
        )
    )


def erase_for_account(db: Session, account_id: uuid.UUID) -> None:
    """On deleting the account (D-122): the record of its exports. Never commits."""
    db.execute(delete(DataExport).where(DataExport.account_id == account_id))


def _refuse_unless_ready(export: DataExport, now: datetime) -> None:
    status = status_of(export, now)
    if status == "preparing":
        raise ExportNotReady()
    if status == "failed":
        raise ExportFailed()
    if status == "downloaded":
        raise ExportAlreadyDownloaded()
    if status == "expired":
        raise ExportExpired()
