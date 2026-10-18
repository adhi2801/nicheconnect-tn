"""Download everything we hold about you, built in the background (D-111).

Every route is about the signed-in account and its own exports: an export
of anyone else reads as not found. The rules and the privacy of the stored
copy: data_export_service.

Deletion is deliberately not here. It needs retention rules from the
validation pack, and CLAUDE.md constraint 6 says ask rather than invent.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.core.storage import FileStore, get_file_store
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, StepUpCode, get_now
from app.modules.me import data_export_service as service
from app.modules.me import export_service
from app.modules.me.data_export_schemas import DataExportList, DataExportRead
from app.modules.me.export_models import DataExport
from app.modules.me.schemas import ExportFile

# Far stricter than an ordinary write: each one builds a copy of every table
# the account appears in (security.md section 3).
EXPORT_LIMIT = "3 per hour"
DOWNLOAD_LIMIT = "10 per hour"
READ_LIMIT = "60 per minute"

# Asking is replayed for a retry with the same Idempotency-Key, like every
# other write.
router = APIRouter(prefix="/api/v1/me", tags=["privacy"], route_class=IdempotentRoute)
# The download is not: a replay would need the whole file kept in the
# idempotency store, the very copy D-111 refuses to keep. A retry after a
# lost answer asks for a new export instead.
download_router = APIRouter(prefix="/api/v1/me", tags=["privacy"])

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_CODE: ResponseDocs = {
    400: problem_doc("The code is wrong, expired, used, or for another change"),
    401: problem_doc(
        "No access token, or it is invalid or expired; or `step_up_required`: "
        "no code was sent"
    ),
    422: problem_doc("The code is not 6 digits"),
    429: problem_doc(
        "Too many requests, or too many wrong codes for your phone; see the "
        "Retry-After header"
    ),
}


def _read(export: DataExport, now: datetime) -> DataExportRead:
    return DataExportRead(
        id=export.id,
        status=service.status_of(export, now),
        requested_at=export.requested_at,
        ready_at=export.ready_at,
        expires_at=export.expires_at,
        size_bytes=export.size_bytes,
        downloaded_at=export.downloaded_at,
    )


@router.post(
    "/exports",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DataExportRead,
    summary="Ask for a copy of my data",
    description=(
        "Starts building one JSON file of everything we hold about the "
        "signed-in account, with a manifest saying why we hold each part and "
        "what is deliberately left out. **Needs a code**: ask at `POST "
        "/api/v1/me/step-up` with `download_export` and no `export_id`, and "
        "send it in the `Step-Up-Code` header. You are told in the app when "
        "it is ready, usually within minutes; then download it, once, within "
        "24 hours. One is prepared at a time. Limited to 3 an hour."
    ),
    responses={
        **_CODE,
        409: problem_doc("`export_already_preparing`: one is already being prepared"),
    },
)
@rate_limit(EXPORT_LIMIT)
def ask_for_my_data(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    step_up_code: StepUpCode = None,
) -> DataExportRead:
    return _read(service.request(db, account, step_up_code, now), now)


@router.get(
    "/exports",
    response_model=DataExportList,
    summary="My data exports",
    description="The 5 newest exports you asked for, newest first, and where each stands.",
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def list_my_exports(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DataExportList:
    return DataExportList(
        items=[_read(export, now) for export in service.recent(db, account)]
    )


@router.get(
    "/exports/{export_id}",
    response_model=DataExportRead,
    summary="One of my data exports",
    description="Where one export you asked for stands.",
    responses={**_COMMON, 404: problem_doc("No such export of yours")},
)
@rate_limit(READ_LIMIT)
def read_my_export(
    request: Request,
    export_id: uuid.UUID,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DataExportRead:
    return _read(service.get_own(db, account, export_id), now)


@download_router.post(
    "/exports/{export_id}/download",
    summary="Download a copy of my data, once",
    description=(
        "Returns the export's file, offered as a download, and destroys the "
        "stored copy: it can be downloaded once. **Needs a code for this "
        "export**: ask at `POST /api/v1/me/step-up` with `download_export` "
        "and this `export_id`. You are told in the app each time a file is "
        "downloaded. Not replayed for a retried request, so no copy is kept "
        "anywhere: if the download breaks, ask for a new export. Limited to "
        "10 an hour."
    ),
    response_class=Response,
    responses={
        200: {
            "model": ExportFile,
            "description": "The export file, offered as a download",
            "content": {"application/json": {}},
        },
        **_CODE,
        404: problem_doc("No such export of yours"),
        409: problem_doc(
            "`export_not_ready`, `export_failed`, `export_already_downloaded` "
            "or `export_expired`"
        ),
    },
)
@rate_limit(DOWNLOAD_LIMIT)
def download_my_data(
    request: Request,
    export_id: uuid.UUID,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    store: Annotated[FileStore, Depends(get_file_store)],
    step_up_code: StepUpCode = None,
) -> Response:
    data = service.download(db, account, store, export_id, step_up_code, now)
    return Response(
        content=data,
        media_type="application/json",
        headers={
            # Offered as a file, so a browser saves it instead of rendering it.
            "Content-Disposition": (
                f'attachment; filename="{export_service.export_filename(now)}"'
            ),
            # Never let a copy of someone's personal data sit in a shared cache.
            "Cache-Control": "no-store",
        },
    )
