"""Opening the files on a proof: short-lived links to the clean copy only (D-065).

Each test walks the real path: upload through the stand-in's form, submit the
proof, run the cleaner, then ask for links as the brand or the creator.
"""

import hashlib
import io
from collections.abc import Iterator
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image
from sqlalchemy import select

from app.core import storage
from app.modules.deal_memo import proof_cleaning_service as cleaning
from app.modules.deal_memo.proof_file_service import VIEW_LINK_LIFETIME
from app.modules.deal_memo.proof_models import ProofFile
from app.modules.deal_memo.proof_router import READ_LIMIT
from app.modules.deal_memo.record_models import DealRecordEntry
from tests.deal_flow import LINK, MEMOS_URL, User, accepted_memo, brand_user, creator_user
from tests.query_counts import queries_for

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
def deal(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    return brand, creator, accepted_memo(client, brand, creator)


def upload(client, clock, creator: User, memo_id: str, data: bytes) -> str:
    form = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/uploads",
        json={
            "content_type": "image/png",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        headers=creator.headers,
    ).json()
    storage.memory_store().receive(
        form["fields"]["key"], data, content_type="image/png", now=clock.now
    )
    return form["upload_id"]


def proof_with(client, clock, creator: User, memo_id: str, *files: bytes) -> str:
    """A submitted proof carrying these files, not yet cleaned."""
    ids = [upload(client, clock, creator, memo_id, data) for data in files]
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"format": "post", "file_ids": ids, "content_url": LINK},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def clean(db, clock) -> None:
    cleaning.clean_attached(db, storage.memory_store(), clock.now)


def files_of(client, user: User, memo_id: str, proof_id: str):
    return client.get(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/files", headers=user.headers
    )


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- what each side sees ----------------------------------------------------------------


def test_both_sides_get_a_five_minute_link_to_the_clean_copy(client, db, clock, deal):
    brand, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())
    clean(db, clock)
    [row] = db.query(ProofFile).filter_by(proof_id=proof_id).all()
    db.refresh(row)

    for user in (brand, creator):
        response = files_of(client, user, memo_id, proof_id)

        assert response.status_code == 200, response.text
        [file] = response.json()
        assert file["id"] == str(row.id)
        assert file["status"] == "cleaned"
        assert file["size_bytes"] == row.clean_size_bytes
        assert file["rejection_reason"] is None
        link = urlparse(file["url"])
        assert link.path.endswith(row.clean_key)
        assert parse_qs(link.query)["expires"] == ["300"]
        assert parse_qs(link.query)["filename"] == [f"{row.id}.png"]
        assert file["url_expires_at"].startswith(
            (clock.now + VIEW_LINK_LIFETIME).isoformat()[:19]
        )


def test_the_original_is_never_linked(client, db, clock, deal):
    """Its location data is the reason it is cleaned; nobody opens it, not even its owner."""
    _, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())
    incoming = db.query(ProofFile).filter_by(proof_id=proof_id).one().storage_key

    before = files_of(client, creator, memo_id, proof_id).json()
    clean(db, clock)
    after = files_of(client, creator, memo_id, proof_id).json()

    assert [(f["status"], f["url"]) for f in before] == [("attached", None)]
    assert after[0]["url"] is not None
    assert incoming not in after[0]["url"]


def test_a_file_still_being_cleaned_has_no_link_yet(client, clock, deal):
    brand, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())

    [file] = files_of(client, brand, memo_id, proof_id).json()

    assert file["status"] == "attached"
    assert file["url"] is None
    assert file["url_expires_at"] is None


def test_a_rejected_file_says_why_and_has_no_link(client, db, clock, deal):
    brand, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png(), NOT_AN_IMAGE)
    clean(db, clock)

    good, bad = files_of(client, brand, memo_id, proof_id).json()

    assert good["status"] == "cleaned" and good["url"]
    assert (bad["status"], bad["rejection_reason"], bad["url"]) == (
        "rejected",
        "not_an_image",
        None,
    )


def test_files_show_in_the_order_the_creator_chose_as_the_record_seals_them(
    client, db, clock, deal
):
    """D-067: uploaded A then B, submitted as B, A; every view says B, A."""
    brand, creator, memo_id = deal
    first = upload(client, clock, creator, memo_id, png())
    clock.advance(timedelta(seconds=1))
    second = upload(client, clock, creator, memo_id, png((1, 2, 3)))
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"format": "post", "file_ids": [second, first]},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    proof_id = response.json()["id"]
    chosen = [second, first]

    assert [f["id"] for f in response.json()["files"]] == chosen
    for user in (brand, creator):
        [listed] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=user.headers).json()
        assert [f["id"] for f in listed["files"]] == chosen
        opened = files_of(client, user, memo_id, proof_id).json()
        assert [f["id"] for f in opened] == chosen
    entry = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.deal_memo_id == memo_id,
            DealRecordEntry.kind == "proof_submitted",
        )
    ).one()
    assert [f["file_id"] for f in entry.facts["files"]] == chosen


def test_a_link_only_proof_has_no_files(client, deal):
    _, creator, memo_id = deal
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"format": "post", "content_url": LINK},
        headers=creator.headers,
    ).json()

    response = files_of(client, creator, memo_id, proof["id"])

    assert response.status_code == 200
    assert response.json() == []


def test_links_are_never_cached(client, db, clock, deal):
    brand, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())
    clean(db, clock)

    response = files_of(client, brand, memo_id, proof_id)

    assert response.headers["Cache-Control"] == "no-store"


def test_listing_proof_never_hands_out_links(client, db, clock, deal):
    """Links are made only when someone asks to open the files."""
    brand, creator, memo_id = deal
    proof_with(client, clock, creator, memo_id, png())
    clean(db, clock)

    [proof] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=brand.headers).json()

    assert "url" not in proof["files"][0]
    assert "proof-files/" not in str(proof)


# --- who may ask ------------------------------------------------------------------------


def test_another_brand_cannot_open_the_files(client, db, clock, deal):
    _, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())
    clean(db, clock)

    response = files_of(client, brand_user(db, clock), memo_id, proof_id)

    assert_problem(response, 404, "memo_not_found")


def test_another_creator_cannot_open_the_files(client, db, clock, deal):
    _, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())

    response = files_of(client, creator_user(db, clock), memo_id, proof_id)

    assert_problem(response, 404, "memo_not_found")


def test_a_proof_from_another_deal_is_not_found_under_yours(client, db, clock, deal):
    """Owning one deal opens nothing on another, even with its proof's id."""
    brand, creator, memo_id = deal
    other_brand, other_creator = brand_user(db, clock), creator_user(db, clock)
    other_memo = accepted_memo(client, other_brand, other_creator)
    their_proof = proof_with(client, clock, other_creator, other_memo, png())
    clean(db, clock)

    for user in (brand, creator):
        assert_problem(
            files_of(client, user, memo_id, their_proof), 404, "proof_not_found"
        )


def test_an_unknown_proof_is_not_found(client, deal):
    brand, _, memo_id = deal

    response = files_of(client, brand, memo_id, "00000000-0000-7000-8000-000000000000")

    assert_problem(response, 404, "proof_not_found")


def test_a_malformed_proof_id_is_refused(client, deal):
    brand, _, memo_id = deal

    assert files_of(client, brand, memo_id, "not-a-uuid").status_code == 422


def test_without_a_token_nothing_opens(client, clock, deal):
    _, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())

    response = client.get(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/files")

    assert response.status_code == 401


def test_it_is_rate_limited_per_account(client, clock, deal):
    brand, creator, memo_id = deal
    proof_id = proof_with(client, clock, creator, memo_id, png())
    for _ in range(int(READ_LIMIT.split()[0])):
        assert files_of(client, brand, memo_id, proof_id).status_code == 200

    assert files_of(client, brand, memo_id, proof_id).status_code == 429
    # Counted per person: the creator on the same deal is not affected.
    assert files_of(client, creator, memo_id, proof_id).status_code == 200


# --- when storage is not there ----------------------------------------------------------


def test_without_storage_only_opening_a_cleaned_file_answers_503(
    client, db, clock, deal, monkeypatch
):
    brand, creator, memo_id = deal
    waiting = proof_with(client, clock, creator, memo_id, png())
    monkeypatch.setattr(storage.settings, "environment", "staging")
    monkeypatch.setattr(storage.settings, "uploads_bucket", None)

    # Nothing cleaned yet, so nothing to sign and no need for the store.
    assert files_of(client, brand, memo_id, waiting).status_code == 200

    # The cleaner is handed the stand-in directly; only the endpoint asks the
    # deployment for a store.
    clean(db, clock)

    assert_problem(files_of(client, brand, memo_id, waiting), 503, "uploads_unavailable")


# --- no query per row (testing.md section 1) ----------------------------------


def test_more_files_cost_no_more_queries(client, db, clock):
    brand = brand_user(db, clock)

    def proof_of(count: int) -> tuple[str, str]:
        creator = creator_user(db, clock)
        memo_id = accepted_memo(client, brand, creator)
        colours = [(20 + 40 * index, 120, 200) for index in range(count)]
        proof_id = proof_with(
            client, clock, creator, memo_id, *(png(colour) for colour in colours)
        )
        clean(db, clock)
        return memo_id, proof_id

    one_memo, one_proof = proof_of(1)
    four_memo, four_proof = proof_of(4)
    one = queries_for(
        client, f"{MEMOS_URL}/{one_memo}/proof/{one_proof}/files", brand.headers
    )
    four = queries_for(
        client, f"{MEMOS_URL}/{four_memo}/proof/{four_proof}/files", brand.headers
    )

    assert one == four, f"{one} queries for 1 file, {four} for 4"
