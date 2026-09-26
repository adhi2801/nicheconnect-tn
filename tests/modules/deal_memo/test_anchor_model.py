"""Checkpoint tables: append-only, enforced by the database itself (D-060)."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from psycopg.errors import Diagnostic
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError

from app.modules.deal_memo.anchor_models import DealRecordCheckpoint, DealRecordTimestamp
from tests.factories import FIXED_NOW

ROOT = bytes(range(32))


def checkpoint(db, **overrides) -> DealRecordCheckpoint:
    fields = {"covers_until": FIXED_NOW, "leaf_count": 3, "merkle_root": ROOT}
    fields.update(overrides)
    row = DealRecordCheckpoint(**fields)
    db.add(row)
    db.flush()
    return row


def stamp(db, checkpoint_id, **overrides) -> DealRecordTimestamp:
    fields = {
        "checkpoint_id": checkpoint_id,
        "authority": "digicert",
        "token": b"\x30\x03\x02\x01\x00",
        "signed_at": FIXED_NOW + timedelta(minutes=1),
    }
    fields.update(overrides)
    row = DealRecordTimestamp(**fields)
    db.add(row)
    db.flush()
    return row


def refused(db, action: Callable[[], object]) -> Diagnostic:
    """Run `action` in a savepoint and return what the database said."""
    with pytest.raises(IntegrityError) as exc_info, db.begin_nested():
        action()
    return exc_info.value.orig.diag


def test_a_checkpoint_and_its_stamps_get_time_ordered_ids(db):
    row = checkpoint(db)
    token = stamp(db, row.id)

    assert row.id.version == 7
    assert token.id.version == 7


# --- nothing can be rewritten ------------------------------------------------------


@pytest.mark.parametrize("model", [DealRecordCheckpoint, DealRecordTimestamp])
def test_neither_table_can_be_updated_or_deleted(db, model):
    row = checkpoint(db)
    target = row if model is DealRecordCheckpoint else stamp(db, row.id)
    table = model.__tablename__

    changed = refused(
        db,
        lambda: db.execute(
            update(model).where(model.id == target.id).values(created_at=FIXED_NOW)
        ),
    )
    removed = refused(db, lambda: db.execute(delete(model).where(model.id == target.id)))

    assert changed.message_primary == f"{table} is append-only: UPDATE refused"
    assert removed.message_primary == f"{table} is append-only: DELETE refused"


@pytest.mark.parametrize("table", ["deal_record_checkpoint", "deal_record_timestamp"])
def test_neither_table_can_be_truncated(db, table):
    checkpoint(db)

    said = refused(db, lambda: db.execute(text(f"TRUNCATE {table} CASCADE")))

    assert said.message_primary == f"{table} is append-only: TRUNCATE refused"


# --- the rules ---------------------------------------------------------------------


def test_one_checkpoint_per_cut_off(db):
    checkpoint(db)

    said = refused(db, lambda: checkpoint(db))

    assert said.constraint_name == "uq_deal_record_checkpoint_covers_until"


def test_one_stamp_per_authority_per_checkpoint(db):
    row = checkpoint(db)
    stamp(db, row.id, authority="digicert")
    stamp(db, row.id, authority="sectigo")

    said = refused(db, lambda: stamp(db, row.id, authority="digicert"))

    assert said.constraint_name == "uq_deal_record_timestamp_authority"


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"leaf_count": -1}, "leaf_count_not_negative"),
        ({"merkle_root": bytes(31)}, "merkle_root_length"),
        ({"merkle_root": bytes(33)}, "merkle_root_length"),
    ],
)
def test_checkpoint_rules_are_enforced_by_the_database(db, overrides, constraint):
    said = refused(db, lambda: checkpoint(db, **overrides))

    assert said.constraint_name == f"ck_deal_record_checkpoint_{constraint}"


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"authority": "a-friend-of-ours"}, "authority_allowed"),
        ({"token": b""}, "token_not_empty"),
    ],
)
def test_stamp_rules_are_enforced_by_the_database(db, overrides, constraint):
    row = checkpoint(db)

    said = refused(db, lambda: stamp(db, row.id, **overrides))

    assert said.constraint_name == f"ck_deal_record_timestamp_{constraint}"


def test_a_stamp_needs_a_real_checkpoint(db):
    import uuid

    said = refused(db, lambda: stamp(db, uuid.uuid4()))

    assert (
        said.constraint_name
        == "fk_deal_record_timestamp_checkpoint_id_deal_record_checkpoint"
    )
