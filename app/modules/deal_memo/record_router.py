"""The deal record over HTTP (D-057). The rules live in `record_service`."""

import base64
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount
from app.modules.deal_memo import anchor_service, record_service
from app.modules.deal_memo.dependencies import visible_memo_for_account
from app.modules.deal_memo.exceptions import CheckpointNotFound
from app.modules.deal_memo.schemas import (
    CheckpointTimestampRead,
    DealRecordEntryRead,
    DealRecordProofRead,
    DealRecordRead,
)

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


@router.get(
    "/{memo_id}/record/proof",
    response_model=DealRecordProofRead,
    summary="Proof that the deal's record existed on a given day",
    description=(
        "Ties this deal's latest seal as of a day's cut-off to that day's "
        "Merkle root (RFC 6962), and returns the RFC 3161 timestamps DigiCert "
        "and Sectigo signed over the root. With it, the record as it stood that "
        "day can be checked without trusting us. Without `date`, the newest "
        "checkpoint that covers the deal. 409 means the record no longer "
        "matches a stamped checkpoint. The brand and the creator of this deal "
        "only."
    ),
    responses={
        **_ERRORS,
        404: problem_doc("No such memo, not yours, or no checkpoint covers it yet"),
        409: problem_doc("The record no longer matches its stamped checkpoint"),
    },
)
@rate_limit(READ_LIMIT)
def read_deal_record_proof(
    request: Request,
    memo_id: Annotated[uuid.UUID, Path(description="The memo's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    day: Annotated[
        date | None,
        Query(
            alias="date", description="The checkpoint's date in Tamil Nadu, YYYY-MM-DD"
        ),
    ] = None,
) -> DealRecordProofRead:
    """Either party. Anyone else gets 404, so ids cannot be walked."""
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    checkpoint = (
        anchor_service.checkpoint_for(db, day)
        if day is not None
        else anchor_service.latest_checkpoint_with(db, memo.id)
    )
    if checkpoint is None:
        raise CheckpointNotFound()
    try:
        proof = anchor_service.proof_for(db, memo.id, checkpoint)
    except anchor_service.NotInCheckpoint:
        raise CheckpointNotFound() from None
    return DealRecordProofRead(
        deal_memo_id=memo.id,
        checkpoint_date=india_date(checkpoint.covers_until),
        covers_until=record_service.timestamp(checkpoint.covers_until),
        leaf_count=checkpoint.leaf_count,
        leaf_index=proof.leaf_index,
        seal=proof.seal.hex(),
        audit_path=[sibling.hex() for sibling in proof.audit_path],
        merkle_root=checkpoint.merkle_root.hex(),
        stamped=bool(proof.timestamps),
        timestamps=[
            CheckpointTimestampRead(
                authority=t.authority,
                signed_at=t.signed_at,
                token_base64=base64.b64encode(t.token).decode("ascii"),
            )
            for t in proof.timestamps
        ],
    )
