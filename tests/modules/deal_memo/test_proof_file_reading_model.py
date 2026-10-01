"""The proof_file_reading table refuses every reading that claims too much (D-070).

These go straight to the database, below the service: whatever the code does,
a reading can never carry numbers it did not read, fail without a reason, or
hold a negative count.
"""

import hashlib
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.deal_memo import proof_reader
from app.modules.deal_memo.proof_models import ProofFile
from app.modules.deal_memo.proof_reading_models import (
    READING_FAILURES,
    READING_METRICS,
    READING_STATUSES,
    ProofFileReading,
)
from app.modules.deal_memo.record_models import RECORD_KINDS
from tests.factories import FIXED_NOW, create_account
from tests.modules.deal_memo.test_deal_memo_model import build_memo
from tests.modules.deal_memo.test_proof_file_model import a_proof

SHA = hashlib.sha256(b"a clean screenshot").hexdigest()


@pytest.fixture
def cleaned_file(db) -> ProofFile:
    memo = build_memo(db)
    db.add(memo)
    db.flush()
    proof = a_proof(db, memo)
    file = ProofFile(
        deal_memo_id=memo.id,
        uploader_account_id=create_account(db, "creator").id,
        storage_key=f"proof-files/incoming/{uuid.uuid4()}",
        content_type="image/png",
        size_bytes=1024,
        sha256=SHA,
        status="cleaned",
        proof_id=proof.id,
        position=0,
        attached_at=FIXED_NOW,
        clean_key=f"proof-files/clean/{uuid.uuid4()}.png",
        clean_sha256=SHA,
        clean_size_bytes=900,
        cleaned_at=FIXED_NOW,
    )
    db.add(file)
    db.flush()
    return file


def a_reading(file: ProofFile, **overrides) -> ProofFileReading:
    fields = {
        "proof_file_id": file.id,
        "status": "read",
        "model": "claude-opus-5-5",
        "prompt_version": proof_reader.PROMPT_VERSION,
        "views": 48210,
        "reach": 31400,
        "read_at": FIXED_NOW,
    }
    fields.update(overrides)
    return ProofFileReading(**fields)


def refused(db, row, constraint: str) -> None:
    db.add(row)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint in str(exc_info.value)
    db.rollback()


# --- what is allowed -------------------------------------------------------------------


def test_a_reading_with_numbers_is_kept(db, cleaned_file):
    row = a_reading(cleaned_file, abbreviated=["views"], handle="priya.eats")
    db.add(row)
    db.flush()
    db.refresh(row)

    assert row.id.version == 7
    assert row.abbreviated == ["views"]
    assert (row.attempts, row.input_tokens, row.output_tokens) == (1, 0, 0)


@pytest.mark.parametrize(
    ("status", "failure"), [("no_numbers", None), ("failed", "api_error")]
)
def test_a_reading_without_numbers_is_kept(db, cleaned_file, status, failure):
    db.add(
        a_reading(cleaned_file, status=status, failure=failure, views=None, reach=None)
    )
    db.flush()


# --- what is refused -----------------------------------------------------------------------


def test_one_reading_per_file(db, cleaned_file):
    db.add(a_reading(cleaned_file))
    db.flush()

    refused(db, a_reading(cleaned_file), "uq_proof_file_reading_proof_file_id")


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"status": "verified", "views": None, "reach": None}, "status_allowed"),
        ({"status": "failed", "views": None, "reach": None}, "failed_has_reason"),
        ({"failure": "api_error"}, "failed_has_reason"),
        (
            {"status": "failed", "failure": "bored", "views": None, "reach": None},
            "failure_allowed",
        ),
        ({"views": None, "reach": None}, "numbers_only_when_read"),
        ({"status": "no_numbers"}, "numbers_only_when_read"),
        ({"views": -1}, "numbers_not_negative"),
        ({"platform": "myspace"}, "platform_allowed"),
        ({"abbreviated": ["followers"]}, "abbreviated_allowed"),
        ({"stated_followers": -5}, "stated_followers_valid"),
        ({"stated_average_views": -5}, "stated_average_views_valid"),
        ({"attempts": 0}, "attempts_positive"),
        ({"input_tokens": -1}, "tokens_not_negative"),
        ({"creator_note": "the reach is wrong"}, "note_has_mark"),
    ],
)
def test_a_reading_that_claims_too_much_is_refused(
    db, cleaned_file, overrides, constraint
):
    refused(
        db, a_reading(cleaned_file, **overrides), f"ck_proof_file_reading_{constraint}"
    )


def test_a_reading_needs_a_real_file(db):
    refused(
        db, a_reading(ProofFile(id=uuid.uuid4())), "fk_proof_file_reading_proof_file_id"
    )


def test_a_file_with_a_reading_cannot_be_deleted(db, cleaned_file):
    """RESTRICT: evidence stays with the deal."""
    db.add(a_reading(cleaned_file))
    db.flush()

    db.delete(cleaned_file)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert "fk_proof_file_reading_proof_file_id_proof_file" in str(exc_info.value)


# --- the code and the database agree --------------------------------------------------------


def test_the_reader_and_the_table_name_the_same_metrics_and_failures():
    assert tuple(proof_reader.METRICS) == READING_METRICS
    assert set(proof_reader.Failure.__args__) == set(READING_FAILURES)
    assert set(proof_reader.ReadingStatus.__args__) == set(READING_STATUSES)


def test_the_record_can_seal_a_reading():
    assert "proof_results_read" in RECORD_KINDS


# --- in a person's data export (DPDP) ---------------------------------------------------


def test_both_sides_of_the_deal_get_the_readings_in_their_export(db, cleaned_file):
    from app.modules.auth.models.brand import Brand
    from app.modules.auth.models.creator import Creator
    from app.modules.campaigns.models import Application, Campaign
    from app.modules.deal_memo import service as deal_memos
    from app.modules.deal_memo.models import DealMemo

    row = a_reading(
        cleaned_file, creator_marked_at=FIXED_NOW, creator_note="reach is 31,040"
    )
    db.add(row)
    db.flush()
    memo = db.get(DealMemo, cleaned_file.deal_memo_id)
    application = db.get(Application, memo.application_id)
    creator = db.get(Creator, application.creator_id)
    brand = db.get(Brand, db.get(Campaign, application.campaign_id).brand_id)

    for account_id in (creator.account_id, brand.account_id):
        sections = {s.name: s for s in deal_memos.export_for_account(db, account_id)}
        [exported] = sections["proof_file_readings"].records
        assert exported["id"] == str(row.id)
        assert exported["views"] == 48210
        assert exported["creator_note"] == "reach is 31,040"
        # Our cost of reading is not the person's data.
        assert "input_tokens" not in exported
        assert "output_tokens" not in exported
