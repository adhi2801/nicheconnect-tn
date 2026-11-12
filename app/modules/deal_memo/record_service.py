"""Writing and checking the deal record (D-057).

`append` adds one sealed entry **inside the caller's transaction**: it never
commits. The change and its entry are committed together or not at all, so
neither can exist without the other.

The fingerprint, version 1. Changing any of this breaks every existing
chain, so it is frozen; a change would be version 2, chosen per entry.

    entry_hash = SHA-256( b"deal-record/v1\\n" + previous_hash + canonical(body) )

    body = {deal_memo_id, sequence, kind, actor_role, actor_account_sha256,
            occurred_at, recorded_at, facts}

`actor_account_sha256` is the SHA-256 of the acting account's id, not the id
itself: each side can check the seals without being shown the other side's
account id, and can recognise their own entries by hashing their own id.
A UUID has 122 random bits, so the fingerprint cannot be worked backwards.

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

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.modules.auth import brand_access
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import BrandMember
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import GENESIS_HASH, DealRecordEntry
from app.modules.payment_status.models import PaymentStatus

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


# A deliverable's fields, as terms version 2 seals them (item 26, D-127).
DELIVERABLE_FIELDS: tuple[str, ...] = ("platform", "format", "quantity", "note")


def terms_fingerprint(memo: DealMemo) -> str:
    """The SHA-256 of the memo's terms, as its terms version defines them.

    Version 1 (every memo before 25 October 2026) is TERMS_FIELDS alone, and
    stays exactly that forever, so no seal made before then changes. Version
    2 adds the list of deliverables, in order (D-127). Version 3 adds
    `draft_review`, whether a draft is shown before posting (item 27, D-140).
    """
    terms: dict[str, Any] = {}
    for field in TERMS_FIELDS:
        value = getattr(memo, field)
        terms[field] = value.isoformat() if isinstance(value, date) else value
    if memo.terms_version is None:
        # Set when the memo is saved; a fingerprint of terms not yet on the
        # record would prove nothing.
        raise ValueError("A memo has no terms version until it is saved")
    if memo.terms_version >= 2:
        terms["deliverable_items"] = [
            {field: getattr(item, field) for field in DELIVERABLE_FIELDS}
            for item in memo.deliverable_items
        ]
    if memo.terms_version >= 3:
        terms["draft_review"] = memo.draft_review
    return hashlib.sha256(canonical(terms)).hexdigest()


def actor_fingerprint(account_id: uuid.UUID | None) -> str | None:
    """SHA-256 of the account id as text, or None for the system."""
    return fingerprint(str(account_id)) if account_id else None


def entry_body(entry: DealRecordEntry) -> dict[str, Any]:
    return {
        "deal_memo_id": str(entry.deal_memo_id),
        "sequence": entry.sequence,
        "kind": entry.kind,
        "actor_role": entry.actor_role,
        "actor_account_sha256": actor_fingerprint(entry.actor_account_id),
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


def _accounts(
    db: Session, brand_account: uuid.UUID, creator_account: uuid.UUID
) -> dict[str, uuid.UUID | None]:
    """The account each role's entry names. The brand side names who acted
    (D-148): a team member acting in this request, else the owner, as before
    teams (a job, or the owner's request)."""
    acting = brand_access.acting(db)
    return {
        "brand": acting.account_id if acting is not None else brand_account,
        "creator": creator_account,
        "system": None,
    }


def _needs_opening(previous: DealRecordEntry | None, kind: str, memo: DealMemo) -> bool:
    """Whether a `record_started` entry goes first: a deal whose history began
    before the record existed, so no deal pretends its record reaches further
    back than it does."""
    return previous is None and (kind != "memo_sent" or memo.revision_count > 0)


def _sealed(
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
    """One entry, chained to `previous` and fingerprinted; not yet added."""
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
    return entry


def _seal(
    db: Session, memo: DealMemo, previous: DealRecordEntry | None, **entry: Any
) -> DealRecordEntry:
    sealed = _sealed(memo, previous, **entry)
    db.add(sealed)
    db.flush()
    return sealed


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
    accounts = _accounts(db, *_party_account_ids(db, memo))

    previous = _last_entry(db, memo.id)
    if _needs_opening(previous, kind, memo):
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


def append_each(
    db: Session,
    facts_by_memo: dict[uuid.UUID, dict[str, Any]],
    *,
    kind: str,
    actor_role: str,
    now: datetime,
) -> None:
    """`append` on many deals at once: one entry of one kind on each, with its
    own facts, in five statements however many deals (audit C16, D-184):
    the deals locked, their deliverables, their parties, their last
    entries, and the entries written.

    Exactly `append`'s rules: each deal locked first, its parties and last
    entry read, a `record_started` entry first where the record has none.
    The deals are locked in one statement, in id order, so two callers
    sharing deals take their locks in the same order and neither can hold
    one the other waits for while waiting on one it holds (a deadlock).
    Never commits.
    """
    if not facts_by_memo:
        return
    memos = list(
        db.scalars(
            select(DealMemo)
            .where(DealMemo.id.in_(facts_by_memo))
            .order_by(DealMemo.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    if len(memos) != len(facts_by_memo):
        raise LookupError("A deal to put on the record does not exist")
    parties = {
        application_id: (brand_account, creator_account)
        for application_id, brand_account, creator_account in db.execute(
            select(Application.id, Brand.account_id, Creator.account_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .join(Brand, Brand.id == Campaign.brand_id)
            .join(Creator, Creator.id == Application.creator_id)
            .where(Application.id.in_([memo.application_id for memo in memos]))
        ).tuples()
    }
    # Each deal's newest entry, in one statement (served by the unique
    # (deal, sequence) index).
    last = {
        entry.deal_memo_id: entry
        for entry in db.scalars(
            select(DealRecordEntry)
            .where(DealRecordEntry.deal_memo_id.in_(facts_by_memo))
            .order_by(DealRecordEntry.deal_memo_id, DealRecordEntry.sequence.desc())
            .ext(distinct_on(DealRecordEntry.deal_memo_id))
        ).all()
    }

    entries: list[DealRecordEntry] = []
    for memo in memos:
        accounts = _accounts(db, *parties[memo.application_id])
        previous = last.get(memo.id)
        if _needs_opening(previous, kind, memo):
            previous = _sealed(
                memo,
                None,
                kind="record_started",
                actor_role="system",
                actor_account_id=None,
                occurred_at=now,
                now=now,
                facts={"terms_sha256": terms_fingerprint(memo)},
            )
            entries.append(previous)
        entries.append(
            _sealed(
                memo,
                previous,
                kind=kind,
                actor_role=actor_role,
                actor_account_id=accounts[actor_role],
                occurred_at=now,
                now=now,
                facts=facts_by_memo[memo.id],
            )
        )
    # Written by hand, in one statement: the database makes each entry's id,
    # and the ORM writes one INSERT per row when it does.
    db.execute(
        insert(DealRecordEntry),
        [{field: getattr(entry, field) for field in _WRITTEN} for entry in entries],
    )


# What `append_each` writes of each entry: everything but the id, which the
# database makes.
_WRITTEN: tuple[str, ...] = (
    "deal_memo_id",
    "sequence",
    "kind",
    "actor_role",
    "actor_account_id",
    "occurred_at",
    "recorded_at",
    "facts",
    "previous_hash",
    "entry_hash",
)


def append_for_payment(
    db: Session, payment_id: uuid.UUID, **entry: Any
) -> DealRecordEntry:
    """`append` for callers that hold a payment rather than its deal."""
    memo = db.scalars(
        select(DealMemo)
        .join(PaymentStatus, PaymentStatus.deal_memo_id == DealMemo.id)
        .where(PaymentStatus.id == payment_id)
    ).one()
    return append(db, memo, **entry)


def terms_facts(memo: DealMemo) -> dict[str, Any]:
    """What a sent or accepted memo puts on the record: the terms' fingerprint,
    and the two terms people argue about most, in plain figures."""
    return {
        "terms_sha256": terms_fingerprint(memo),
        "fee_amount_paise": memo.fee_amount_paise,
        "content_due_on": memo.content_due_on.isoformat()
        if memo.content_due_on
        else None,
    }


# --- reading and checking ---------------------------------------------------


def actor_first_names(
    db: Session, memo: DealMemo, entries: list[DealRecordEntry]
) -> dict[uuid.UUID, str]:
    """The first name of each team member who acted on the brand's side (D-148).

    Read when the record is, not sealed: the seal names the account, and the
    name is how the brand's team knows that person today. The brand's owner
    has none, since the brand's own name stands for them; a member who left
    keeps theirs, so who acted on an old deal stays known. One query.
    """
    actors = {
        e.actor_account_id
        for e in entries
        if e.actor_role == "brand" and e.actor_account_id is not None
    }
    if not actors:
        return {}
    rows = db.execute(
        select(BrandMember.account_id, BrandMember.first_name)
        .join(Brand, Brand.id == BrandMember.brand_id)
        .join(Campaign, Campaign.brand_id == Brand.id)
        .join(Application, Application.campaign_id == Campaign.id)
        .where(
            Application.id == memo.application_id,
            BrandMember.account_id.in_(actors),
            BrandMember.account_id != Brand.account_id,
        )
        # The newest membership last, so it is the one kept.
        .order_by(BrandMember.created_at, BrandMember.id)
    ).all()
    return {account_id: first_name for account_id, first_name in rows}


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
