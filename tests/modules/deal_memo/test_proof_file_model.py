"""The proof_file table refuses every state that does not make sense (D-065).

These go straight to the database, below the service: whatever the code does,
a file can never claim to be cleaned without a clean copy, belong to a proof
while pending, or carry a fingerprint that is not one.
"""

import hashlib
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.deal_memo.proof_models import (
    MAX_PROOF_FILE_BYTES,
    DeliverableProof,
    ProofFile,
)
from tests.factories import FIXED_NOW, create_account
from tests.modules.deal_memo.test_deal_memo_model import build_memo

SHA = hashlib.sha256(b"a screenshot").hexdigest()


@pytest.fixture
def memo(db):
    memo = build_memo(db)
    db.add(memo)
    db.flush()
    return memo


@pytest.fixture
def uploader(db):
    return create_account(db, "creator")


def a_proof(db, memo, **overrides) -> DeliverableProof:
    fields = {
        "deal_memo_id": memo.id,
        "content_url": None,
        "format": "post",
        "status": "submitted",
        "created_at": FIXED_NOW,
        "updated_at": FIXED_NOW,
    }
    fields.update(overrides)
    proof = DeliverableProof(**fields)
    db.add(proof)
    db.flush()
    return proof


def a_file(memo, uploader, **overrides) -> ProofFile:
    fields = {
        "deal_memo_id": memo.id,
        "uploader_account_id": uploader.id,
        "storage_key": f"proof-files/incoming/{uuid.uuid4()}",
        "content_type": "image/png",
        "size_bytes": 1024,
        "sha256": SHA,
    }
    fields.update(overrides)
    return ProofFile(**fields)


def refused(db, row, constraint: str) -> None:
    db.add(row)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint in str(exc_info.value)
    db.rollback()


# --- what is allowed -------------------------------------------------------------------


def test_a_new_upload_is_pending_and_belongs_to_no_proof(db, memo, uploader):
    row = a_file(memo, uploader)
    db.add(row)
    db.flush()
    db.refresh(row)

    assert row.status == "pending"
    assert row.proof_id is None
    assert row.id.version == 7  # uuidv7, as every new table (D-049)


def test_a_cleaned_file_carries_its_clean_copy(db, memo, uploader):
    proof = a_proof(db, memo)
    row = a_file(
        memo,
        uploader,
        status="cleaned",
        proof_id=proof.id,
        position=0,
        attached_at=FIXED_NOW,
        clean_key="proof-files/clean/x.png",
        clean_sha256=SHA,
        clean_size_bytes=900,
        cleaned_at=FIXED_NOW,
    )
    db.add(row)
    db.flush()


def test_a_proof_may_now_have_no_link(db, memo):
    """D-065: files alone are evidence; the service insists on one or the other."""
    assert a_proof(db, memo).content_url is None


# --- what is refused ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        # A place, so the status check is the one that speaks: Postgres
        # tests checks in name order, and "position" comes before "status".
        ({"status": "lost", "position": 0}, "ck_proof_file_status_allowed"),
        ({"content_type": "image/gif"}, "ck_proof_file_content_type_allowed"),
        ({"content_type": "video/mp4"}, "ck_proof_file_content_type_allowed"),
        ({"size_bytes": 0}, "ck_proof_file_size_in_range"),
        ({"size_bytes": MAX_PROOF_FILE_BYTES + 1}, "ck_proof_file_size_in_range"),
        ({"sha256": "NOT-A-HASH"}, "ck_proof_file_sha256_hex"),
        ({"sha256": SHA.upper()}, "ck_proof_file_sha256_hex"),
        ({"clean_sha256": "short"}, "ck_proof_file_clean_sha256_hex"),
    ],
)
def test_nonsense_values_are_refused(db, memo, uploader, overrides, constraint):
    refused(db, a_file(memo, uploader, **overrides), constraint)


def test_a_pending_upload_cannot_already_belong_to_a_proof(db, memo, uploader):
    proof = a_proof(db, memo)
    refused(
        db,
        a_file(memo, uploader, proof_id=proof.id),
        "ck_proof_file_pending_is_unattached",
    )


def test_an_attached_file_must_name_its_proof(db, memo, uploader):
    refused(
        db,
        a_file(memo, uploader, status="attached", attached_at=FIXED_NOW),
        "ck_proof_file_attached_has_proof",
    )


def test_cleaned_without_a_clean_copy_is_refused(db, memo, uploader):
    proof = a_proof(db, memo)
    refused(
        db,
        a_file(
            memo, uploader, status="cleaned", proof_id=proof.id, attached_at=FIXED_NOW
        ),
        "ck_proof_file_cleaned_has_copy",
    )


def test_a_clean_copy_without_the_cleaned_status_is_refused(db, memo, uploader):
    refused(
        db,
        a_file(
            memo,
            uploader,
            clean_key="k",
            clean_sha256=SHA,
            clean_size_bytes=1,
            cleaned_at=FIXED_NOW,
        ),
        "ck_proof_file_cleaned_has_copy",
    )


def test_rejected_needs_a_reason_and_a_reason_needs_rejected(db, memo, uploader):
    refused(
        db,
        a_file(memo, uploader, status="rejected", position=0),
        "ck_proof_file_rejected_has_reason",
    )
    refused(
        db,
        a_file(memo, uploader, rejection_reason="missing"),
        "ck_proof_file_rejected_has_reason",
    )


def test_an_unknown_rejection_reason_is_refused(db, memo, uploader):
    refused(
        db,
        a_file(
            memo,
            uploader,
            status="rejected",
            position=0,
            rejection_reason="felt_like_it",
        ),
        "ck_proof_file_rejection_reason_allowed",
    )


def test_two_rows_cannot_claim_one_stored_object(db, memo, uploader):
    db.add(a_file(memo, uploader, storage_key="proof-files/incoming/same"))
    db.flush()

    refused(
        db,
        a_file(memo, uploader, storage_key="proof-files/incoming/same"),
        "uq_proof_file_storage_key",
    )


# --- a file's place in its proof (D-067) ---------------------------------------------------


def on_proof(memo, uploader, proof, position) -> ProofFile:
    return a_file(
        memo,
        uploader,
        status="attached",
        proof_id=proof.id,
        attached_at=FIXED_NOW,
        position=position,
    )


def test_a_pending_upload_has_no_place_yet(db, memo, uploader):
    refused(
        db, a_file(memo, uploader, position=0), "ck_proof_file_position_once_attached"
    )


def test_a_file_on_a_proof_must_have_a_place(db, memo, uploader):
    proof = a_proof(db, memo)
    refused(
        db,
        on_proof(memo, uploader, proof, position=None),
        "ck_proof_file_position_once_attached",
    )


@pytest.mark.parametrize("position", [-1, 10])
def test_a_place_outside_the_ten_is_refused(db, memo, uploader, position):
    proof = a_proof(db, memo)
    refused(
        db, on_proof(memo, uploader, proof, position), "ck_proof_file_position_in_range"
    )


def test_two_files_cannot_share_a_place_on_one_proof(db, memo, uploader):
    proof = a_proof(db, memo)
    db.add(on_proof(memo, uploader, proof, position=0))
    db.flush()

    refused(db, on_proof(memo, uploader, proof, position=0), "uq_proof_file_proof_id")


def test_the_same_place_on_two_proofs_is_fine(db, memo, uploader):
    # One proof waits for review at a time; the earlier one was sent back.
    first = a_proof(db, memo, status="revision_requested", revision_note="Add the label.")
    second = a_proof(db, memo)
    db.add_all(
        [
            on_proof(memo, uploader, first, position=0),
            on_proof(memo, uploader, second, position=0),
        ]
    )
    db.flush()


def test_a_proof_with_files_cannot_be_deleted(db, memo, uploader):
    """RESTRICT: evidence stays with the deal."""
    proof = a_proof(db, memo)
    db.add(
        a_file(
            memo,
            uploader,
            status="attached",
            proof_id=proof.id,
            position=0,
            attached_at=FIXED_NOW,
        )
    )
    db.flush()

    db.delete(proof)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert "fk_proof_file_proof_id_deliverable_proof" in str(exc_info.value)


# --- in a person's data export (DPDP) ---------------------------------------------------


def test_both_sides_of_the_deal_get_the_files_in_their_export(db, memo, uploader):
    from app.modules.auth.models.brand import Brand
    from app.modules.auth.models.creator import Creator
    from app.modules.campaigns.models import Application, Campaign
    from app.modules.deal_memo import service as deal_memos

    row = a_file(memo, uploader)
    db.add(row)
    db.flush()
    application = db.get(Application, memo.application_id)
    creator = db.get(Creator, application.creator_id)
    brand = db.get(Brand, db.get(Campaign, application.campaign_id).brand_id)

    for account_id in (creator.account_id, brand.account_id):
        sections = {s.name: s for s in deal_memos.export_for_account(db, account_id)}
        [exported] = sections["proof_files"].records
        assert exported["id"] == str(row.id)
        assert exported["sha256"] == SHA
        assert exported["position"] is None  # still pending
        # Our internal addresses stay internal.
        assert "storage_key" not in exported
        assert "clean_key" not in exported
