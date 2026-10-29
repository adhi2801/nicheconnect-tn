"""Images on drafts (item 27, piece 2): uploaded, shown, cleaned, opened.

The same cleaned pipeline as proof files (D-065), through the draft's own
routes. Each test walks the real path: describe the image, upload it through
the in-memory store's form, show the draft with it, run the cleaner, and ask
for links as the brand or the creator.
"""

import hashlib
import io
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from urllib.parse import urlparse

import pytest
from PIL import Image
from sqlalchemy import select

from app.core import storage
from app.core.clock import india_date
from app.modules.auth.models.account import Account
from app.modules.deal_memo import proof_cleaning_service as cleaning
from app.modules.deal_memo.draft_models import ContentDraft
from app.modules.deal_memo.proof_models import MAX_FILES_PER_PROOF, ProofFile
from app.modules.deal_memo.proof_reading_service import read_due
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.me import export_service
from tests.deal_flow import LINK, MEMOS_URL, User, accepted_memo, brand_user, creator_user
from tests.modules.deal_memo.test_proof_reading import FakeReader
from tests.query_counts import queries_for

BODY = "Pongal at home, the Madurai way. Our new sweet box serves six. #ad"
NOT_AN_IMAGE = b"%PDF-1.7 pretending to be a png"


def png(colour: tuple[int, int, int] = (20, 120, 200)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (30, 20), colour).save(out, "PNG")
    return out.getvalue()


@pytest.fixture(autouse=True)
def empty_store() -> Iterator[None]:
    storage.memory_store().clear()
    yield
    storage.memory_store().clear()


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def memo_id(client, brand, creator) -> str:
    """An accepted deal whose terms include a draft review."""
    return accepted_memo(client, brand, creator, draft_review=True)


def drafts_url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/drafts"


def describe(data: bytes) -> dict:
    return {
        "content_type": "image/png",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def start_upload(client, user: User, memo_id: str, data: bytes | None = None):
    return client.post(
        f"{drafts_url(memo_id)}/uploads",
        json=describe(png() if data is None else data),
        headers=user.headers,
    )


def uploaded(
    client, clock, creator: User, memo_id: str, data: bytes | None = None
) -> str:
    """A finished upload: the form asked for, then the file sent through it."""
    data = png() if data is None else data
    response = start_upload(client, creator, memo_id, data)
    assert response.status_code == 201, response.text
    form = response.json()
    storage.memory_store().receive(
        form["fields"]["key"], data, content_type="image/png", now=clock.now
    )
    return form["upload_id"]


def show(client, creator: User, memo_id: str, file_ids: list[str], **fields):
    return client.post(
        drafts_url(memo_id),
        json={"body": BODY, "file_ids": file_ids, **fields},
        headers=creator.headers,
    )


def shown(client, creator: User, memo_id: str, file_ids: list[str]) -> dict:
    response = show(client, creator, memo_id, file_ids)
    assert response.status_code == 201, response.text
    return response.json()


def files_of(client, user: User, memo_id: str, draft_id: str):
    return client.get(f"{drafts_url(memo_id)}/{draft_id}/files", headers=user.headers)


def approve(client, brand: User, memo_id: str, draft_id: str) -> None:
    response = client.post(
        f"{drafts_url(memo_id)}/{draft_id}/approve", headers=brand.headers
    )
    assert response.status_code == 200, response.text


def ask_changes(client, brand: User, memo_id: str, draft_id: str) -> None:
    response = client.post(
        f"{drafts_url(memo_id)}/{draft_id}/request-changes",
        json={"note": "Add the ad label."},
        headers=brand.headers,
    )
    assert response.status_code == 200, response.text


def clean(db, clock) -> None:
    cleaning.clean_attached(db, storage.memory_store(), clock.now)


def entries(db, memo_id: str, kind: str) -> list[DealRecordEntry]:
    return list(
        db.scalars(
            select(DealRecordEntry)
            .where(DealRecordEntry.deal_memo_id == memo_id, DealRecordEntry.kind == kind)
            .order_by(DealRecordEntry.sequence)
        ).all()
    )


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- asking to upload -------------------------------------------------------------------


def test_the_creator_gets_a_form_and_a_pending_upload_on_no_draft(
    client, db, creator, memo_id
):
    response = start_upload(client, creator, memo_id)

    assert response.status_code == 201, response.text
    form = response.json()
    assert form["fields"]["key"].startswith("proof-files/incoming/")
    row = db.get_one(ProofFile, uuid.UUID(form["upload_id"]))
    assert (row.status, row.proof_id, row.draft_id) == ("pending", None, None)
    assert row.uploader_account_id == creator.account_id


def test_the_brand_cannot_upload_for_a_draft(client, brand, memo_id):
    assert_problem(start_upload(client, brand, memo_id), 403, "role_not_allowed")


def test_another_creator_cannot_upload_to_your_deal(client, db, clock, memo_id):
    assert_problem(
        start_upload(client, creator_user(db, clock), memo_id), 404, "memo_not_found"
    )


def test_no_upload_where_the_terms_have_no_draft_review(client, brand, creator):
    plain = accepted_memo(client, brand, creator)

    assert_problem(start_upload(client, creator, plain), 409, "draft_review_not_agreed")


def test_no_upload_once_a_draft_is_approved(client, db, clock, brand, creator, memo_id):
    draft = shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])
    clean(db, clock)
    approve(client, brand, memo_id, draft["id"])

    assert_problem(start_upload(client, creator, memo_id), 409, "draft_already_decided")


def test_a_bad_description_is_refused(client, creator, memo_id):
    response = client.post(
        f"{drafts_url(memo_id)}/uploads",
        json={**describe(png()), "content_type": "video/mp4"},
        headers=creator.headers,
    )

    assert response.status_code == 422
    assert "content_type" in response.text


def test_without_storage_uploads_answer_503_and_drafts_without_images_still_work(
    client, creator, memo_id, monkeypatch
):
    monkeypatch.setattr(storage.settings, "environment", "staging")
    monkeypatch.setattr(storage.settings, "uploads_bucket", None)

    assert_problem(start_upload(client, creator, memo_id), 503, "uploads_unavailable")
    assert show(client, creator, memo_id, []).status_code == 201


# --- showing a draft with images --------------------------------------------------------


def test_images_join_the_draft_in_the_order_the_creator_chose(
    client, db, clock, creator, memo_id
):
    first = uploaded(client, clock, creator, memo_id)
    second = uploaded(client, clock, creator, memo_id, png((1, 2, 3)))

    draft = shown(client, creator, memo_id, [second, first])

    assert [f["id"] for f in draft["files"]] == [second, first]
    assert {f["status"] for f in draft["files"]} == {"attached"}
    rows = {str(r.id): r for r in db.scalars(select(ProofFile)).all()}
    assert [rows[i].position for i in (second, first)] == [0, 1]
    for file_id in (first, second):
        assert str(rows[file_id].draft_id) == draft["id"]
        assert rows[file_id].proof_id is None


def test_each_images_fingerprint_is_sealed_with_the_draft(
    client, db, clock, creator, memo_id
):
    data = png()
    file_id = uploaded(client, clock, creator, memo_id, data)

    shown(client, creator, memo_id, [file_id])

    [entry] = entries(db, memo_id, "draft_submitted")
    [sealed] = entry.facts["files"]
    assert sealed["file_id"] == file_id
    assert sealed["sha256"] == hashlib.sha256(data).hexdigest()


def test_a_draft_without_images_is_sealed_exactly_as_before(client, db, creator, memo_id):
    shown(client, creator, memo_id, [])

    [entry] = entries(db, memo_id, "draft_submitted")
    assert "files" not in entry.facts


def test_both_sides_list_the_images_on_each_draft(client, clock, brand, creator, memo_id):
    file_id = uploaded(client, clock, creator, memo_id)
    draft = shown(client, creator, memo_id, [file_id])

    for user in (brand, creator):
        [listed] = client.get(drafts_url(memo_id), headers=user.headers).json()
        assert listed["id"] == draft["id"]
        assert [f["id"] for f in listed["files"]] == [file_id]


def test_an_image_that_never_finished_uploading_is_refused(client, creator, memo_id):
    unsent = start_upload(client, creator, memo_id).json()["upload_id"]

    assert_problem(
        show(client, creator, memo_id, [unsent]), 409, "proof_file_not_uploaded"
    )


def test_an_unknown_image_is_refused(client, creator, memo_id):
    assert_problem(
        show(client, creator, memo_id, [str(uuid.uuid4())]), 422, "proof_file_not_found"
    )


def test_an_image_from_another_deal_cannot_be_used(client, db, clock, brand, creator):
    first = accepted_memo(client, brand, creator, draft_review=True)
    second = accepted_memo(client, brand, creator, draft_review=True)
    elsewhere = uploaded(client, clock, creator, first)

    assert_problem(
        show(client, creator, second, [elsewhere]), 422, "proof_file_not_found"
    )


def test_a_refused_draft_leaves_nothing_behind(client, db, clock, creator, memo_id):
    """One good image and one unknown: no draft, and the good one still pending."""
    good = uploaded(client, clock, creator, memo_id)

    response = show(client, creator, memo_id, [good, str(uuid.uuid4())])

    assert_problem(response, 422, "proof_file_not_found")
    assert client.get(drafts_url(memo_id), headers=creator.headers).json() == []
    row = db.get_one(ProofFile, uuid.UUID(good))
    db.refresh(row)
    assert (row.status, row.draft_id) == ("pending", None)


def test_an_image_on_one_draft_cannot_be_reused_on_the_next(
    client, clock, brand, creator, memo_id
):
    file_id = uploaded(client, clock, creator, memo_id)
    draft = shown(client, creator, memo_id, [file_id])
    ask_changes(client, brand, memo_id, draft["id"])

    assert_problem(show(client, creator, memo_id, [file_id]), 422, "proof_file_not_found")


def test_an_image_on_a_draft_cannot_become_proof(
    client, db, clock, brand, creator, memo_id
):
    """What was approved stays with the draft; proof is uploaded as proof."""
    file_id = uploaded(client, clock, creator, memo_id)
    draft = shown(client, creator, memo_id, [file_id])
    clean(db, clock)
    approve(client, brand, memo_id, draft["id"])

    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"format": "reel", "content_url": LINK, "file_ids": [file_id]},
        headers=creator.headers,
    )

    assert_problem(response, 422, "proof_file_not_found")


@pytest.mark.parametrize("count", [MAX_FILES_PER_PROOF + 1])
def test_more_than_ten_images_is_refused(client, creator, memo_id, count):
    response = show(client, creator, memo_id, [str(uuid.uuid4()) for _ in range(count)])

    assert response.status_code == 422
    assert "file_ids" in response.text


def test_the_same_image_twice_is_refused(client, clock, creator, memo_id):
    file_id = uploaded(client, clock, creator, memo_id)

    response = show(client, creator, memo_id, [file_id, file_id])

    assert response.status_code == 422
    assert "each file may appear once" in response.text


# --- cleaning, opening, reading ---------------------------------------------------------


def test_cleaning_seals_the_draft_not_a_proof(client, db, clock, creator, memo_id):
    file_id = uploaded(client, clock, creator, memo_id)
    draft = shown(client, creator, memo_id, [file_id])

    clean(db, clock)

    [entry] = entries(db, memo_id, "draft_file_cleaned")
    assert entry.facts["file_id"] == file_id
    assert entry.facts["draft_id"] == draft["id"]
    assert "proof_id" not in entry.facts
    assert entries(db, memo_id, "proof_file_cleaned") == []


def test_both_sides_open_the_clean_copy_never_the_original(
    client, db, clock, brand, creator, memo_id
):
    file_id = uploaded(client, clock, creator, memo_id)
    draft = shown(client, creator, memo_id, [file_id])
    row = db.get_one(ProofFile, uuid.UUID(file_id))
    incoming = row.storage_key

    before = files_of(client, brand, memo_id, draft["id"])
    clean(db, clock)
    db.refresh(row)

    assert [(f["status"], f["url"]) for f in before.json()] == [("attached", None)]
    for user in (brand, creator):
        response = files_of(client, user, memo_id, draft["id"])
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        [file] = response.json()
        assert file["status"] == "cleaned"
        assert file["size_bytes"] == row.clean_size_bytes
        assert urlparse(file["url"]).path.endswith(row.clean_key)
        assert incoming not in file["url"]


def test_a_rejected_image_says_why_and_has_no_link(
    client, db, clock, brand, creator, memo_id
):
    good = uploaded(client, clock, creator, memo_id)
    bad = uploaded(client, clock, creator, memo_id, NOT_AN_IMAGE)
    draft = shown(client, creator, memo_id, [good, bad])
    clean(db, clock)

    opened = files_of(client, brand, memo_id, draft["id"]).json()

    assert opened[0]["status"] == "cleaned" and opened[0]["url"]
    assert (opened[1]["status"], opened[1]["rejection_reason"], opened[1]["url"]) == (
        "rejected",
        "not_an_image",
        None,
    )


def test_a_stranger_cannot_open_a_drafts_images(client, db, clock, creator, memo_id):
    draft = shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])

    for stranger in (brand_user(db, clock), creator_user(db, clock)):
        assert_problem(
            files_of(client, stranger, memo_id, draft["id"]), 404, "memo_not_found"
        )


def test_an_unknown_draft_has_no_images_to_open(client, creator, memo_id):
    assert_problem(
        files_of(client, creator, memo_id, str(uuid.uuid4())), 404, "draft_not_found"
    )


def test_a_draft_without_images_opens_to_an_empty_list(client, creator, memo_id):
    draft = shown(client, creator, memo_id, [])

    response = files_of(client, creator, memo_id, draft["id"])

    assert response.status_code == 200
    assert response.json() == []


def test_a_drafts_images_are_never_read_for_results(client, db, clock, creator, memo_id):
    """They show what will be posted, not what a post achieved."""
    shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])
    clean(db, clock)
    reader = FakeReader()

    result = read_due(db, storage.memory_store(), reader, clock.now)

    assert result.read == 0
    assert reader.images == []


# --- the export, the cost of a list -----------------------------------------------------


def test_the_export_names_each_images_draft(client, db, clock, creator, memo_id):
    file_id = uploaded(client, clock, creator, memo_id)
    draft = shown(client, creator, memo_id, [file_id])

    account = db.get_one(Account, creator.account_id)
    [section] = [
        s
        for s in export_service.collect_sections(db, account, clock.now)
        if s.table == "proof_file"
    ]
    [exported] = [r for r in section.records if r["id"] == file_id]
    assert exported["draft_id"] == draft["id"]
    assert exported["proof_id"] is None


def test_listing_drafts_costs_the_same_however_many_carry_images(
    client, clock, brand, creator, memo_id
):
    def one_more_draft() -> None:
        ids = [uploaded(client, clock, creator, memo_id) for _ in range(2)]
        ask_changes(client, brand, memo_id, shown(client, creator, memo_id, ids)["id"])

    one_more_draft()
    one = queries_for(client, drafts_url(memo_id), brand.headers)
    one_more_draft()
    one_more_draft()
    three = queries_for(client, drafts_url(memo_id), brand.headers)

    assert three == one


# --- what each upload is for (Adhi, after the review, 29 October 2026) ------------------


def proof_upload(client, clock, creator: User, memo_id: str) -> str:
    data = png((9, 9, 9))
    form = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/uploads",
        json=describe(data),
        headers=creator.headers,
    ).json()
    storage.memory_store().receive(
        form["fields"]["key"], data, content_type="image/png", now=clock.now
    )
    return form["upload_id"]


def test_a_proof_upload_never_joins_a_draft(client, clock, creator, memo_id):
    assert_problem(
        show(client, creator, memo_id, [proof_upload(client, clock, creator, memo_id)]),
        422,
        "proof_file_not_found",
    )


def test_an_unused_draft_upload_never_becomes_proof(
    client, db, clock, brand, creator, memo_id
):
    spare = uploaded(client, clock, creator, memo_id)
    draft = shown(client, creator, memo_id, [])
    approve(client, brand, memo_id, draft["id"])

    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"format": "reel", "content_url": LINK, "file_ids": [spare]},
        headers=creator.headers,
    )

    assert_problem(response, 422, "proof_file_not_found")


def test_an_upload_is_marked_with_its_purpose(client, db, clock, creator, memo_id):
    for_draft = uploaded(client, clock, creator, memo_id)
    for_proof = proof_upload(client, clock, creator, memo_id)

    assert db.get_one(ProofFile, uuid.UUID(for_draft)).purpose == "draft"
    assert db.get_one(ProofFile, uuid.UUID(for_proof)).purpose == "proof"


def test_proof_and_draft_uploads_share_one_hourly_limit(client, brand, creator):
    """30 an hour per person in all, across both routes, not 30 on each."""
    reviewed = accepted_memo(client, brand, creator, draft_review=True)
    plain = accepted_memo(client, brand, creator)
    statuses = [start_upload(client, creator, reviewed).status_code for _ in range(15)]
    statuses += [
        client.post(
            f"{MEMOS_URL}/{plain}/proof/uploads",
            json=describe(png()),
            headers=creator.headers,
        ).status_code
        for _ in range(15)
    ]

    assert statuses == [201] * 30
    assert_problem(start_upload(client, creator, reviewed), 429, "rate_limited")


# --- nothing approved before the brand can open it --------------------------------------


def test_the_brand_cannot_approve_while_images_are_being_cleaned(
    client, db, clock, brand, creator, memo_id
):
    draft = shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])

    response = client.post(
        f"{drafts_url(memo_id)}/{draft['id']}/approve", headers=brand.headers
    )

    assert_problem(response, 409, "draft_images_not_ready")
    assert draft["images_ready_at"] is None
    assert draft["answer_by"] is None
    clean(db, clock)
    approve(client, brand, memo_id, draft["id"])


def test_the_brand_may_still_ask_for_changes_while_images_are_cleaned(
    client, clock, brand, creator, memo_id
):
    draft = shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])

    ask_changes(client, brand, memo_id, draft["id"])


def test_the_clock_never_approves_images_nobody_could_open(
    client, db, clock, brand, creator, memo_id
):
    """A stalled cleaner: weeks pass, and the draft still waits for the brand."""
    shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])
    clock.advance(timedelta(days=30))

    [listed] = client.get(drafts_url(memo_id), headers=brand.headers).json()

    assert (listed["status"], listed["auto_approved"]) == ("submitted", False)
    assert entries(db, memo_id, "draft_auto_approved") == []


def test_the_brands_two_days_count_from_when_it_could_open_the_images(
    client, db, clock, brand, creator, memo_id
):
    shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])
    clock.advance(timedelta(days=30))
    clean(db, clock)

    [listed] = client.get(drafts_url(memo_id), headers=brand.headers).json()

    assert listed["status"] == "submitted"
    assert listed["images_ready_at"].startswith(clock.now.isoformat()[:19])
    ready_day = date.fromisoformat(listed["answer_by"]) - timedelta(days=2)
    assert ready_day == india_date(clock.now)


def test_a_rejected_image_still_lets_the_brand_answer(
    client, db, clock, brand, creator, memo_id
):
    draft = shown(
        client,
        creator,
        memo_id,
        [uploaded(client, clock, creator, memo_id, NOT_AN_IMAGE)],
    )
    clean(db, clock)

    approve(client, brand, memo_id, draft["id"])


def test_a_draft_is_ready_only_once_its_last_image_is_cleaned(
    client, db, clock, creator, memo_id
):
    first = uploaded(client, clock, creator, memo_id)
    second = uploaded(client, clock, creator, memo_id, png((5, 6, 7)))
    draft = shown(client, creator, memo_id, [first, second])

    cleaning.clean_one(db, storage.memory_store(), uuid.UUID(first), clock.now)
    after_one = db.get_one(ContentDraft, uuid.UUID(draft["id"]))
    db.refresh(after_one)
    assert after_one.images_ready_at is None
    clock.advance(timedelta(minutes=1))
    cleaning.clean_one(db, storage.memory_store(), uuid.UUID(second), clock.now)
    db.refresh(after_one)
    assert after_one.images_ready_at == clock.now


def test_a_draft_without_images_is_ready_when_shown(client, creator, memo_id):
    draft = shown(client, creator, memo_id, [])

    assert draft["images_ready_at"] == draft["created_at"]
    assert draft["answer_by"] is not None


# --- the review's other gaps ------------------------------------------------------------


def test_no_upload_on_a_cancelled_deal(client, brand, creator, memo_id):
    client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers)

    assert_problem(start_upload(client, creator, memo_id), 409, "memo_status_conflict")


def test_draft_uploads_count_toward_the_deals_cap_with_proof(
    client, db, creator, clock, memo_id
):
    from app.modules.deal_memo.proof_file_service import MAX_PENDING_UPLOADS_PER_MEMO

    for _ in range(MAX_PENDING_UPLOADS_PER_MEMO):
        db.add(
            ProofFile(
                deal_memo_id=memo_id,
                uploader_account_id=creator.account_id,
                storage_key=f"proof-files/incoming/cap-{uuid.uuid4().hex}",
                content_type="image/png",
                size_bytes=1,
                sha256="a" * 64,
                created_at=clock.now,
                updated_at=clock.now,
            )
        )
    db.flush()

    assert_problem(
        start_upload(client, creator, memo_id), 409, "too_many_pending_uploads"
    )


def test_showing_images_without_storage_answers_503(
    client, clock, creator, memo_id, monkeypatch
):
    file_id = uploaded(client, clock, creator, memo_id)
    monkeypatch.setattr(storage.settings, "environment", "staging")
    monkeypatch.setattr(storage.settings, "uploads_bucket", None)

    assert_problem(show(client, creator, memo_id, [file_id]), 503, "uploads_unavailable")


def test_exactly_ten_images_are_accepted(client, clock, creator, memo_id, unlimited):
    ids = [
        uploaded(client, clock, creator, memo_id, png((i, i, i)))
        for i in range(MAX_FILES_PER_PROOF)
    ]

    draft = shown(client, creator, memo_id, ids)

    assert [f["id"] for f in draft["files"]] == ids


def test_a_draft_from_another_deal_between_the_same_two_is_not_found(
    client, clock, brand, creator, memo_id
):
    other = accepted_memo(client, brand, creator, draft_review=True)
    elsewhere = shown(client, creator, other, [uploaded(client, clock, creator, other)])

    for user in (brand, creator):
        assert_problem(
            files_of(client, user, memo_id, elsewhere["id"]), 404, "draft_not_found"
        )


def test_opening_images_is_rate_limited(client, creator, memo_id):
    from app.modules.deal_memo.draft_router import READ_LIMIT

    draft = shown(client, creator, memo_id, [])
    per_minute = int(READ_LIMIT.split()[0])
    statuses = [
        files_of(client, creator, memo_id, draft["id"]).status_code
        for _ in range(per_minute + 1)
    ]

    assert statuses[:per_minute] == [200] * per_minute
    assert statuses[-1] == 429


def test_both_sides_still_open_images_after_the_deal_is_cancelled(
    client, db, clock, brand, creator, memo_id
):
    draft = shown(client, creator, memo_id, [uploaded(client, clock, creator, memo_id)])
    clean(db, clock)
    client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers)

    for user in (brand, creator):
        [file] = files_of(client, user, memo_id, draft["id"]).json()
        assert file["url"]


def test_the_listed_size_is_the_cleaned_copys_once_cleaned(
    client, db, clock, creator, memo_id
):
    file_id = uploaded(client, clock, creator, memo_id)
    shown(client, creator, memo_id, [file_id])
    clean(db, clock)
    row = db.get_one(ProofFile, uuid.UUID(file_id))
    db.refresh(row)

    [listed] = client.get(drafts_url(memo_id), headers=creator.headers).json()

    assert listed["files"][0]["size_bytes"] == row.clean_size_bytes
