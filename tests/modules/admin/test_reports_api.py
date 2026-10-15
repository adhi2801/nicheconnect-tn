"""Users reporting a creator, a brand or a campaign (D-061)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.admin.report_router import REPORT_LIMIT
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import build_campaign, create_account
from tests.query_counts import queries_for

URL = "/api/v1/reports"
NOTIFICATIONS = "/api/v1/notifications"


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def creator_id(db, user: User) -> str:
    return str(db.scalar(select(Creator.id).where(Creator.account_id == user.account_id)))


def brand_id(db, user: User) -> str:
    return str(db.scalar(select(Brand.id).where(Brand.account_id == user.account_id)))


def report(client, user: User, kind: str, subject_id, **extra):
    body = {
        "subject_kind": kind,
        "subject_id": str(subject_id),
        "category": "fake_profile",
    }
    body.update(extra)
    return client.post(URL, json=body, headers=user.headers)


def test_a_brand_reports_a_creator(client, db, brand, creator):
    response = report(
        client, brand, "creator", creator_id(db, creator), note="Stolen photos."
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "open"
    assert body["note"] == "Stolen photos."
    assert set(body) == {
        "id",
        "subject_kind",
        "subject_id",
        "category",
        "note",
        "status",
        "created_at",
        "due_at",
        "resolved_at",
    }
    assert body["resolved_at"] is None


def test_a_creator_reports_a_brand_and_a_campaign(client, db, brand, creator):
    campaign = build_campaign(db, brand_id=uuid.UUID(brand_id(db, brand)), status="open")
    db.add(campaign)
    db.flush()

    assert report(client, creator, "brand", brand_id(db, brand)).status_code == 201
    assert (
        report(client, creator, "campaign", campaign.id, category="spam").status_code
        == 201
    )


def test_reporting_the_same_thing_again_changes_nothing_and_says_so(
    client, db, brand, creator
):
    first = report(client, brand, "creator", creator_id(db, creator))

    again = report(client, brand, "creator", creator_id(db, creator), category="abuse")

    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["category"] == "fake_profile"  # unchanged


# --- acknowledged at once, with its deadline (item 51) -----------------------------------


@pytest.mark.parametrize(
    ("category", "hours"),
    [
        ("impersonation", 2),
        ("intimate_content", 2),
        ("abuse", 36),
        ("fake_profile", 36),
        ("spam", 36),
        ("other", 36),
        ("non_payment", 7 * 24),
    ],
)
def test_a_report_says_when_it_will_be_answered_by(
    client, db, clock, brand, creator, category, hours
):
    response = report(
        client, brand, "creator", creator_id(db, creator), category=category
    )

    assert response.status_code == 201, response.text
    due = clock.now + timedelta(hours=hours)
    assert response.json()["due_at"] == due.isoformat().replace("+00:00", "Z")


def test_filing_is_acknowledged_at_once_and_never_repeats_the_note(
    client, db, clock, brand, creator
):
    filed = report(
        client,
        brand,
        "creator",
        creator_id(db, creator),
        category="impersonation",
        note="This page uses my photos and my name.",
    ).json()

    told = [
        n
        for n in client.get(NOTIFICATIONS, headers=brand.headers).json()["items"]
        if n["notification_type"] == "report_received"
    ]

    assert len(told) == 1
    assert told[0]["details"] == {
        "report_id": filed["id"],
        "subject_kind": "creator",
        "category": "impersonation",
        "due_at": filed["due_at"],
    }
    assert told[0]["created_at"] == filed["created_at"]
    # The reported side is told nothing (trust-and-safety.md rule 9).
    reported_side = client.get(NOTIFICATIONS, headers=creator.headers).json()["items"]
    assert [
        n for n in reported_side if n["notification_type"].startswith("report_")
    ] == []


def test_a_second_report_of_the_same_thing_is_not_acknowledged_again(
    client, db, brand, creator
):
    first = report(client, brand, "creator", creator_id(db, creator)).json()

    again = report(client, brand, "creator", creator_id(db, creator), category="abuse")

    assert again.json()["due_at"] == first["due_at"]  # the first deadline stands
    received = [
        n
        for n in client.get(NOTIFICATIONS, headers=brand.headers).json()["items"]
        if n["notification_type"] == "report_received"
    ]
    assert len(received) == 1


def test_a_report_refused_is_never_acknowledged(client, db, brand):
    report(client, brand, "creator", uuid.uuid4())

    items = client.get(NOTIFICATIONS, headers=brand.headers).json()["items"]
    assert [n for n in items if n["notification_type"] == "report_received"] == []


def test_nobody_can_report_themselves(client, db, brand, creator):
    campaign = build_campaign(db, brand_id=uuid.UUID(brand_id(db, brand)), status="open")
    db.add(campaign)
    db.flush()

    for user, kind, subject in (
        (creator, "creator", creator_id(db, creator)),
        (brand, "brand", brand_id(db, brand)),
        (brand, "campaign", campaign.id),
    ):
        response = report(client, user, kind, subject)
        assert response.status_code == 422
        assert response.json()["code"] == "cannot_report_yourself"


def test_something_that_does_not_exist_cannot_be_reported(client, brand):
    response = report(client, brand, "creator", uuid.uuid4())

    assert response.status_code == 404
    assert response.json()["code"] == "report_subject_not_found"


def test_admins_do_not_file_reports(client, db, clock, creator):
    admin = User(create_account(db, "admin").id, "admin", clock)

    assert report(client, admin, "creator", creator_id(db, creator)).status_code == 403


def test_it_needs_a_login(client, db, creator):
    assert client.post(URL, json={}).status_code == 401


@pytest.mark.parametrize(
    "bad",
    [
        {"subject_kind": "deal_memo"},
        {"category": "boring"},
        {"note": "x" * 1001},
        {"subject_id": "not-an-id"},
        {"extra": "field"},
    ],
)
def test_bad_reports_are_refused(client, db, brand, creator, bad):
    body = {
        "subject_kind": "creator",
        "subject_id": creator_id(db, creator),
        "category": "fake_profile",
    }
    body.update(bad)

    assert client.post(URL, json=body, headers=brand.headers).status_code == 422


def test_the_limit_is_per_account_not_per_connection(client, db, clock, brand):
    """Ten an hour for one account; a second account on the same connection
    is unaffected."""
    limit = int(REPORT_LIMIT.split()[0])
    for _ in range(limit):
        target = creator_user(db, clock)
        assert report(client, brand, "creator", creator_id(db, target)).status_code == 201

    over = report(client, brand, "creator", creator_id(db, creator_user(db, clock)))
    other_brand = brand_user(db, clock)
    other = report(
        client, other_brand, "creator", creator_id(db, creator_user(db, clock))
    )

    assert over.status_code == 429
    assert other.status_code == 201


def test_a_reporter_finds_their_reports_in_their_export(client, db, brand, creator):
    filed = report(client, brand, "creator", creator_id(db, creator)).json()

    exported = client.get("/api/v1/me/export", headers=brand.headers).json()

    assert [r["id"] for r in exported["data"]["reports_made"]] == [filed["id"]]
    # The deadline we gave them is theirs to keep (item 51).
    assert exported["data"]["reports_made"][0]["due_at"] == filed["due_at"]


def test_two_identical_reports_at_once_leave_one(client, db, brand, creator, monkeypatch):
    """The partial unique index is the real guard: when the check before the
    insert misses a report filed at the same moment, the second insert fails
    and returns the first report instead."""
    from app.modules.admin import report_service

    first = report(client, brand, "creator", creator_id(db, creator)).json()
    db.commit()  # the rollback on the failed insert must not undo the first
    real = report_service._open_report
    calls = {"n": 0}

    def misses_once(*args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(report_service, "_open_report", misses_once)

    again = report(client, brand, "creator", creator_id(db, creator))

    assert again.status_code == 200
    assert again.json()["id"] == first["id"]


# --- what became of it (item 102) -------------------------------------------------------

MINE = f"{URL}/mine"


@pytest.fixture
def admin(db, clock) -> User:
    account = create_account(db, "admin")
    # Committed inside the test's outer transaction: a service that refuses
    # rolls back the shared session, and an uncommitted admin would vanish.
    db.commit()
    return User(account.id, "admin", clock)


def resolve(client, admin: User, report_id: str, outcome: str, note: str):
    response = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"outcome": outcome, "note": note},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text


def reports_of(client, db, clock, reporter: User, how_many: int) -> list[str]:
    """How many reports this person files, each about a different creator."""
    filed = []
    for _ in range(how_many):
        subject = creator_id(db, creator_user(db, clock))
        filed.append(report(client, reporter, "creator", subject).json()["id"])
        clock.advance(timedelta(minutes=1))
    return filed


def test_a_reporter_sees_what_became_of_each_report(client, db, clock, admin, brand):
    first, second = reports_of(client, db, clock, brand, 2)
    resolve(client, admin, first, "actioned", "Suspended: the photos were stolen.")

    response = client.get(MINE, headers=brand.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [r["id"] for r in items] == [second, first]  # newest first
    assert (items[0]["status"], items[0]["resolved_at"]) == ("open", None)
    assert items[1]["status"] == "actioned"
    assert items[1]["resolved_at"] is not None
    # Never the admin's note, and never who handled it.
    assert "Suspended" not in response.text
    assert str(admin.account_id) not in response.text


def test_nobody_sees_another_person_s_reports(client, db, clock, brand):
    reports_of(client, db, clock, brand, 1)
    someone_else = brand_user(db, clock)

    assert client.get(MINE, headers=someone_else.headers).json()["items"] == []


def test_resolving_tells_the_reporter_and_nobody_else(client, db, clock, admin, brand):
    reported = creator_user(db, clock)
    filed = report(client, brand, "creator", creator_id(db, reported)).json()["id"]

    resolve(client, admin, filed, "dismissed", "Looked genuine to us.")

    told = [
        n
        for n in client.get(NOTIFICATIONS, headers=brand.headers).json()["items"]
        if n["notification_type"] == "report_resolved"
    ]
    assert len(told) == 1
    assert told[0]["details"] == {
        "report_id": filed,
        "subject_kind": "creator",
        "outcome": "dismissed",
    }
    reported_side = client.get(NOTIFICATIONS, headers=reported.headers).json()["items"]
    assert [n for n in reported_side if n["notification_type"] == "report_resolved"] == []


def test_my_reports_page_without_gaps_or_repeats(client, db, clock, brand):
    filed = reports_of(client, db, clock, brand, 3)

    first = client.get(MINE, params={"limit": 2}, headers=brand.headers).json()
    second = client.get(
        MINE, params={"limit": 2, "cursor": first["next_cursor"]}, headers=brand.headers
    ).json()

    assert [r["id"] for r in first["items"] + second["items"]] == filed[::-1]
    assert second["next_cursor"] is None


def test_my_reports_cost_the_same_queries_however_many(client, db, clock):
    few, many = brand_user(db, clock), brand_user(db, clock)
    reports_of(client, db, clock, few, 1)
    reports_of(client, db, clock, many, 4)

    assert queries_for(client, MINE, few.headers) == queries_for(
        client, MINE, many.headers
    )


def test_my_reports_need_a_login(client):
    assert client.get(MINE).status_code == 401


def test_a_broken_cursor_is_refused(client, brand):
    response = client.get(MINE, params={"cursor": "not-a-cursor"}, headers=brand.headers)

    assert response.status_code == 422
