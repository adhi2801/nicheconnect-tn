"""Readings on the proof's files, for both sides, and the creator's mark (D-070, step 5).

The real path every time: upload, submit, clean, read with a fake reader,
then ask the API as the brand or the creator.
"""

import uuid
from collections.abc import Iterator

import pytest

from app.core import storage
from app.core.clock import india_date
from tests.deal_flow import MEMOS_URL, User, accepted_memo, brand_user, creator_user
from tests.modules.auth.test_creator_search_api import count_queries
from tests.modules.deal_memo.test_proof_reading import (
    FakeReader,
    channel,
    cleaned,
    run,
)


@pytest.fixture(autouse=True)
def empty_store() -> Iterator[None]:
    storage.memory_store().clear()
    yield
    storage.memory_store().clear()


@pytest.fixture
def deal(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    return brand, creator, accepted_memo(client, brand, creator)


def proof_id_of(client, user: User, memo_id: str) -> str:
    [proof] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=user.headers).json()
    return proof["id"]


def files_of(client, user: User, memo_id: str, proof_id: str):
    return client.get(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/files", headers=user.headers
    )


def mark(
    client, user: User, memo_id: str, proof_id: str, file_id: str, note="Reach is 31,040."
):
    return client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/files/{file_id}/reading/mark",
        json={"note": note},
        headers=user.headers,
    )


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


@pytest.fixture
def read_deal(client, db, clock, deal):
    """A deal whose one proof file has been read."""
    brand, creator, memo_id = deal
    channel(db, creator, clock)
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    run(db, clock, FakeReader(post_date=india_date(clock.now)))
    return brand, creator, memo_id, proof_id_of(client, creator, memo_id), file_id


# --- what each side sees -----------------------------------------------------------------


def test_both_sides_see_the_reading_labelled_as_read_from_a_screenshot(client, read_deal):
    brand, creator, memo_id, proof_id, _ = read_deal

    for user in (brand, creator):
        [file] = files_of(client, user, memo_id, proof_id).json()
        reading = file["reading"]
        assert reading["source"] == "read_from_screenshot"
        assert reading["status"] == "read"
        assert reading["numbers"]["views"] == 48210
        assert reading["numbers"]["impressions"] is None
        assert reading["checks"] == {
            "handle_matches": True,
            "date_within_deal": True,
            "numbers_consistent": True,
        }
        assert (reading["stated_followers"], reading["stated_average_views"]) == (
            12000,
            9000,
        )
        # 48,210 views against a stated 9,000.
        assert reading["views_against_stated"] == pytest.approx(5.36)
        assert reading["creator_note"] is None


def test_without_views_reach_is_compared_with_the_stated_average(client, db, clock, deal):
    brand, creator, memo_id = deal
    channel(db, creator, clock)
    cleaned(client, db, clock, creator, memo_id)
    run(db, clock, FakeReader(numbers={"reach": 4500}))

    [file] = files_of(client, brand, memo_id, proof_id_of(client, brand, memo_id)).json()

    assert file["reading"]["views_against_stated"] == 0.5


def test_a_file_not_read_yet_has_no_reading(client, db, clock, deal):
    brand, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id)

    [file] = files_of(client, brand, memo_id, proof_id_of(client, brand, memo_id)).json()

    assert file["reading"] is None


def test_a_failed_reading_is_shown_as_not_read_yet(client, db, clock, deal):
    brand, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id)
    run(db, clock, FakeReader(status="failed", failure="api_error", numbers=None))

    [file] = files_of(client, brand, memo_id, proof_id_of(client, brand, memo_id)).json()

    assert file["reading"] is None


def test_a_screen_with_no_numbers_says_so(client, db, clock, deal):
    brand, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id)
    run(
        db,
        clock,
        FakeReader(status="no_numbers", numbers=None, platform=None, handle=None),
    )

    [file] = files_of(client, brand, memo_id, proof_id_of(client, brand, memo_id)).json()

    assert file["reading"]["status"] == "no_numbers"
    assert set(file["reading"]["numbers"].values()) == {None}
    assert file["reading"]["views_against_stated"] is None


def test_readings_for_many_files_cost_one_query(client, db, clock, deal):
    """No query per file (CLAUDE.md section 7: no N+1)."""
    brand, creator, memo_id = deal
    cleaned(client, db, clock, creator, memo_id, count=3)
    run(db, clock, FakeReader())
    proof_id = proof_id_of(client, brand, memo_id)

    with count_queries() as statements:
        files = files_of(client, brand, memo_id, proof_id).json()

    assert [f["reading"]["status"] for f in files] == ["read"] * 3
    reading_queries = [s for s in statements if "FROM proof_file_reading" in s]
    assert len(reading_queries) == 1


# --- the creator's mark -------------------------------------------------------------------


def test_the_creator_marks_a_misread_and_the_brand_sees_it_beside_the_numbers(
    client, read_deal
):
    brand, creator, memo_id, proof_id, file_id = read_deal

    response = mark(client, creator, memo_id, proof_id, file_id)

    assert response.status_code == 200, response.text
    assert response.json()["creator_note"] == "Reach is 31,040."
    [file] = files_of(client, brand, memo_id, proof_id).json()
    assert file["reading"]["creator_note"] == "Reach is 31,040."
    assert file["reading"]["creator_marked_at"] is not None
    # Beside the reading, never instead of it.
    assert file["reading"]["numbers"]["reach"] == 31400


def test_a_reading_is_marked_once(client, read_deal):
    _, creator, memo_id, proof_id, file_id = read_deal
    mark(client, creator, memo_id, proof_id, file_id)

    response = mark(client, creator, memo_id, proof_id, file_id, note="Changed my mind.")

    assert_problem(response, 409, "proof_reading_already_marked")


def test_a_screen_with_no_numbers_cannot_be_marked(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)
    run(
        db,
        clock,
        FakeReader(status="no_numbers", numbers=None, platform=None, handle=None),
    )

    response = mark(
        client, creator, memo_id, proof_id_of(client, creator, memo_id), file_id
    )

    assert_problem(response, 409, "proof_reading_not_markable")


def test_a_file_not_read_cannot_be_marked(client, db, clock, deal):
    _, creator, memo_id = deal
    [file_id] = cleaned(client, db, clock, creator, memo_id)

    response = mark(
        client, creator, memo_id, proof_id_of(client, creator, memo_id), file_id
    )

    assert_problem(response, 404, "proof_reading_not_found")


def test_a_file_that_is_not_on_this_proof_is_not_found(client, read_deal):
    _, creator, memo_id, proof_id, _ = read_deal

    response = mark(client, creator, memo_id, proof_id, str(uuid.uuid4()))

    assert_problem(response, 404, "proof_reading_not_found")


def test_the_brand_cannot_mark_a_reading(client, read_deal):
    brand, _, memo_id, proof_id, file_id = read_deal

    response = mark(client, brand, memo_id, proof_id, file_id)

    assert response.status_code == 403


def test_another_creator_cannot_mark_it(client, db, clock, read_deal):
    _, _, memo_id, proof_id, file_id = read_deal

    response = mark(client, creator_user(db, clock), memo_id, proof_id, file_id)

    assert_problem(response, 404, "memo_not_found")


@pytest.mark.parametrize("note", ["", "abc", "x" * 501])
def test_the_note_must_say_something_and_not_too_much(client, read_deal, note):
    _, creator, memo_id, proof_id, file_id = read_deal

    response = mark(client, creator, memo_id, proof_id, file_id, note=note)

    assert response.status_code == 422


def test_without_a_token_nothing_is_marked(client, read_deal):
    _, _, memo_id, proof_id, file_id = read_deal

    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/files/{file_id}/reading/mark",
        json={"note": "Reach is wrong."},
    )

    assert response.status_code == 401
