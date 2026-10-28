"""A brand's saved creator lists (item 66, D-129).

The rules worth proving: a list is its brand's alone; it shows only
creators the brand could find in search today, so it is never a way round
an unpublished Passport, a suspension, a takedown or a block; and its caps
hold. Every filtered list here has two or more creators (testing.md
section 2), and each one hidden is first proven shown.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.matching import creator_list_service
from app.modules.matching.creator_list_models import (
    LIST_NAME_MAX_LENGTH,
    MAX_LISTS_PER_BRAND,
    CreatorList,
    CreatorListEntry,
)
from app.modules.matching.creator_list_router import CREATORS_LIMIT, WRITE_LIMIT
from app.modules.me import export_service
from app.modules.safety.models import AccountBlock
from tests.deal_flow import User, accepted_memo, brand_user, creator_user
from tests.factories import FIXED_NOW, create_account
from tests.modules.admin.test_takedowns_api import brand_id_of, creator_id_of, withhold
from tests.query_counts import queries_for

URL = "/api/v1/creator-lists"
SEARCH_FIELDS = {
    "creator_id",
    "handle",
    "display_name",
    "city",
    "niches",
    "bio",
    "member_since",
    "channels",
    "from_price_paise",
    "currency",
    "booked_until",
}


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def findable(db, clock) -> tuple[User, str]:
    """A creator with a published Passport, and their creator id."""
    user = creator_user(db, clock)
    db.execute(
        update(Creator)
        .where(Creator.account_id == user.account_id)
        .values(passport_published_at=FIXED_NOW)
    )
    db.flush()
    return user, creator_id_of(db, user)


def start(client, brand: User, name: str = "Diwali food creators") -> dict:
    response = client.post(URL, json={"name": name}, headers=brand.headers)
    assert response.status_code == 201, response.text
    return response.json()


def save(client, brand: User, list_id: str, creator_id: str) -> None:
    response = client.put(f"{URL}/{list_id}/creators/{creator_id}", headers=brand.headers)
    assert response.status_code == 204, response.text


def on_list(client, brand: User, list_id: str, **params) -> dict:
    response = client.get(
        f"{URL}/{list_id}/creators", params=params, headers=brand.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def ids_on(client, brand: User, list_id: str) -> set[str]:
    return {row["creator_id"] for row in on_list(client, brand, list_id)["items"]}


def count_of(client, brand: User, list_id: str) -> int:
    lists = client.get(URL, headers=brand.headers).json()
    return next(row["creators"] for row in lists if row["id"] == list_id)


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- the lists ------------------------------------------------------------------------


def test_a_brand_starts_a_list_and_sees_it(client, brand):
    response = client.post(URL, json={"name": "  Diwali food  "}, headers=brand.headers)

    assert response.status_code == 201, response.text
    made = response.json()
    assert made["name"] == "Diwali food"  # trimmed
    assert made["creators"] == 0
    assert response.headers["Location"] == f"{URL}/{made['id']}/creators"
    assert client.get(URL, headers=brand.headers).json() == [made]


def test_lists_come_newest_first(client, clock, brand):
    first = start(client, brand, "First")
    clock.advance(timedelta(minutes=1))
    second = start(client, brand, "Second")

    names = [row["name"] for row in client.get(URL, headers=brand.headers).json()]

    assert names == [second["name"], first["name"]]


def test_a_name_is_used_once_per_brand_but_two_brands_may_share_it(
    client, db, clock, brand
):
    other = brand_user(db, clock)
    start(client, brand, "Madurai food")

    assert_problem(
        client.post(URL, json={"name": "Madurai food"}, headers=brand.headers),
        409,
        "creator_list_name_taken",
    )
    start(client, other, "Madurai food")


def test_a_rename_keeps_the_creators_and_refuses_a_taken_name(client, db, clock, brand):
    kept = start(client, brand, "Old name")
    start(client, brand, "Taken")
    _, creator_id = findable(db, clock)
    save(client, brand, kept["id"], creator_id)
    clock.advance(timedelta(minutes=5))

    renamed = client.patch(
        f"{URL}/{kept['id']}", json={"name": "New name"}, headers=brand.headers
    )

    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert (body["name"], body["creators"]) == ("New name", 1)
    assert body["updated_at"] > body["created_at"]
    assert_problem(
        client.patch(
            f"{URL}/{kept['id']}", json={"name": "Taken"}, headers=brand.headers
        ),
        409,
        "creator_list_name_taken",
    )
    assert ids_on(client, brand, kept["id"]) == {creator_id}


def test_the_fifty_first_list_is_refused(client, db, brand):
    db.add_all(
        CreatorList(brand_id=uuid.UUID(brand_id_of(db, brand)), name=f"List {n}")
        for n in range(MAX_LISTS_PER_BRAND - 1)
    )
    db.flush()
    start(client, brand, "The fiftieth")

    assert_problem(
        client.post(URL, json={"name": "One more"}, headers=brand.headers),
        409,
        "creator_lists_full",
    )
    assert len(client.get(URL, headers=brand.headers).json()) == MAX_LISTS_PER_BRAND


def test_removing_a_list_takes_its_creators_with_it(client, db, clock, brand):
    gone, kept = start(client, brand, "Gone"), start(client, brand, "Kept")
    _, creator_id = findable(db, clock)
    save(client, brand, gone["id"], creator_id)
    save(client, brand, kept["id"], creator_id)

    response = client.delete(f"{URL}/{gone['id']}", headers=brand.headers)

    assert response.status_code == 204
    assert_problem(
        client.get(f"{URL}/{gone['id']}/creators", headers=brand.headers),
        404,
        "creator_list_not_found",
    )
    assert [row["name"] for row in client.get(URL, headers=brand.headers).json()] == [
        "Kept"
    ]
    assert ids_on(client, brand, kept["id"]) == {creator_id}
    assert (
        db.scalar(
            select(CreatorListEntry.id).where(
                CreatorListEntry.list_id == uuid.UUID(gone["id"])
            )
        )
        is None
    )


# --- the creators on a list -------------------------------------------------------


def test_a_saved_creator_shows_what_search_shows_and_when_saved(client, db, clock, brand):
    saved = start(client, brand)
    _, creator_id = findable(db, clock)
    save(client, brand, saved["id"], creator_id)

    (row,) = on_list(client, brand, saved["id"])["items"]
    searched = next(
        item
        for item in client.get(
            "/api/v1/creators", params={"limit": 100}, headers=brand.headers
        ).json()["items"]
        if item["creator_id"] == creator_id
    )

    assert set(row) == SEARCH_FIELDS | {"saved_at", "delivery"}
    assert {key: row[key] for key in SEARCH_FIELDS} == searched
    assert row["saved_at"].startswith(clock.now.date().isoformat())
    assert count_of(client, brand, saved["id"]) == 1


def test_each_creator_carries_their_own_delivery_record(client, db, clock, brand):
    """Two creators, one with an overdue deal and one with none, so a record
    tied to the wrong creator cannot pass by luck."""
    saved = start(client, brand)
    late_user, late = findable(db, clock)
    _, fresh = findable(db, clock)
    due = (clock.now + timedelta(days=3)).date().isoformat()
    accepted_memo(client, brand, late_user, content_due_on=due)
    save(client, brand, saved["id"], late)
    save(client, brand, saved["id"], fresh)
    clock.advance(timedelta(days=5))

    rows = {
        row["creator_id"]: row for row in on_list(client, brand, saved["id"])["items"]
    }

    assert rows[late]["delivery"]["currently_overdue"] == 1
    assert rows[fresh]["delivery"]["currently_overdue"] == 0
    for creator_id in (late, fresh):
        record = client.get(
            f"/api/v1/creators/{creator_id}/delivery-record", headers=brand.headers
        )
        assert record.status_code == 200, record.text
        assert rows[creator_id]["delivery"] == record.json()


def test_creators_come_latest_saved_first(client, db, clock, brand):
    saved = start(client, brand)
    first, second = findable(db, clock)[1], findable(db, clock)[1]
    save(client, brand, saved["id"], first)
    clock.advance(timedelta(minutes=1))
    save(client, brand, saved["id"], second)

    rows = on_list(client, brand, saved["id"])["items"]

    assert [row["creator_id"] for row in rows] == [second, first]


def test_saving_twice_changes_nothing(client, db, clock, brand):
    saved = start(client, brand)
    _, creator_id = findable(db, clock)
    save(client, brand, saved["id"], creator_id)
    when = on_list(client, brand, saved["id"])["items"][0]["saved_at"]
    clock.advance(timedelta(hours=1))

    save(client, brand, saved["id"], creator_id)

    rows = on_list(client, brand, saved["id"])["items"]
    assert [(row["creator_id"], row["saved_at"]) for row in rows] == [(creator_id, when)]


def test_taking_a_creator_off_leaves_the_others(client, db, clock, brand):
    saved = start(client, brand)
    gone, kept = findable(db, clock)[1], findable(db, clock)[1]
    save(client, brand, saved["id"], gone)
    save(client, brand, saved["id"], kept)

    response = client.delete(
        f"{URL}/{saved['id']}/creators/{gone}", headers=brand.headers
    )
    again = client.delete(f"{URL}/{saved['id']}/creators/{gone}", headers=brand.headers)

    assert (response.status_code, again.status_code) == (204, 204)
    assert ids_on(client, brand, saved["id"]) == {kept}


def test_a_full_list_refuses_a_new_creator_but_not_one_already_on_it(
    client, db, clock, brand, monkeypatch
):
    monkeypatch.setattr(creator_list_service, "MAX_CREATORS_PER_LIST", 2)
    saved = start(client, brand)
    first, second, third = (findable(db, clock)[1] for _ in range(3))
    save(client, brand, saved["id"], first)
    save(client, brand, saved["id"], second)

    assert_problem(
        client.put(f"{URL}/{saved['id']}/creators/{third}", headers=brand.headers),
        409,
        "creator_list_full",
    )
    save(client, brand, saved["id"], first)
    assert ids_on(client, brand, saved["id"]) == {first, second}


def test_pages_have_no_gaps_or_repeats(client, db, clock, brand):
    saved = start(client, brand)
    expected = []
    for _ in range(5):
        creator_id = findable(db, clock)[1]
        save(client, brand, saved["id"], creator_id)
        expected.insert(0, creator_id)
        clock.advance(timedelta(seconds=1))

    seen, cursor = [], None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = on_list(client, brand, saved["id"], **params)
        seen += [row["creator_id"] for row in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == expected


def test_a_long_page_costs_the_same_queries_as_a_short_one(
    client, db, clock, brand, unlimited
):
    short, long = start(client, brand, "Short"), start(client, brand, "Long")
    # Each creator with a deal, so every page reads deals and proofs.
    for list_id in [short["id"]] + [long["id"]] * 6:
        user, creator_id = findable(db, clock)
        accepted_memo(client, brand, user)
        save(client, brand, list_id, creator_id)

    def cost(list_id: str) -> int:
        return queries_for(client, f"{URL}/{list_id}/creators", brand.headers)

    warm_up(client, brand)

    assert cost(long["id"]) == cost(short["id"])


def test_the_lists_cost_the_same_queries_however_many_there_are(client, db, clock, brand):
    other = brand_user(db, clock)
    start(client, other, "Only one")
    for n in range(5):
        made = start(client, brand, f"List {n}")
        save(client, brand, made["id"], findable(db, clock)[1])

    warm_up(client, brand)
    assert queries_for(client, URL, brand.headers) == queries_for(
        client, URL, other.headers
    )


def warm_up(client, user: User) -> None:
    """The first request after a commit opens the test's savepoint: one
    statement more that no request in production runs."""
    assert client.get(URL, headers=user.headers).status_code == 200


# --- only creators the brand could find -------------------------------------------


def unpublish(db, user: User) -> None:
    db.execute(
        update(Creator)
        .where(Creator.account_id == user.account_id)
        .values(passport_published_at=None)
    )
    db.flush()


def suspend(db, user: User) -> None:
    db.execute(
        update(Account)
        .where(Account.id == user.account_id)
        .values(suspended_at=FIXED_NOW, suspension_reason="fake_profile")
    )
    db.flush()


def blocked_by_creator(db, user: User, brand: User) -> None:
    db.add(
        AccountBlock(
            blocker_account_id=user.account_id, blocked_account_id=brand.account_id
        )
    )
    db.flush()


def blocked_by_brand(db, user: User, brand: User) -> None:
    db.add(
        AccountBlock(
            blocker_account_id=brand.account_id, blocked_account_id=user.account_id
        )
    )
    db.flush()


HIDINGS = {
    "unpublished": lambda client, db, user, brand: unpublish(db, user),
    "suspended": lambda client, db, user, brand: suspend(db, user),
    "blocked by the creator": lambda client, db, user, brand: blocked_by_creator(
        db, user, brand
    ),
    "blocked by the brand": lambda client, db, user, brand: blocked_by_brand(
        db, user, brand
    ),
    "withheld": lambda client, db, user, brand: withhold(
        client,
        User(create_account(db, "admin").id, "admin", brand.clock),
        "creator",
        creator_id_of(db, user),
    ),
}


@pytest.mark.parametrize("how", HIDINGS)
def test_a_creator_who_cannot_be_found_drops_out_of_view(client, db, clock, brand, how):
    saved = start(client, brand)
    hidden_user, hidden = findable(db, clock)
    _, kept = findable(db, clock)
    save(client, brand, saved["id"], hidden)
    save(client, brand, saved["id"], kept)
    assert ids_on(client, brand, saved["id"]) == {hidden, kept}

    HIDINGS[how](client, db, hidden_user, brand)

    assert ids_on(client, brand, saved["id"]) == {kept}
    assert count_of(client, brand, saved["id"]) == 1


def test_one_published_again_comes_back(client, db, clock, brand):
    saved = start(client, brand)
    user, creator_id = findable(db, clock)
    save(client, brand, saved["id"], creator_id)
    unpublish(db, user)
    assert ids_on(client, brand, saved["id"]) == set()

    db.execute(
        update(Creator)
        .where(Creator.account_id == user.account_id)
        .values(passport_published_at=FIXED_NOW)
    )
    db.flush()

    assert ids_on(client, brand, saved["id"]) == {creator_id}


@pytest.mark.parametrize("how", HIDINGS)
def test_a_creator_who_cannot_be_found_cannot_be_saved(client, db, clock, brand, how):
    saved = start(client, brand)
    user, creator_id = findable(db, clock)
    HIDINGS[how](client, db, user, brand)

    assert_problem(
        client.put(f"{URL}/{saved['id']}/creators/{creator_id}", headers=brand.headers),
        404,
        "creator_not_found",
    )
    assert ids_on(client, brand, saved["id"]) == set()


def test_no_such_creator_cannot_be_saved(client, brand):
    saved = start(client, brand)

    assert_problem(
        client.put(f"{URL}/{saved['id']}/creators/{uuid.uuid4()}", headers=brand.headers),
        404,
        "creator_not_found",
    )


# --- who may ---------------------------------------------------------------------


def test_another_brands_list_is_not_found(client, db, clock, brand):
    saved = start(client, brand)
    _, creator_id = findable(db, clock)
    save(client, brand, saved["id"], creator_id)
    other = brand_user(db, clock).headers
    where = f"{URL}/{saved['id']}"

    for response in (
        client.get(f"{where}/creators", headers=other),
        client.patch(where, json={"name": "Mine now"}, headers=other),
        client.delete(where, headers=other),
        client.put(f"{where}/creators/{creator_id}", headers=other),
        client.delete(f"{where}/creators/{creator_id}", headers=other),
    ):
        assert_problem(response, 404, "creator_list_not_found")
    assert client.get(URL, headers=other).json() == []
    assert ids_on(client, brand, saved["id"]) == {creator_id}


def test_creators_keep_no_lists(client, db, clock):
    creator = creator_user(db, clock)

    assert client.get(URL, headers=creator.headers).status_code == 403
    assert (
        client.post(URL, json={"name": "Mine"}, headers=creator.headers).status_code
        == 403
    )


def test_lists_need_a_login(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"name": "Mine"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * (LIST_NAME_MAX_LENGTH + 1)},
        {},
        {"name": "Fine", "extra": 1},
    ],
)
def test_a_bad_name_is_refused(client, brand, body):
    assert client.post(URL, json=body, headers=brand.headers).status_code == 422


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 1000}, {"cursor": "nope"}])
def test_bad_paging_is_refused(client, brand, params):
    saved = start(client, brand)

    response = client.get(
        f"{URL}/{saved['id']}/creators", params=params, headers=brand.headers
    )

    assert response.status_code == 422


def test_a_retry_with_the_same_key_starts_one_list(client, brand):
    headers = {**brand.headers, "Idempotency-Key": "list-retry-1"}

    first = client.post(URL, json={"name": "Once"}, headers=headers)
    second = client.post(URL, json={"name": "Once"}, headers=headers)

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert len(client.get(URL, headers=brand.headers).json()) == 1


def test_reading_a_list_is_rate_limited_as_search_is(client, brand):
    saved = start(client, brand)
    where = f"{URL}/{saved['id']}/creators"
    for _ in range(int(CREATORS_LIMIT.split()[0])):
        assert client.get(where, headers=brand.headers).status_code == 200

    assert client.get(where, headers=brand.headers).status_code == 429


def test_saving_is_rate_limited(client, db, clock, brand):
    saved = start(client, brand)
    _, creator_id = findable(db, clock)
    where = f"{URL}/{saved['id']}/creators/{creator_id}"
    for _ in range(int(WRITE_LIMIT.split()[0])):
        assert client.put(where, headers=brand.headers).status_code == 204

    assert client.put(where, headers=brand.headers).status_code == 429


# --- the export -------------------------------------------------------------------


def test_the_brands_export_holds_its_lists_and_the_creators_export_does_not(
    client, db, clock, brand
):
    saved = start(client, brand)
    user, creator_id = findable(db, clock)
    save(client, brand, saved["id"], creator_id)

    mine = export_service.build_export(
        db, db.get_one(Account, brand.account_id), clock.now
    )["data"]
    theirs = export_service.build_export(
        db, db.get_one(Account, user.account_id), clock.now
    )["data"]

    assert [row["name"] for row in mine["creator_lists"]] == [saved["name"]]
    assert [row["creator_id"] for row in mine["creator_list_entries"]] == [creator_id]
    assert theirs["creator_lists"] == theirs["creator_list_entries"] == []
