"""The deal record over HTTP (D-057). The rules live in `record_service`."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount
from app.modules.deal_memo import record_service
from app.modules.deal_memo.dependencies import visible_memo_for_account
from app.modules.deal_memo.schemas import DealRecordEntryRead, DealRecordRead

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/deal-memos", tags=["deal record"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    404: problem_doc("No such memo, or not yours"),
    422: problem_doc("The memo id is not a valid id"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/{memo_id}/record",
    response_model=DealRecordRead,
    summary="The deal's sealed record",
    description=(
        "Every step of this deal since it was first sent, each sealed with the "
        "SHA-256 of the one before, so a changed or missing entry shows. "
        "Typed text (terms, links, notes, payment references) appears only as "
        "a fingerprint. `intact` is our check; `docs/DEAL_RECORD_VERIFY.md` "
        "shows how to make your own, and keeping `latest_seal` lets you catch "
        "a rewrite later. The brand and the creator of this deal only."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_deal_record(
    request: Request,
    memo_id: Annotated[uuid.UUID, Path(description="The memo's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> DealRecordRead:
    """Either party. Anyone else gets 404, so ids cannot be walked."""
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    entries = record_service.entries_for(db, memo.id)
    check = record_service.verify(memo, entries)
    return DealRecordRead(
        deal_memo_id=memo.id,
        intact=check.intact,
        first_broken_sequence=check.first_broken_sequence,
        terms_unchanged_since_accepted=check.terms_unchanged_since_accepted,
        latest_seal=entries[-1].entry_hash.hex() if entries else None,
        entries=[
            DealRecordEntryRead(
                sequence=e.sequence,
                kind=e.kind,
                actor_role=e.actor_role,
                actor_account_sha256=record_service.actor_fingerprint(e.actor_account_id),
                occurred_at=record_service.timestamp(e.occurred_at),
                recorded_at=record_service.timestamp(e.recorded_at),
                facts=e.facts,
                previous_seal=e.previous_hash.hex(),
                seal=e.entry_hash.hex(),
            )
            for e in entries
        ],
    )
