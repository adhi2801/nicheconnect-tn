"""Users reporting a creator, a brand or a campaign (D-061)."""

import uuid

import pytest
from sqlalchemy import select

from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.report_router import REPORT_LIMIT
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import build_campaign, create_account

URL = "/api/v1/reports"


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
    }


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


def test_two_identical_reports_at_once_leave_one(client, db, brand, creator, monkeypatch):
    """The partial unique index is the real guard: when the check before the
    insert misses a report filed at the same moment, the second insert fails
    and returns the first report instead."""
    from app.modules.auth import report_service

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
