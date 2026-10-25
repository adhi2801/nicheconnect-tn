"""Deal notes on the record (item 17, D-128), through the API.

Either party writes, from the memo being sent until the deal ends; each
note is sealed onto the deal's record by its fingerprint, and a note
rewritten behind the database's back shows. The table's rules are in
test_deal_notes_model.py, notes written at once in test_deal_notes_concurrency.py.
"""

import hashlib

import pytest
from sqlalchemy import select, text

from app.modules.auth.models.account import Account
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.me import export_service
from app.modules.notifications.models import Notification
from tests.deal_flow import (
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import create_account
from tests.modules.deal_memo.test_memo_deliverables_api import accepted_application, draft
from tests.query_counts import queries_for


@pytest.fixture
def brand(db, clock) -> User:
    user = brand_user(db, clock)
    db.commit()
    return user


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    db.commit()
    return user


def notes_url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/notes"


def write(
    client, user: User, memo_id: str, body: str = "Can the reel go up on Saturday?"
):
    return client.post(notes_url(memo_id), json={"body": body}, headers=user.headers)


def record(client, user: User, memo_id: str) -> dict:
    response = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def sent_memo(client, brand: User, creator: User) -> str:
    memo = draft(client, brand, accepted_application(client, brand, creator))
    sent = client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=brand.headers)
    assert sent.status_code == 200, sent.text
    return str(memo["id"])


# --- writing and reading -------------------------------------------------------------


def test_both_sides_write_and_read_the_same_thread(client, db, clock, brand, creator):
    from datetime import timedelta

    memo_id = sent_memo(client, brand, creator)
    first = write(client, creator, memo_id, "Is a Saturday post fine?")
    clock.advance(timedelta(minutes=1))
    second = write(client, brand, memo_id, "Saturday is fine.")

    assert first.status_code == second.status_code == 201
    assert (first.json()["author_side"], second.json()["author_side"]) == (
        "creator",
        "brand",
    )
    for user in (brand, creator):
        page = client.get(notes_url(memo_id), headers=user.headers).json()
        assert [n["body"] for n in page["items"]] == [
            "Saturday is fine.",
            "Is a Saturday post fine?",
        ]


def test_each_note_tells_the_other_side(client, db, brand, creator):
    memo_id = sent_memo(client, brand, creator)

    write(client, brand, memo_id)

    told = db.scalars(
        select(Notification.id).where(
            Notification.account_id == creator.account_id,
            Notification.notification_type == "note_added",
        )
    ).all()
    assert len(told) == 1


def test_each_note_is_sealed_by_its_fingerprint(client, db, brand, creator):
    memo_id = sent_memo(client, brand, creator)
    body = "We agreed two reels, not three."

    note = write(client, creator, memo_id, body).json()

    [entry] = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.deal_memo_id == note["deal_memo_id"],
            DealRecordEntry.kind == "note_added",
        )
    ).all()
    assert entry.actor_role == "creator"
    assert entry.facts == {
        "note_id": note["id"],
        "note_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    checked = record(client, brand, memo_id)
    assert checked["intact"] is True
    assert checked["notes_unchanged"] is True


def test_a_deal_with_no_notes_says_so(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)

    assert record(client, brand, memo_id)["notes_unchanged"] is None


@pytest.mark.owner
def test_a_note_rewritten_behind_the_databases_back_shows(client, db, brand, creator):
    """Someone with full control of the database switches the triggers off."""
    memo_id = sent_memo(client, brand, creator)
    note = write(client, brand, memo_id, "The fee is 8,000.").json()

    db.execute(text("SET LOCAL session_replication_role = replica"))
    db.execute(
        text("UPDATE deal_note SET body = 'The fee is 5,000.' WHERE id = :n"),
        {"n": note["id"]},
    )
    db.execute(text("SET LOCAL session_replication_role = origin"))

    assert record(client, creator, memo_id)["notes_unchanged"] is False


def test_notes_run_through_an_accepted_deal(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    assert write(client, creator, memo_id).status_code == 201


def test_a_draft_takes_no_notes(client, brand, creator):
    memo = draft(client, brand, accepted_application(client, brand, creator))

    from_brand = write(client, brand, memo["id"])
    from_creator = write(client, creator, memo["id"])

    assert from_brand.status_code == 409
    assert from_brand.json()["code"] == "notes_closed"
    # The draft is the brand's alone: the creator cannot see it at all.
    assert from_creator.status_code == 404


@pytest.mark.parametrize("ending", ["decline", "cancel"])
def test_an_ended_deal_takes_no_more_notes_but_keeps_its_own(
    client, brand, creator, ending
):
    memo_id = sent_memo(client, brand, creator)
    write(client, creator, memo_id)
    actor = creator if ending == "decline" else brand
    ended = client.post(
        f"{MEMOS_URL}/{memo_id}/{ending}",
        json={"reason": "other"} if ending == "cancel" else None,
        headers=actor.headers,
    )
    assert ended.status_code == 200, ended.text

    response = write(client, brand, memo_id)

    assert response.json()["code"] == "notes_closed"
    assert len(client.get(notes_url(memo_id), headers=brand.headers).json()["items"]) == 1


# --- what is shown -------------------------------------------------------------------------


def test_a_brands_note_asking_for_money_is_flagged(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)

    note = write(
        client, brand, memo_id, "Pay a 2,000 registration fee to confirm."
    ).json()

    assert {flag["field"] for flag in note["text_flags"]} == {"body"}


def test_a_creators_note_naming_their_fee_is_not_flagged(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)

    note = write(
        client, creator, memo_id, "Pay a 2,000 registration fee to confirm."
    ).json()

    assert note["text_flags"] == []


def test_pages_have_no_gaps_or_repeats(client, clock, brand, creator):
    from datetime import timedelta

    memo_id = sent_memo(client, brand, creator)
    for n in range(5):
        write(client, brand, memo_id, f"Note {n}")
        clock.advance(timedelta(seconds=1))

    seen, cursor = [], None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = client.get(
            notes_url(memo_id), params=params, headers=creator.headers
        ).json()
        seen += [n["body"] for n in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == [f"Note {n}" for n in reversed(range(5))]


def test_a_long_thread_costs_the_same_queries_as_a_short_one(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)
    write(client, brand, memo_id)
    one = queries_for(client, notes_url(memo_id), brand.headers)
    for n in range(9):
        write(client, creator, memo_id, f"Note {n}")

    assert queries_for(client, notes_url(memo_id), brand.headers) == one


def test_both_exports_hold_the_notes(client, db, clock, brand, creator):
    memo_id = sent_memo(client, brand, creator)
    write(client, brand, memo_id, "From the brand.")

    for user in (brand, creator):
        exported = export_service.build_export(
            db, db.get_one(Account, user.account_id), clock.now
        )
        assert [n["body"] for n in exported["data"]["deal_notes"]] == ["From the brand."]


# --- who may -----------------------------------------------------------------------------


def test_notes_need_a_login(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)

    assert client.get(notes_url(memo_id)).status_code == 401
    assert client.post(notes_url(memo_id), json={"body": "Hi"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [{"body": ""}, {"body": "   "}, {"body": "x" * 1001}, {}, {"body": "Hi", "extra": 1}],
)
def test_a_bad_note_is_refused(client, brand, creator, body):
    memo_id = sent_memo(client, brand, creator)

    assert (
        client.post(notes_url(memo_id), json=body, headers=brand.headers).status_code
        == 422
    )


def test_a_stranger_sees_and_writes_nothing(client, db, clock, brand, creator):
    memo_id = sent_memo(client, brand, creator)
    write(client, brand, memo_id)
    strangers = [brand_user(db, clock), creator_user(db, clock)]
    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()

    for stranger in [*strangers, admin]:
        assert client.get(notes_url(memo_id), headers=stranger.headers).status_code == 404
        assert write(client, stranger, memo_id).status_code == 404


def test_a_retry_with_the_same_key_writes_one_note(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)
    headers = {**brand.headers, "Idempotency-Key": "note-retry-1"}

    first = client.post(notes_url(memo_id), json={"body": "Once."}, headers=headers)
    second = client.post(notes_url(memo_id), json={"body": "Once."}, headers=headers)

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert len(client.get(notes_url(memo_id), headers=brand.headers).json()["items"]) == 1
