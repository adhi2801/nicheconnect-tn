"""Writing and checking the deal record (D-057).

`append` adds one sealed entry **inside the caller's transaction**: it never
commits. The change and its entry are committed together or not at all, so
neither can exist without the other.

The fingerprint, version 1. Changing any of this breaks every existing
chain, so it is frozen; a change would be version 2, chosen per entry.

    entry_hash = SHA-256( b"deal-record/v1\\n" + previous_hash + canonical(body) )

    body = {deal_memo_id, sequence, kind, actor_role, actor_account_id,
            occurred_at, recorded_at, facts}

`canonical` is JSON with keys sorted, no spaces, UTF-8, whole numbers only
(a float is refused), and times in UTC to the microsecond ending in `Z`. For
those values it produces the same bytes as RFC 8785, the JSON
canonicalisation standard, so anyone can reproduce it without our code.
`docs/DEAL_RECORD_VERIFY.md` walks through it.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import GENESIS_HASH, DealRecordEntry

DOMAIN = b"deal-record/v1\n"

# What a memo's terms are, for the fingerprint that proves they have not
# changed. Everything the two sides agree to; nothing about its progress.
TERMS_FIELDS: tuple[str, ...] = (
    "deliverables",
    "fee_amount_paise",
    "currency",
    "cancellation_fee_paise",
    "approval_window_days",
    "payment_due_days",
    "usage_rights_days",
    "content_due_on",
    "disclosure_required",
    "extra_terms",
)


# --- the fingerprint --------------------------------------------------------


def timestamp(moment: datetime) -> str:
    """UTC to the microsecond, ending in Z: one spelling for every time."""
    if moment.tzinfo is None:
        raise ValueError("A time on the record must carry its time zone")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _check_canonical(value: Any) -> None:
    """Refuse anything whose JSON spelling is not fixed by our rules."""
    if isinstance(value, bool) or value is None or isinstance(value, str | int):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Keys on the record must be strings")
            _check_canonical(item)
        return
    if isinstance(value, list):
        for item in value:
            _check_canonical(item)
        return
    # Floats have more than one spelling; dates and times must be converted
    # by the caller, so there is exactly one way they appear.
    raise TypeError(f"{type(value).__name__} cannot go on the record")


def canonical(value: Any) -> bytes:
    _check_canonical(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def fingerprint(text: str) -> str:
    """SHA-256 of text a person typed, so the record proves it without holding it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def terms_fingerprint(memo: DealMemo) -> str:
    terms: dict[str, Any] = {}
    for field in TERMS_FIELDS:
        value = getattr(memo, field)
        terms[field] = value.isoformat() if isinstance(value, date) else value
    return hashlib.sha256(canonical(terms)).hexdigest()


def entry_body(entry: DealRecordEntry) -> dict[str, Any]:
    return {
        "deal_memo_id": str(entry.deal_memo_id),
        "sequence": entry.sequence,
        "kind": entry.kind,
        "actor_role": entry.actor_role,
        "actor_account_id": (
            str(entry.actor_account_id) if entry.actor_account_id else None
        ),
        "occurred_at": timestamp(entry.occurred_at),
        "recorded_at": timestamp(entry.recorded_at),
        "facts": entry.facts,
    }


def compute_hash(previous_hash: bytes, body: dict[str, Any]) -> bytes:
    return hashlib.sha256(DOMAIN + previous_hash + canonical(body)).digest()


# --- writing ----------------------------------------------------------------


def _party_account_ids(db: Session, memo: DealMemo) -> tuple[uuid.UUID, uuid.UUID]:
    """(brand account, creator account) for this deal, in one query."""
    row = db.execute(
        select(Brand.account_id, Creator.account_id)
        .select_from(Application)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .join(Creator, Creator.id == Application.creator_id)
        .where(Application.id == memo.application_id)
    ).one()
    return row[0], row[1]


def _last_entry(db: Session, memo_id: uuid.UUID) -> DealRecordEntry | None:
    return db.scalars(
        select(DealRecordEntry)
        .where(DealRecordEntry.deal_memo_id == memo_id)
        .order_by(DealRecordEntry.sequence.desc())
        .limit(1)
    ).first()


def _seal(
    db: Session,
    memo: DealMemo,
    previous: DealRecordEntry | None,
    *,
    kind: str,
    actor_role: str,
    actor_account_id: uuid.UUID | None,
    occurred_at: datetime,
    now: datetime,
    facts: dict[str, Any],
) -> DealRecordEntry:
    entry = DealRecordEntry(
        deal_memo_id=memo.id,
        sequence=1 if previous is None else previous.sequence + 1,
        kind=kind,
        actor_role=actor_role,
        actor_account_id=actor_account_id,
        occurred_at=occurred_at,
        recorded_at=now,
        facts=facts,
        previous_hash=GENESIS_HASH if previous is None else previous.entry_hash,
    )
    entry.entry_hash = compute_hash(entry.previous_hash, entry_body(entry))
    db.add(entry)
    db.flush()
    return entry


def append(
    db: Session,
    memo: DealMemo,
    *,
    kind: str,
    actor_role: str,
    now: datetime,
    facts: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> DealRecordEntry:
    """Seal one entry onto this deal's record, inside the caller's transaction.

    The deal's row is locked first, so two changes to one deal at the same
    moment append one after the other rather than both claiming the same
    place. The unique (deal, sequence) index backs that up.

    A deal whose history began before the record existed gets an opening
    `record_started` entry first, so no deal pretends its record reaches
    further back than it does.
    """
    db.execute(select(DealMemo.id).where(DealMemo.id == memo.id).with_for_update())
    brand_account, creator_account = _party_account_ids(db, memo)
    accounts = {"brand": brand_account, "creator": creator_account, "system": None}

    previous = _last_entry(db, memo.id)
    if previous is None and (kind != "memo_sent" or memo.revision_count > 0):
        previous = _seal(
            db,
            memo,
            None,
            kind="record_started",
            actor_role="system",
            actor_account_id=None,
            occurred_at=now,
            now=now,
            facts={"terms_sha256": terms_fingerprint(memo)},
        )

    return _seal(
        db,
        memo,
        previous,
        kind=kind,
        actor_role=actor_role,
        actor_account_id=accounts[actor_role],
        occurred_at=occurred_at or now,
        now=now,
        facts=facts or {},
    )


# --- reading and checking ---------------------------------------------------


def entries_for(db: Session, memo_id: uuid.UUID) -> list[DealRecordEntry]:
    return list(
        db.scalars(
            select(DealRecordEntry)
            .where(DealRecordEntry.deal_memo_id == memo_id)
            .order_by(DealRecordEntry.sequence)
        ).all()
    )


@dataclass(frozen=True)
class Verification:
    intact: bool
    # The first entry that does not match, when one does not.
    first_broken_sequence: int | None
    # None until the memo has been accepted; then whether the terms today
    # are the terms that were accepted.
    terms_unchanged_since_accepted: bool | None


def verify(memo: DealMemo, entries: list[DealRecordEntry]) -> Verification:
    """Recompute every fingerprint from the first entry on."""
    previous_hash = GENESIS_HASH
    accepted_terms: str | None = None
    for expected_sequence, entry in enumerate(entries, start=1):
        if (
            entry.deal_memo_id != memo.id
            or entry.sequence != expected_sequence
            or entry.previous_hash != previous_hash
            or compute_hash(previous_hash, entry_body(entry)) != entry.entry_hash
        ):
            return Verification(False, entry.sequence, None)
        if entry.kind == "memo_accepted":
            accepted_terms = entry.facts.get("terms_sha256")
        previous_hash = entry.entry_hash

    terms_ok = (
        None if accepted_terms is None else accepted_terms == terms_fingerprint(memo)
    )
    return Verification(True, None, terms_ok)
