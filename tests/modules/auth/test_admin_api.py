"""The admin API (D-061): invisible to everyone else, and every act on the log."""

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.modules.auth.models.account import Account
from app.modules.auth.models.admin_action import AdminAction
from app.modules.auth.models.creator import Creator
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import FIXED_NOW, build_auth_session, create_account

ADMIN = "/api/v1/admin"
REASON = {"reason": "Caller asked about their account"}


@pytest.fixture
def admin(db, clock) -> User:
    account = create_account(db, "admin")
    # Committed (inside the test's outer transaction, still rolled back at the
    # end), because a service that refuses rolls back its session, and in a
    # test that session is the fixture's: an uncommitted admin would vanish.
    db.commit()
    return User(account.id, "admin", clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def phone_of(db, user: User) -> str:
    return db.get(Account, user.account_id).phone


def log_rows(db, action: str | None = None) -> list[AdminAction]:
    query = select(AdminAction).order_by(AdminAction.created_at, AdminAction.id)
    if action is not None:
        query = query.where(AdminAction.action == action)
    return list(db.scalars(query).all())


def file_report(client, reporter: User, subject_id, category="fake_profile") -> dict:
    response = client.post(
        "/api/v1/reports",
        json={
            "subject_kind": "creator",
            "subject_id": str(subject_id),
            "category": category,
        },
        headers=reporter.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def creator_profile_id(db, user: User) -> uuid.UUID:
    return db.scalar(select(Creator.id).where(Creator.account_id == user.account_id))


# --- invisible to everyone but admins -------------------------------------------------

ROUTES = [
    ("GET", f"{ADMIN}/accounts?phone=%2B919000000001&reason=looking"),
    ("GET", f"{ADMIN}/accounts/{uuid.uuid4()}?reason=looking"),
    ("POST", f"{ADMIN}/accounts/{uuid.uuid4()}/suspend"),
    ("POST", f"{ADMIN}/accounts/{uuid.uuid4()}/restore"),
    ("GET", f"{ADMIN}/reports"),
    ("POST", f"{ADMIN}/reports/{uuid.uuid4()}/resolve"),
    ("GET", f"{ADMIN}/actions"),
]


@pytest.mark.parametrize(("method", "url"), ROUTES)
def test_every_admin_route_is_a_plain_404_for_anyone_else(client, db, clock, method, url):
    suspended_admin = User(create_account(db, "admin").id, "admin", clock)
    db.execute(
        update(Account)
        .where(Account.id == suspended_admin.account_id)
        .values(suspended_at=FIXED_NOW, suspension_reason="abuse")
    )
    db.flush()
    callers = [
        {},
        brand_user(db, clock).headers,
        creator_user(db, clock).headers,
        suspended_admin.headers,
        {"Authorization": "Bearer not-a-token"},
    ]

    for headers in callers:
        response = client.request(method, url, headers=headers, json={})
        assert response.status_code == 404, (headers, response.text)
        assert response.json()["code"] == "not_found"


# --- looking up accounts, and the log it leaves ------------------------------------------


def test_finding_an_account_by_phone_is_logged_with_the_reason(
    client, db, admin, creator
):
    response = client.get(
        f"{ADMIN}/accounts",
        params={"phone": phone_of(db, creator), **REASON},
        headers=admin.headers,
    )

    assert response.status_code == 200, response.text
    [found] = response.json()
    assert found["id"] == str(creator.account_id)
    assert found["profile"]["kind"] == "creator"
    [entry] = log_rows(db, "view_account")
    assert entry.admin_account_id == admin.account_id
    assert entry.subject_account_id == creator.account_id
    assert entry.note == REASON["reason"]


def test_finding_by_handle_works_however_it_is_typed(client, db, admin, creator):
    handle = db.get(Creator, creator_profile_id(db, creator)).handle

    response = client.get(
        f"{ADMIN}/accounts",
        params={"handle": f"@{handle.upper()}", **REASON},
        headers=admin.headers,
    )

    assert [a["id"] for a in response.json()] == [str(creator.account_id)]


@pytest.mark.parametrize(
    "params",
    [
        {**REASON},
        {"phone": "+919000000001", "handle": "priya.eats", **REASON},
        {"phone": "+919000000001"},
        {"phone": "+919000000001", "reason": "x"},
    ],
    ids=["neither", "both", "no-reason", "reason-too-short"],
)
def test_a_lookup_needs_one_key_and_a_reason(client, admin, params):
    assert (
        client.get(f"{ADMIN}/accounts", params=params, headers=admin.headers).status_code
        == 422
    )


def test_reading_an_account_is_logged(client, db, admin, creator):
    response = client.get(
        f"{ADMIN}/accounts/{creator.account_id}", params=REASON, headers=admin.headers
    )

    assert response.status_code == 200
    assert len(log_rows(db, "view_account")) == 1


def test_an_unknown_account_is_not_found_and_nothing_is_logged(client, db, admin):
    response = client.get(
        f"{ADMIN}/accounts/{uuid.uuid4()}", params=REASON, headers=admin.headers
    )

    assert response.status_code == 404
    assert log_rows(db) == []


def field_names(value) -> set[str]:
    """Every key in a JSON document, at any depth."""
    if isinstance(value, dict):
        return set(value) | {
            name for item in value.values() for name in field_names(item)
        }
    if isinstance(value, list):
        return {name for item in value for name in field_names(item)}
    return set()


def test_an_admin_never_sees_codes_tokens_or_fees(client, db, admin, creator):
    """No field that carries any of these, at any depth.

    Field names, not the raw text: ids are hexadecimal, so "fee" turns up
    inside a random id now and then, which made the text check fail at random.
    """
    body = client.get(
        f"{ADMIN}/accounts/{creator.account_id}", params=REASON, headers=admin.headers
    ).json()

    names = field_names(body)
    assert names  # the check reads a real answer, not an empty one
    for forbidden in ("code_hash", "token", "fee", "price", "otp"):
        assert not [name for name in names if forbidden in name], forbidden


# --- suspending and restoring ----------------------------------------------------------


def suspend(client, admin: User, account_id, **body):
    payload = {"reason": "fake_profile", "note": "Stolen photos, reported twice."}
    payload.update(body)
    return client.post(
        f"{ADMIN}/accounts/{account_id}/suspend", json=payload, headers=admin.headers
    )


def test_suspending_stops_the_account_and_ends_its_sessions(client, db, admin, creator):
    session = build_auth_session(db, account_id=creator.account_id)
    db.add(session)
    db.flush()

    response = suspend(client, admin, creator.account_id)

    assert response.status_code == 200, response.text
    assert response.json()["suspension_reason"] == "fake_profile"
    db.refresh(session)
    assert session.revoked_at is not None
    refused = client.get("/api/v1/auth/me", headers=creator.headers)
    assert refused.status_code == 403
    assert refused.json()["detail"] == "Reason: fake profile."  # never the note
    [entry] = log_rows(db, "suspend")
    assert entry.note == "Stolen photos, reported twice."


def test_restoring_brings_the_account_back_and_is_logged(client, db, admin, creator):
    suspend(client, admin, creator.account_id)

    response = client.post(
        f"{ADMIN}/accounts/{creator.account_id}/restore",
        json={"note": "Identity confirmed on a call."},
        headers=admin.headers,
    )

    assert response.status_code == 200
    assert response.json()["suspended_at"] is None
    assert client.get("/api/v1/auth/me", headers=creator.headers).status_code == 200
    assert len(log_rows(db, "restore")) == 1


def test_an_admin_cannot_suspend_an_admin_or_themself(client, db, clock, admin):
    other = create_account(db, "admin")
    db.commit()  # see the admin fixture

    for target in (other.id, admin.account_id):
        response = suspend(client, admin, target)
        assert response.status_code == 409
        assert response.json()["code"] == "admin_target_not_allowed"
    assert log_rows(db, "suspend") == []


def test_suspending_twice_or_restoring_the_active_is_refused(client, db, admin, creator):
    suspend(client, admin, creator.account_id)

    twice = suspend(client, admin, creator.account_id)
    user = creator_user(db, admin.clock)
    not_suspended = client.post(
        f"{ADMIN}/accounts/{user.account_id}/restore",
        json={"note": "Nothing to lift."},
        headers=admin.headers,
    )

    assert twice.json()["code"] == "already_suspended"
    assert not_suspended.json()["code"] == "not_suspended"
    assert len(log_rows(db, "suspend")) == 1


@pytest.mark.parametrize(
    "body",
    [{"reason": "looked_funny"}, {"note": "x"}, {"note": "x" * 1001}, {"extra": 1}],
)
def test_a_suspension_needs_a_known_reason_and_a_real_note(client, admin, creator, body):
    assert suspend(client, admin, creator.account_id, **body).status_code == 422


# --- the report queue ------------------------------------------------------------------


def test_the_queue_runs_oldest_first_and_pages(client, db, clock, admin):
    reporter = brand_user(db, clock)
    filed = []
    for minutes in range(3):
        clock.now = FIXED_NOW + timedelta(minutes=minutes)
        target = creator_user(db, clock)
        filed.append(file_report(client, reporter, creator_profile_id(db, target))["id"])

    first = client.get(
        f"{ADMIN}/reports", params={"limit": 2}, headers=admin.headers
    ).json()
    second = client.get(
        f"{ADMIN}/reports",
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=admin.headers,
    ).json()

    assert [r["id"] for r in first["items"] + second["items"]] == filed
    assert second["next_cursor"] is None


def test_resolving_a_report_closes_it_and_is_logged(client, db, clock, admin, creator):
    reporter = brand_user(db, clock)
    filed = file_report(client, reporter, creator_profile_id(db, creator))

    response = client.post(
        f"{ADMIN}/reports/{filed['id']}/resolve",
        json={"outcome": "actioned", "note": "Suspended the account."},
        headers=admin.headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "actioned"
    assert client.get(f"{ADMIN}/reports", headers=admin.headers).json()["items"] == []
    [entry] = log_rows(db, "resolve_report")
    assert str(entry.report_id) == filed["id"]
    again = client.post(
        f"{ADMIN}/reports/{filed['id']}/resolve",
        json={"outcome": "dismissed", "note": "Second try."},
        headers=admin.headers,
    )
    assert again.json()["code"] == "report_already_resolved"


def test_the_account_view_counts_reports_about_it(client, db, clock, admin, creator):
    for _ in range(2):
        file_report(client, brand_user(db, clock), creator_profile_id(db, creator))

    view = client.get(
        f"{ADMIN}/accounts/{creator.account_id}", params=REASON, headers=admin.headers
    ).json()

    assert view["reports_about_open"] == 2
    assert view["reports_about_total"] == 2


# --- the log itself ------------------------------------------------------------------------


def test_the_log_answers_who_looked_at_this_account(client, db, clock, admin, creator):
    other = creator_user(db, clock)
    client.get(
        f"{ADMIN}/accounts/{creator.account_id}", params=REASON, headers=admin.headers
    )
    client.get(
        f"{ADMIN}/accounts/{other.account_id}", params=REASON, headers=admin.headers
    )

    about = client.get(
        f"{ADMIN}/actions",
        params={"account_id": str(creator.account_id)},
        headers=admin.headers,
    ).json()

    assert [e["subject_account_id"] for e in about["items"]] == [str(creator.account_id)]
    assert about["items"][0]["admin_account_id"] == str(admin.account_id)
    everything = client.get(f"{ADMIN}/actions", headers=admin.headers).json()["items"]
    assert len(everything) == 2
    assert json.dumps(everything).count("view_account") == 2


# --- the less common paths -------------------------------------------------------------


def test_a_brand_is_described_with_its_deals_and_its_campaigns_reports(
    client, db, clock, admin
):
    from app.modules.auth.models.brand import Brand
    from tests.deal_flow import accepted_memo

    brand = brand_user(db, clock)
    maker = creator_user(db, clock)
    accepted_memo(client, brand, maker)
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == brand.account_id))
    from app.modules.campaigns.models import Campaign

    campaign_id = db.scalar(select(Campaign.id).where(Campaign.brand_id == brand_id))
    client.post(
        "/api/v1/reports",
        json={
            "subject_kind": "campaign",
            "subject_id": str(campaign_id),
            "category": "spam",
        },
        headers=maker.headers,
    )

    view = client.get(
        f"{ADMIN}/accounts/{brand.account_id}", params=REASON, headers=admin.headers
    ).json()

    assert view["profile"]["kind"] == "brand"
    assert view["profile"]["handle"] is None
    assert view["deals"] == 1
    assert view["reports_about_total"] == 1  # a report on its campaign counts


def test_an_account_with_no_profile_is_described_with_nothing_to_count(client, db, admin):
    other_admin = create_account(db, "admin")
    db.commit()

    view = client.get(
        f"{ADMIN}/accounts/{other_admin.id}", params=REASON, headers=admin.headers
    ).json()

    assert view["profile"] is None
    assert view["deals"] == 0
    assert view["reports_about_total"] == 0


def test_suspending_or_resolving_something_that_does_not_exist(client, admin):
    suspended = suspend(client, admin, uuid.uuid4())
    resolved = client.post(
        f"{ADMIN}/reports/{uuid.uuid4()}/resolve",
        json={"outcome": "dismissed", "note": "Nothing there."},
        headers=admin.headers,
    )

    assert suspended.status_code == 404
    assert resolved.status_code == 404
    assert resolved.json()["code"] == "report_not_found"


def test_the_log_pages_newest_first(client, db, clock, admin):
    viewed = []
    for minutes in range(3):
        clock.now = FIXED_NOW + timedelta(minutes=minutes)
        user = creator_user(db, clock)
        client.get(
            f"{ADMIN}/accounts/{user.account_id}", params=REASON, headers=admin.headers
        )
        viewed.append(str(user.account_id))

    first = client.get(
        f"{ADMIN}/actions", params={"limit": 2}, headers=admin.headers
    ).json()
    second = client.get(
        f"{ADMIN}/actions",
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=admin.headers,
    ).json()

    subjects = [e["subject_account_id"] for e in first["items"] + second["items"]]
    assert subjects == list(reversed(viewed))
