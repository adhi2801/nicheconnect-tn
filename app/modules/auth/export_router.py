"""Download everything we hold about you.

One endpoint, about the signed-in account and nothing else. There is no way
to ask for somebody else's data: the account comes from the access token, so
there is no identifier in the path or the body for anyone to tamper with.

Deletion is deliberately not here. It needs retention rules from the
validation pack, and CLAUDE.md constraint 6 says ask rather than invent.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth import export_service
from app.modules.auth.dependencies import CurrentAccount, get_now

# Deliberately far stricter than an ordinary read. Building an export touches
# every table an account appears in, and the result is the most sensitive
# response this API produces, so it is treated as a sensitive flow
# (security.md section 3).
EXPORT_LIMIT = "3 per hour"

router = APIRouter(prefix="/api/v1/me", tags=["privacy"])


@router.get(
    "/export",
    summary="Download my data",
    description=(
        "Everything we hold about the signed-in account, as one JSON file. "
        "Includes a manifest explaining each section and why we hold it, and "
        "a list of what is deliberately not included. Limited to 3 requests "
        "an hour."
    ),
    response_class=JSONResponse,
    responses={
        200: {
            "description": "The export file",
            "content": {"application/json": {}},
        },
        401: problem_doc("No access token, or it is invalid or expired"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(EXPORT_LIMIT)
def export_my_data(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> JSONResponse:
    """Build this account's export and return it as a download."""
    payload = export_service.build_export(db, account, now)
    filename = export_service.export_filename(now)
    return JSONResponse(
        payload,
        headers={
            # Offered as a file, so a browser saves it instead of rendering it.
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Never let a copy of someone's personal data sit in a shared cache.
            "Cache-Control": "no-store",
        },
    )
