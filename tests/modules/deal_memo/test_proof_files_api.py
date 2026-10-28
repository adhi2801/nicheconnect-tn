"""Proof with files: asking to upload, uploading, submitting (D-065).

Files go to the in-memory store, which refuses exactly what S3's signed form
tells S3 to refuse, so each test walks the whole path: describe the file,
upload it through the form, attach it to a proof.
"""

import hashlib
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import storage
from app.modules.deal_memo.proof_file_service import (
    ABANDONED_AFTER,
    MAX_PENDING_UPLOADS_PER_MEMO,
)
from app.modules.deal_memo.proof_models import MAX_PROOF_FILE_BYTES, ProofFile
from app.modules.deal_memo.record_models import DealRecordEntry
from tests.deal_flow import LINK, MEMOS_URL, User, accepted_memo, brand_user, creator_user

PNG = b"\x89PNG\r\n\x1a\n" + b"pretend these are pixels" * 10


@pytest.fixture(autouse=True)
def empty_store() -> Iterator[None]:
    storage.memory_store().clear()
    yield
    storage.memory_store().clear()


def describe(data: bytes = PNG, content_type: str = "image/png") -> dict:
    return {
        "content_type": content_type,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def start_upload(client, user: User, memo_id: str, **overrides):
    body = describe()
    body.update(overrides)
    return client.post(
        f"{MEMOS_URL}/{memo_id}/proof/uploads", json=body, headers=user.headers
    )


def uploaded(client, clock, creator: User, memo_id: str, data: bytes = PNG) -> str:
    """A finished upload: the form asked for, then the file sent through it."""
    response = start_upload(client, creator, memo_id, **describe(data))
    assert response.status_code == 201, response.text
    form = response.json()
    storage.memory_store().receive(
        form["fields"]["key"], data, content_type="image/png", now=clock.now
    )
    return form["upload_id"]


def submit(client, creator: User, memo_id: str, **body):
    body.setdefault("format", "post")
    return client.post(f"{MEMOS_URL}/{memo_id}/proof", json=body, headers=creator.headers)


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


@pytest.fixture
def deal(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    return brand, creator, accepted_memo(client, brand, creator)


# --- asking to upload -------------------------------------------------------------------


def test_the_form_pins_the_declared_file_and_expires_in_ten_minutes(client, clock, deal):
    _, creator, memo_id = deal

    response = start_upload(client, creator, memo_id)

    assert response.status_code == 201
    form = response.json()
    assert form["fields"]["Content-Type"] == "image/png"
    assert form["fields"]["x-amz-checksum-algorithm"] == "SHA256"
    assert form["fields"]["key"].startswith("proof-files/incoming/")
    assert form["expires_at"].startswith(
        (clock.now + timedelta(minutes=10)).date().isoformat()
    )


def test_the_upload_is_pending_until_a_proof_uses_it(client, db, deal):
    _, creator, memo_id = deal

    upload_id = start_upload(client, creator, memo_id).json()["upload_id"]

    row = db.get(ProofFile, upload_id)
    assert row.status == "pending"
    assert row.proof_id is None
    assert row.uploader_account_id == creator.account_id


def test_two_uploads_never_share_a_key(client, deal):
    _, creator, memo_id = deal

    keys = {
        start_upload(client, creator, memo_id).json()["fields"]["key"] for _ in range(3)
    }

    assert len(keys) == 3


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"content_type": "image/gif"}, "content_type"),
        ({"content_type": "video/mp4"}, "content_type"),
        ({"size_bytes": 0}, "size_bytes"),
        ({"size_bytes": MAX_PROOF_FILE_BYTES + 1}, "size_bytes"),
        ({"sha256": "ABC"}, "sha256"),
        ({"sha256": "A" * 64}, "sha256"),
    ],
)
def test_a_bad_description_is_refused(client, deal, overrides, field):
    _, creator, memo_id = deal

    response = start_upload(client, creator, memo_id, **overrides)

    assert response.status_code == 422
    assert field in response.text


def test_the_brand_cannot_upload_proof(client, deal):
    brand, _, memo_id = deal

    assert_problem(start_upload(client, brand, memo_id), 403, "role_not_allowed")


def test_another_creator_cannot_upload_to_your_deal(client, db, clock, deal):
    _, _, memo_id = deal

    assert_problem(
        start_upload(client, creator_user(db, clock), memo_id), 404, "memo_not_found"
    )


def test_uploads_need_an_accepted_memo(client, deal):
    brand, creator, memo_id = deal
    client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers)

    assert_problem(start_upload(client, creator, memo_id), 409, "memo_status_conflict")


def pending_rows(db, creator: User, memo_id: str, created_at) -> None:
    """A deal's worth of unfinished uploads, written directly: the hourly rate
    limit would stop the API first, and these tests are about the per-deal
    cap behind it."""
    for _ in range(MAX_PENDING_UPLOADS_PER_MEMO):
        db.add(
            ProofFile(
                deal_memo_id=memo_id,
                uploader_account_id=creator.account_id,
                storage_key=f"proof-files/incoming/cap-{uuid.uuid4().hex}",
                content_type="image/png",
                size_bytes=1,
                sha256="a" * 64,
                created_at=created_at,
                updated_at=created_at,
            )
        )
    db.flush()


def test_unfinished_uploads_are_capped_per_deal(client, db, clock, deal):
    _, creator, memo_id = deal
    pending_rows(db, creator, memo_id, created_at=clock.now - timedelta(hours=23))

    assert_problem(
        start_upload(client, creator, memo_id), 409, "too_many_pending_uploads"
    )


def test_uploads_abandoned_over_a_day_ago_no_longer_count(client, db, clock, deal):
    """Storage has deleted them by then; a deal is never shut out for good."""
    _, creator, memo_id = deal
    pending_rows(
        db,
        creator,
        memo_id,
        created_at=clock.now - ABANDONED_AFTER - timedelta(seconds=1),
    )

    assert start_upload(client, creator, memo_id).status_code == 201


def test_uploads_are_rate_limited_per_account(client, deal):
    _, creator, memo_id = deal
    statuses = [start_upload(client, creator, memo_id).status_code for _ in range(21)]

    # 20 unfinished uploads fill the deal's cap before the hourly limit of 30.
    assert statuses[:20] == [201] * 20
    assert statuses[20] == 409


# --- submitting proof with files ------------------------------------------------------


def test_a_proof_can_be_files_alone(client, db, clock, deal):
    _, creator, memo_id = deal
    first = uploaded(client, clock, creator, memo_id)
    second = uploaded(client, clock, creator, memo_id, data=PNG + b"another")

    response = submit(client, creator, memo_id, file_ids=[first, second])

    assert response.status_code == 201, response.text
    proof = response.json()
    assert proof["content_url"] is None
    assert [f["id"] for f in proof["files"]] == [first, second]
    assert {f["status"] for f in proof["files"]} == {"attached"}
    assert db.get(ProofFile, first).proof_id is not None


def test_a_proof_can_have_a_link_and_files(client, clock, deal):
    _, creator, memo_id = deal
    upload_id = uploaded(client, clock, creator, memo_id)

    response = submit(client, creator, memo_id, content_url=LINK, file_ids=[upload_id])

    assert response.status_code == 201
    assert response.json()["content_url"] == LINK
    assert len(response.json()["files"]) == 1


def test_each_files_fingerprint_is_sealed_in_the_deal_record(client, db, clock, deal):
    _, creator, memo_id = deal
    upload_id = uploaded(client, clock, creator, memo_id)

    submit(client, creator, memo_id, file_ids=[upload_id])

    entry = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.deal_memo_id == memo_id,
            DealRecordEntry.kind == "proof_submitted",
        )
    ).one()
    assert entry.facts["files"] == [
        {
            "file_id": upload_id,
            "sha256": hashlib.sha256(PNG).hexdigest(),
            "size_bytes": len(PNG),
            "content_type": "image/png",
        }
    ]
    assert entry.facts["content_url_sha256"] is None


def test_a_link_only_proof_records_exactly_what_it_did_before(client, db, deal):
    _, creator, memo_id = deal

    submit(client, creator, memo_id, content_url=LINK)

    entry = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.deal_memo_id == memo_id,
            DealRecordEntry.kind == "proof_submitted",
        )
    ).one()
    assert "files" not in entry.facts


def test_a_proof_with_neither_a_link_nor_a_file_is_refused(client, deal):
    _, creator, memo_id = deal

    response = submit(client, creator, memo_id)

    assert response.status_code == 422
    assert "content_url, file_ids, or both" in response.text


def test_the_same_file_twice_is_refused(client, clock, deal):
    _, creator, memo_id = deal
    upload_id = uploaded(client, clock, creator, memo_id)

    response = submit(client, creator, memo_id, file_ids=[upload_id, upload_id])

    assert response.status_code == 422


def test_a_file_that_never_finished_uploading_is_refused(client, db, deal):
    _, creator, memo_id = deal
    upload_id = start_upload(client, creator, memo_id).json()["upload_id"]

    assert_problem(
        submit(client, creator, memo_id, file_ids=[upload_id]),
        409,
        "proof_file_not_uploaded",
    )
    # Nothing half-done: no proof, and the file is still pending.
    assert db.get(ProofFile, upload_id).status == "pending"


def test_an_unknown_file_is_refused_like_anyone_elses(client, deal):
    _, creator, memo_id = deal

    assert_problem(
        submit(
            client, creator, memo_id, file_ids=["00000000-0000-7000-8000-000000000000"]
        ),
        422,
        "proof_file_not_found",
    )


def test_a_file_from_another_deal_cannot_be_used(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    first_deal = accepted_memo(client, brand, creator)
    second_deal = accepted_memo(client, brand_user(db, clock), creator)
    upload_id = uploaded(client, clock, creator, first_deal)

    assert_problem(
        submit(client, creator, second_deal, file_ids=[upload_id]),
        422,
        "proof_file_not_found",
    )


def test_a_file_already_on_a_proof_cannot_be_used_again(client, clock, deal):
    brand, creator, memo_id = deal
    upload_id = uploaded(client, clock, creator, memo_id)
    proof_id = submit(client, creator, memo_id, file_ids=[upload_id]).json()["id"]
    client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/request-revision",
        json={"note": "Please add the insights screenshot."},
        headers=brand.headers,
    )

    assert_problem(
        submit(client, creator, memo_id, file_ids=[upload_id]),
        422,
        "proof_file_not_found",
    )


def test_more_than_ten_files_is_refused(client, deal):
    _, creator, memo_id = deal
    ids = [f"00000000-0000-7000-8000-0000000000{n:02d}" for n in range(11)]

    assert submit(client, creator, memo_id, file_ids=ids).status_code == 422


def test_both_sides_see_the_files_on_the_proof(client, clock, deal):
    brand, creator, memo_id = deal
    upload_id = uploaded(client, clock, creator, memo_id)
    submit(client, creator, memo_id, file_ids=[upload_id])

    for user in (brand, creator):
        [proof] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=user.headers).json()
        assert [f["id"] for f in proof["files"]] == [upload_id]


# --- when storage is not there --------------------------------------------------------


def test_without_storage_uploads_answer_503_and_links_still_work(
    client, deal, monkeypatch
):
    _, creator, memo_id = deal
    monkeypatch.setattr(storage.settings, "environment", "staging")
    monkeypatch.setattr(storage.settings, "uploads_bucket", None)

    assert_problem(start_upload(client, creator, memo_id), 503, "uploads_unavailable")
    # A link-only proof never asks for the store.
    assert submit(client, creator, memo_id, content_url=LINK).status_code == 201


# --- the service's own guards, below the API's validation -------------------------------


def test_the_service_itself_refuses_a_proof_without_evidence(db, deal):
    """The API's schema catches this first; the rule must not depend on it."""
    from app.modules.deal_memo import proof_service
    from app.modules.deal_memo.exceptions import ProofNeedsEvidence
    from app.modules.deal_memo.models import DealMemo

    _, _, memo_id = deal
    memo = db.get(DealMemo, memo_id)

    with pytest.raises(ProofNeedsEvidence):
        proof_service.submit_proof(db, memo, {"format": "post"}, memo.created_at)


def test_attaching_files_without_the_store_is_a_programming_error(db, deal):
    from app.modules.deal_memo import proof_service
    from app.modules.deal_memo.models import DealMemo

    _, _, memo_id = deal
    memo = db.get(DealMemo, memo_id)

    with pytest.raises(ValueError, match="needs the store"):
        proof_service.submit_proof(
            db, memo, {"format": "post"}, memo.created_at, file_ids=[memo.id]
        )
