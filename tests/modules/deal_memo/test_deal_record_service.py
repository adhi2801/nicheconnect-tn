"""Sealing and checking the deal record, below the HTTP layer (D-057)."""

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text

from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import record_service
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import GENESIS_HASH, DealRecordEntry
from tests.factories import FIXED_NOW
from tests.modules.deal_memo.test_deal_record_model import make_memo


def make_memo_terms() -> DealMemo:
    """Terms only, never saved: what the terms fingerprint reads."""
    return DealMemo(
        deliverables="2 reels.",
        fee_amount_paise=800_000,
        currency="INR",
        cancellation_fee_paise=0,
        approval_window_days=7,
        payment_due_days=7,
        usage_rights_days=90,
        content_due_on=date(2026, 12, 31),
        disclosure_required=True,
        extra_terms=None,
    )


# --- the fingerprint, version 1, frozen ------------------------------------------


def test_the_v1_fingerprint_is_exactly_what_the_documentation_says():
    """A known answer, worked out by hand rather than by our own code.

    If this fails, every existing chain would stop verifying: the change is
    not a refactor, it is version 2.
    """
    memo_id = uuid.UUID("0192f7a0-0000-7000-8000-000000000001")
    body = {
        "deal_memo_id": str(memo_id),
        "sequence": 1,
        "kind": "memo_sent",
        "actor_role": "system",
        "actor_account_sha256": None,
        "occurred_at": "2026-09-26T06:30:00.000000Z",
        "recorded_at": "2026-09-26T06:30:00.000000Z",
        "facts": {"fee_amount_paise": 800000, "terms_sha256": "ab"},
    }
    by_hand = (
        b'{"actor_account_sha256":null,"actor_role":"system",'
        b'"deal_memo_id":"0192f7a0-0000-7000-8000-000000000001",'
        b'"facts":{"fee_amount_paise":800000,"terms_sha256":"ab"},'
        b'"kind":"memo_sent","occurred_at":"2026-09-26T06:30:00.000000Z",'
        b'"recorded_at":"2026-09-26T06:30:00.000000Z","sequence":1}'
    )
    expected = hashlib.sha256(b"deal-record/v1\n" + bytes(32) + by_hand).digest()

    assert record_service.canonical(body) == by_hand
    assert record_service.compute_hash(GENESIS_HASH, body) == expected


def test_an_entry_is_sealed_from_exactly_the_documented_fields():
    """The same known answer, reached from a real entry through `entry_body`.

    The test above hashes a body typed by hand; this one checks that an entry
    is turned into exactly that body: every key, the actor's fingerprint, and
    times given in Tamil Nadu time spelled in UTC. Mutation testing found
    every key could be renamed without a fast test failing (D-091).
    """
    memo_id = uuid.UUID("0192f7a0-0000-7000-8000-000000000001")
    actor = uuid.UUID("0192f7a0-0000-7000-8000-0000000000aa")
    at = datetime(2026, 9, 26, 12, 0, 0, 123456, tzinfo=ZoneInfo("Asia/Kolkata"))
    entry = DealRecordEntry(
        deal_memo_id=memo_id,
        sequence=2,
        kind="memo_accepted",
        actor_role="creator",
        actor_account_id=actor,
        occurred_at=at,
        recorded_at=at + timedelta(seconds=1),
        facts={"terms_sha256": "ab"},
    )
    actor_sha = hashlib.sha256(str(actor).encode("utf-8")).hexdigest()
    by_hand = (
        b'{"actor_account_sha256":"' + actor_sha.encode() + b'","actor_role":"creator",'
        b'"deal_memo_id":"0192f7a0-0000-7000-8000-000000000001",'
        b'"facts":{"terms_sha256":"ab"},'
        b'"kind":"memo_accepted","occurred_at":"2026-09-26T06:30:00.123456Z",'
        b'"recorded_at":"2026-09-26T06:30:01.123456Z","sequence":2}'
    )

    assert record_service.canonical(record_service.entry_body(entry)) == by_hand


def test_the_terms_fingerprint_spells_a_date_as_iso():
    memo = make_memo_terms()
    terms = {field: getattr(memo, field) for field in record_service.TERMS_FIELDS}
    terms["content_due_on"] = "2026-12-31"
    by_hand = hashlib.sha256(
        json.dumps(terms, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert record_service.terms_fingerprint(memo) == by_hand


def test_times_have_one_spelling_whatever_zone_they_arrive_in():
    ist = FIXED_NOW.astimezone(ZoneInfo("Asia/Kolkata"))

    assert record_service.timestamp(ist) == record_service.timestamp(FIXED_NOW)
    assert record_service.timestamp(FIXED_NOW).endswith("Z")


@pytest.mark.parametrize(
    "value", [{"fee": 1.5}, {"when": FIXED_NOW}, {1: "numeric key"}, {"set": {1}}]
)
def test_values_with_more_than_one_spelling_are_refused(value):
    with pytest.raises(TypeError):
        record_service.canonical(value)


def test_a_time_without_a_zone_is_refused():
    with pytest.raises(ValueError):
        record_service.timestamp(datetime(2026, 9, 26, 12, 0))  # noqa: DTZ001


def test_typed_text_is_kept_as_a_fingerprint_only():
    assert (
        record_service.fingerprint("UTR 412345678901")
        == hashlib.sha256(b"UTR 412345678901").hexdigest()
    )


# --- appending ---------------------------------------------------------------------


def test_entries_chain_one_to_the_next(db):
    memo = make_memo(db)
    first = record_service.append(
        db, memo, kind="memo_sent", actor_role="brand", now=FIXED_NOW
    )
    second = record_service.append(
        db, memo, kind="memo_accepted", actor_role="creator", now=FIXED_NOW
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert second.previous_hash == first.entry_hash
    assert record_service.verify(memo, [first, second]).intact


def test_the_actor_is_the_deals_own_account_for_that_side(db):
    memo = make_memo(db)
    brand, creator = record_service._party_account_ids(db, memo)

    by_brand = record_service.append(
        db, memo, kind="memo_sent", actor_role="brand", now=FIXED_NOW
    )
    by_creator = record_service.append(
        db, memo, kind="memo_accepted", actor_role="creator", now=FIXED_NOW
    )
    by_us = record_service.append(
        db, memo, kind="payment_opened", actor_role="system", now=FIXED_NOW
    )

    assert by_brand.actor_account_id == brand
    assert by_creator.actor_account_id == creator
    assert by_us.actor_account_id is None


def test_a_deal_with_earlier_history_opens_with_record_started(db):
    """No deal pretends its record reaches further back than it does."""
    memo = make_memo(db)

    entry = record_service.append(
        db, memo, kind="memo_accepted", actor_role="creator", now=FIXED_NOW
    )
    started, accepted = record_service.entries_for(db, memo.id)

    assert started.kind == "record_started"
    assert started.actor_role == "system"
    assert started.facts == {"terms_sha256": record_service.terms_fingerprint(memo)}
    assert accepted.id == entry.id
    assert entry.sequence == 2


def test_a_first_send_needs_no_opening_entry(db):
    memo = make_memo(db)

    record_service.append(db, memo, kind="memo_sent", actor_role="brand", now=FIXED_NOW)

    assert [e.kind for e in record_service.entries_for(db, memo.id)] == ["memo_sent"]


def test_a_resend_after_changes_with_no_record_opens_one(db):
    memo = make_memo(db)
    memo.revision_count = 1

    record_service.append(db, memo, kind="memo_sent", actor_role="brand", now=FIXED_NOW)

    assert [e.kind for e in record_service.entries_for(db, memo.id)] == [
        "record_started",
        "memo_sent",
    ]


def test_append_never_commits_on_its_own(db):
    """The change and its entry are committed together or not at all."""
    memo = make_memo(db)
    savepoint = db.begin_nested()
    record_service.append(db, memo, kind="memo_sent", actor_role="brand", now=FIXED_NOW)

    savepoint.rollback()

    count = db.scalar(select(func.count()).where(DealRecordEntry.deal_memo_id == memo.id))
    assert count == 0


def test_occurred_and_recorded_can_differ(db):
    memo = make_memo(db)
    deadline = FIXED_NOW - timedelta(days=2)

    entry = record_service.append(
        db,
        memo,
        kind="proof_auto_approved",
        actor_role="system",
        now=FIXED_NOW,
        occurred_at=deadline,
    )

    assert entry.occurred_at == deadline
    assert entry.recorded_at == FIXED_NOW


# --- checking ------------------------------------------------------------------------


def three_entries(db):
    memo = make_memo(db)
    for kind, actor in (
        ("memo_sent", "brand"),
        ("memo_accepted", "creator"),
        ("payment_opened", "system"),
    ):
        facts = (
            {"terms_sha256": record_service.terms_fingerprint(memo)}
            if kind == "memo_accepted"
            else {}
        )
        record_service.append(
            db, memo, kind=kind, actor_role=actor, now=FIXED_NOW, facts=facts
        )
    entries = record_service.entries_for(db, memo.id)
    # Detached, so the tests below can alter them in memory without the
    # database (which refuses) ever being asked to store the change.
    for entry in entries:
        db.expunge(entry)
    return memo, entries


def test_an_untouched_record_verifies(db):
    memo, entries = three_entries(db)

    result = record_service.verify(memo, entries)

    assert result.intact is True
    assert result.first_broken_sequence is None
    assert result.terms_unchanged_since_accepted is True


def test_a_changed_fact_is_caught_at_that_entry(db):
    memo, entries = three_entries(db)
    entries[1].facts = {"terms_sha256": "0" * 64}

    result = record_service.verify(memo, entries)

    assert result.intact is False
    assert result.first_broken_sequence == 2


def test_a_changed_time_is_caught(db):
    memo, entries = three_entries(db)
    entries[0].occurred_at = entries[0].occurred_at - timedelta(days=1)

    assert record_service.verify(memo, entries).first_broken_sequence == 1


def test_a_missing_entry_is_caught(db):
    memo, entries = three_entries(db)

    result = record_service.verify(memo, [entries[0], entries[2]])

    assert result.intact is False
    assert result.first_broken_sequence == 3


def test_a_rewritten_chain_with_fresh_seals_is_caught_by_a_saved_fingerprint(db):
    """Step 1's honest limit: rebuilding a whole chain recomputes every seal.
    A party who saved the last fingerprint still sees the difference."""
    memo, entries = three_entries(db)
    saved = entries[-1].entry_hash
    entries[1].facts = {"terms_sha256": "0" * 64}
    previous = GENESIS_HASH
    for entry in entries:
        entry.previous_hash = previous
        entry.entry_hash = record_service.compute_hash(
            previous, record_service.entry_body(entry)
        )
        previous = entry.entry_hash

    assert record_service.verify(memo, entries).intact is True  # the limit
    assert entries[-1].entry_hash != saved  # and how a party catches it


def test_terms_changed_after_acceptance_are_caught(db):
    memo, entries = three_entries(db)

    memo.fee_amount_paise = 600_000

    result = record_service.verify(memo, entries)
    assert result.intact is True
    assert result.terms_unchanged_since_accepted is False


def test_terms_are_not_judged_before_acceptance(db):
    memo = make_memo(db)
    record_service.append(db, memo, kind="memo_sent", actor_role="brand", now=FIXED_NOW)

    result = record_service.verify(memo, record_service.entries_for(db, memo.id))

    assert result.terms_unchanged_since_accepted is None


def test_the_actor_is_sealed_as_a_fingerprint_of_the_account_id():
    """So each side can check every seal without being shown the other's id."""
    account_id = uuid.UUID("0192f7a0-0000-7000-8000-00000000abcd")

    assert (
        record_service.actor_fingerprint(account_id)
        == hashlib.sha256(b"0192f7a0-0000-7000-8000-00000000abcd").hexdigest()
    )
    assert record_service.actor_fingerprint(None) is None


def test_an_entry_whose_previous_seal_alone_was_changed_is_caught(db):
    """Its own seal still matches its body, so only the chain link shows it."""
    memo, entries = three_entries(db)
    entries[1].previous_hash = bytes(32)

    result = record_service.verify(memo, entries)

    assert (result.intact, result.first_broken_sequence) == (False, 2)


def test_another_deals_record_does_not_check_for_this_deal(db):
    """Every seal of the other record is sound; it is just not this deal's."""
    memo, _ = three_entries(db)
    _, others = three_entries(db)

    result = record_service.verify(memo, others)

    assert (result.intact, result.first_broken_sequence) == (False, 1)


def test_a_record_is_read_in_order_of_sequence_whatever_order_it_was_written(db):
    """Mutation testing found the ordering could go without a test noticing
    (D-091): rows came back in the order written, which was always 1, 2, 3.
    Here they are written 3, 2, 1, so only the ORDER BY puts them right."""
    memo = make_memo(db)
    previous_hash, entries = GENESIS_HASH, []
    for sequence, kind in enumerate(("memo_sent", "memo_accepted", "payment_opened"), 1):
        entry = DealRecordEntry(
            deal_memo_id=memo.id,
            sequence=sequence,
            kind=kind,
            actor_role="system",
            actor_account_id=None,
            occurred_at=FIXED_NOW,
            recorded_at=FIXED_NOW,
            facts={},
            previous_hash=previous_hash,
        )
        entry.entry_hash = record_service.compute_hash(
            previous_hash, record_service.entry_body(entry)
        )
        previous_hash = entry.entry_hash
        entries.append(entry)
    for entry in reversed(entries):
        db.add(entry)
        db.flush()
    db.expire_all()
    # Read the table in the order written, as the planner may on any day:
    # an index scan would return 1, 2, 3 and hide a missing ORDER BY.
    for setting in ("enable_indexscan", "enable_indexonlyscan", "enable_bitmapscan"):
        db.execute(text(f"SET LOCAL {setting} = off"))

    found = record_service.entries_for(db, memo.id)

    assert [entry.sequence for entry in found] == [1, 2, 3]
    assert record_service.verify(memo, found).intact is True


def test_each_entry_names_the_account_of_the_side_that_acted(db):
    """The brand's entries carry the brand's account, the creator's the
    creator's, and the system's none. Mutation testing found that giving
    both sides the creator's account passed every fast test (D-091)."""
    memo = make_memo(db)
    application = db.get(Application, memo.application_id)
    creator_account = db.scalar(
        select(Creator.account_id).where(Creator.id == application.creator_id)
    )
    brand_account = db.scalar(
        select(Brand.account_id)
        .join(Campaign, Campaign.brand_id == Brand.id)
        .where(Campaign.id == application.campaign_id)
    )
    for kind, actor in (
        ("memo_sent", "brand"),
        ("memo_accepted", "creator"),
        ("payment_opened", "system"),
    ):
        record_service.append(db, memo, kind=kind, actor_role=actor, now=FIXED_NOW)

    found = {
        e.actor_role: e.actor_account_id for e in record_service.entries_for(db, memo.id)
    }

    assert found == {"brand": brand_account, "creator": creator_account, "system": None}
    assert brand_account != creator_account
