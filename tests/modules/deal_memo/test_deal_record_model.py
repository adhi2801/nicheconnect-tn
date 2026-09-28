"""The deal record table: append-only, enforced by the database itself (D-057)."""

import uuid
from collections.abc import Callable

import pytest
from psycopg.errors import Diagnostic
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError

from app.modules.campaigns.models import Application
from app.modules.deal_memo import record_service
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import GENESIS_HASH, DealRecordEntry
from tests.factories import FIXED_NOW, build_campaign, build_creator

ONES_32 = bytes([1]) * 32


def make_memo(db) -> DealMemo:
    campaign = build_campaign(db, status="open")
    db.add(campaign)
    creator = build_creator(db, handle=f"rec{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    application = Application(
        campaign_id=campaign.id,
        creator_id=creator.id,
        pitch="I run a Madurai street-food page with 12,000 local followers.",
        status="accepted",
        status_changed_at=FIXED_NOW,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    db.add(application)
    db.flush()
    memo = DealMemo(
        application_id=application.id,
        deliverables="3 Instagram reels, 1 story set.",
        fee_amount_paise=800_000,
        status="sent",
        sent_at=FIXED_NOW,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    db.add(memo)
    db.flush()
    return memo


def sealed_entry(db) -> DealRecordEntry:
    memo = make_memo(db)
    return record_service.append(
        db, memo, kind="memo_sent", actor_role="brand", now=FIXED_NOW
    )


def raw_entry(memo: DealMemo, **overrides) -> DealRecordEntry:
    """An entry built by hand, to reach the constraints directly."""
    fields = {
        "deal_memo_id": memo.id,
        "sequence": 1,
        "kind": "memo_sent",
        "actor_role": "system",
        "actor_account_id": None,
        "occurred_at": FIXED_NOW,
        "recorded_at": FIXED_NOW,
        "facts": {},
        "previous_hash": GENESIS_HASH,
        "entry_hash": bytes(range(32)),
    }
    fields.update(overrides)
    return DealRecordEntry(**fields)


def refused(db, action: Callable[[], object]) -> Diagnostic:
    """Run `action` in a savepoint and return what the database said.

    The savepoint sits inside `pytest.raises`, so it is rolled back as the
    error passes through it and the test's own transaction stays usable.
    """
    with pytest.raises(IntegrityError) as exc_info, db.begin_nested():
        action()
    return exc_info.value.orig.diag


def inserting(db, entry: DealRecordEntry) -> Callable[[], None]:
    def insert() -> None:
        db.add(entry)
        db.flush()

    return insert


# --- what a valid entry looks like ---------------------------------------------


def test_an_entry_gets_a_time_ordered_id_and_a_32_byte_seal(db):
    entry = sealed_entry(db)

    assert entry.id.version == 7  # uuidv7(), D-047
    assert len(entry.entry_hash) == 32
    assert entry.previous_hash == GENESIS_HASH
    assert entry.sequence == 1


# --- the database refuses to rewrite history -----------------------------------


def test_an_entry_cannot_be_updated(db):
    entry = sealed_entry(db)

    said = refused(
        db,
        lambda: db.execute(
            update(DealRecordEntry)
            .where(DealRecordEntry.id == entry.id)
            .values(facts={"fee_amount_paise": 1})
        ),
    )

    assert said.message_primary == "deal_record_entry is append-only: UPDATE refused"


def test_an_entry_cannot_be_deleted(db):
    entry = sealed_entry(db)

    said = refused(
        db,
        lambda: db.execute(delete(DealRecordEntry).where(DealRecordEntry.id == entry.id)),
    )

    assert said.message_primary == "deal_record_entry is append-only: DELETE refused"


def test_the_table_cannot_be_truncated(db):
    sealed_entry(db)

    said = refused(db, lambda: db.execute(text("TRUNCATE deal_record_entry")))

    assert said.message_primary == "deal_record_entry is append-only: TRUNCATE refused"


def test_a_deal_with_a_record_cannot_be_deleted(db):
    entry = sealed_entry(db)

    said = refused(
        db,
        lambda: db.execute(delete(DealMemo).where(DealMemo.id == entry.deal_memo_id)),
    )

    assert said.constraint_name == "fk_deal_record_entry_deal_memo_id_deal_memo"


# --- the constraints -----------------------------------------------------------


def test_two_entries_cannot_claim_the_same_place(db):
    """The backstop against a forked chain."""
    entry = sealed_entry(db)
    memo = db.get(DealMemo, entry.deal_memo_id)

    said = refused(db, inserting(db, raw_entry(memo)))

    assert said.constraint_name == "uq_deal_record_entry_sequence"


# Each bad row breaks exactly one rule, so which rule is reported is never
# down to the order Postgres happens to check them in.
@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"sequence": 0, "previous_hash": ONES_32}, "sequence_positive"),
        ({"kind": "memo_edited_quietly"}, "kind_allowed"),
        (
            {"actor_role": "admin", "actor_account_id": uuid.uuid4()},
            "actor_role_allowed",
        ),
        ({"actor_role": "brand"}, "actor_account_matches_role"),
        ({"actor_account_id": uuid.uuid4()}, "actor_account_matches_role"),
        (
            {"sequence": 2, "previous_hash": bytes([1]) * 31},
            "previous_hash_length",
        ),
        ({"entry_hash": bytes([1]) * 33}, "entry_hash_length"),
        ({"previous_hash": ONES_32}, "genesis_only_first"),
        ({"sequence": 2}, "genesis_only_first"),
        ({"facts": ["not", "an", "object"]}, "facts_is_object"),
    ],
)
def test_each_rule_is_enforced_by_the_database(db, overrides, constraint):
    memo = make_memo(db)

    said = refused(db, inserting(db, raw_entry(memo, **overrides)))

    assert said.constraint_name == f"ck_deal_record_entry_{constraint}"
