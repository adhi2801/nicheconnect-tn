"""The daily checkpoint and a deal's proof (D-060), with authorities faked.

The authorities' real signatures are tested in test_timestamp_authority.py;
here they are stand-ins, so the tests are about the checkpoint itself.
"""

import logging
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, text

from app.core.clock import IST
from app.modules.deal_memo import anchor_service, merkle, record_service
from app.modules.deal_memo.anchor_models import DealRecordCheckpoint, DealRecordTimestamp
from app.modules.deal_memo.anchor_service import NotInCheckpoint
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.timestamp_authority import Stamp, TimestampFailed
from tests.modules.deal_memo.test_deal_record_model import make_memo

DAY = date(2026, 9, 27)
MIDNIGHT = datetime(2026, 9, 27, 0, 0, tzinfo=IST)
BEFORE = MIDNIGHT - timedelta(hours=3)
AFTER = MIDNIGHT + timedelta(hours=3)


@pytest.fixture(autouse=True)
def empty_record(db):
    """A checkpoint covers every deal, so each test starts from none.

    The record refuses deletion; inside this test's own transaction, which is
    rolled back afterwards, the triggers are set aside for the delete and then
    restored, so the tests below run with append-only fully in force.
    """
    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(delete(DealRecordTimestamp))
    db.execute(delete(DealRecordCheckpoint))
    db.execute(delete(DealRecordEntry))
    db.execute(text("SET LOCAL session_replication_role = origin"))


class FakeAuthority:
    def __init__(self, name: str, *, fails: bool = False):
        self.name = name
        self.fails = fails
        self.asked: list[bytes] = []

    def stamp(self, fingerprint: bytes) -> Stamp:
        self.asked.append(fingerprint)
        if self.fails:
            raise TimestampFailed(f"{self.name} unreachable after 3 attempts")
        return Stamp(token=b"token-from-" + self.name.encode(), signed_at=MIDNIGHT)


def deal_with_entries(db, *times: datetime):
    memo = make_memo(db)
    kinds = ["memo_sent", "memo_accepted", "payment_opened"]
    for kind, moment in zip(kinds, times, strict=False):
        record_service.append(
            db,
            memo,
            kind=kind,
            actor_role="system" if kind == "payment_opened" else "brand",
            now=moment,
        )
    return memo


def latest_seal(db, memo_id, cutoff: datetime) -> bytes:
    return db.scalar(
        select(DealRecordEntry.entry_hash)
        .where(
            DealRecordEntry.deal_memo_id == memo_id, DealRecordEntry.recorded_at < cutoff
        )
        .order_by(DealRecordEntry.sequence.desc())
        .limit(1)
    )


# --- building a checkpoint ---------------------------------------------------------


def test_the_root_covers_each_deals_latest_seal_before_midnight(db):
    first = deal_with_entries(db, BEFORE - timedelta(hours=1), BEFORE)
    second = deal_with_entries(db, BEFORE)

    checkpoint = anchor_service.create_checkpoint(db, DAY)

    expected = sorted(
        m.id.bytes + latest_seal(db, m.id, MIDNIGHT) for m in (first, second)
    )
    assert checkpoint.leaf_count == 2
    assert checkpoint.merkle_root == merkle.root(expected)
    assert checkpoint.covers_until == MIDNIGHT


def test_entries_after_midnight_wait_for_the_next_checkpoint(db):
    memo = deal_with_entries(db, BEFORE, AFTER)
    later_only = deal_with_entries(db, AFTER)

    checkpoint = anchor_service.create_checkpoint(db, DAY)

    assert checkpoint.leaf_count == 1
    assert checkpoint.merkle_root == merkle.root(
        [memo.id.bytes + latest_seal(db, memo.id, MIDNIGHT)]
    )
    with pytest.raises(NotInCheckpoint):
        anchor_service.proof_for(db, later_only.id, checkpoint)


def test_a_day_with_no_deals_still_gets_a_checkpoint(db):
    checkpoint = anchor_service.create_checkpoint(db, DAY)

    assert checkpoint.leaf_count == 0
    assert checkpoint.merkle_root == merkle.root([])


def test_a_checkpoint_is_written_once(db):
    deal_with_entries(db, BEFORE)
    first = anchor_service.create_checkpoint(db, DAY)

    again = anchor_service.create_checkpoint(db, DAY)

    assert again.id == first.id
    assert db.scalar(select(func.count()).select_from(DealRecordCheckpoint)) == 1


# --- stamping --------------------------------------------------------------------------


def test_each_authority_stamps_the_root(db):
    deal_with_entries(db, BEFORE)
    checkpoint = anchor_service.create_checkpoint(db, DAY)
    digicert, sectigo = FakeAuthority("digicert"), FakeAuthority("sectigo")

    stamped = anchor_service.stamp_checkpoint(db, checkpoint, [digicert, sectigo])

    assert stamped == ["digicert", "sectigo"]
    assert digicert.asked == sectigo.asked == [checkpoint.merkle_root]
    rows = db.scalars(
        select(DealRecordTimestamp).order_by(DealRecordTimestamp.authority)
    ).all()
    assert [(r.authority, r.token) for r in rows] == [
        ("digicert", b"token-from-digicert"),
        ("sectigo", b"token-from-sectigo"),
    ]


def test_an_unreachable_authority_leaves_a_visible_gap_and_is_asked_again(db, caplog):
    checkpoint = anchor_service.create_checkpoint(db, DAY)
    caplog.set_level(logging.WARNING)

    stamped = anchor_service.stamp_checkpoint(
        db, checkpoint, [FakeAuthority("digicert"), FakeAuthority("sectigo", fails=True)]
    )

    assert stamped == ["digicert"]
    assert "authority=sectigo" in caplog.text

    digicert_again, sectigo_again = FakeAuthority("digicert"), FakeAuthority("sectigo")
    stamped = anchor_service.stamp_checkpoint(
        db, checkpoint, [digicert_again, sectigo_again]
    )

    assert stamped == ["sectigo"]
    assert digicert_again.asked == []  # already stamped, not asked twice


def test_the_daily_run_restamps_recent_gaps_but_not_old_ones(db):
    recent = anchor_service.create_checkpoint(db, DAY - timedelta(days=3))
    old = anchor_service.create_checkpoint(db, DAY - timedelta(days=30))
    authority = FakeAuthority("digicert")

    run = anchor_service.run_daily(db, MIDNIGHT + timedelta(minutes=10), [authority])

    assert run.checkpoint_day == DAY
    assert set(run.stamped) == {DAY - timedelta(days=3), DAY}
    assert recent.merkle_root in authority.asked
    assert old.id not in {
        r.checkpoint_id for r in db.scalars(select(DealRecordTimestamp)).all()
    }


# --- a deal's proof --------------------------------------------------------------------


def test_every_deals_proof_leads_to_the_stamped_root(db):
    memos = [deal_with_entries(db, BEFORE - timedelta(minutes=i)) for i in range(5)]
    checkpoint = anchor_service.create_checkpoint(db, DAY)

    for memo in memos:
        proof = anchor_service.proof_for(db, memo.id, checkpoint)
        rebuilt = merkle.root_from_path(
            proof.leaf_index,
            checkpoint.leaf_count,
            memo.id.bytes + proof.seal,
            proof.audit_path,
        )
        assert rebuilt == checkpoint.merkle_root


def test_a_backdated_entry_is_caught(db):
    """The point of the checkpoint: an entry slipped in after the day was
    stamped, dated before its cut-off, no longer leads to the stamped root."""
    memo = deal_with_entries(db, BEFORE - timedelta(hours=1))
    checkpoint = anchor_service.create_checkpoint(db, DAY)

    record_service.append(db, memo, kind="memo_accepted", actor_role="brand", now=BEFORE)

    with pytest.raises(RuntimeError, match="no longer matches"):
        anchor_service.proof_for(db, memo.id, checkpoint)


def test_the_latest_checkpoint_holding_a_deal_is_found(db):
    memo = deal_with_entries(db, BEFORE)
    anchor_service.create_checkpoint(db, DAY - timedelta(days=1))  # before the deal
    today = anchor_service.create_checkpoint(db, DAY)
    tomorrow = anchor_service.create_checkpoint(db, DAY + timedelta(days=1))

    found = anchor_service.latest_checkpoint_with(db, memo.id)

    assert found is not None
    assert found.id == tomorrow.id
    assert found.id != today.id


def test_a_deal_with_no_record_is_in_no_checkpoint(db):
    memo = make_memo(db)
    anchor_service.create_checkpoint(db, DAY)

    assert anchor_service.latest_checkpoint_with(db, memo.id) is None
