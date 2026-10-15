"""The report queue against the IT Rules' clocks, as the admins see it (item 51)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.auth.models.creator import Creator
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import create_account
from tests.query_counts import queries_for

ADMIN = "/api/v1/admin"
QUEUE = f"{ADMIN}/reports"
CLOCKS = f"{ADMIN}/reports/clocks"


@pytest.fixture
def admin(db, clock) -> User:
    account = create_account(db, "admin")
    # Committed inside the test's outer transaction: a service that refuses
    # rolls back the shared session, and an uncommitted admin would vanish.
    db.commit()
    return User(account.id, "admin", clock)


def file_report(client, db, clock, category: str, reporter: User | None = None) -> dict:
    """A report of `category` about a new creator, by `reporter` or a new brand."""
    reporter = reporter or brand_user(db, clock)
    subject = creator_user(db, clock)
    subject_id = db.scalar(
        select(Creator.id).where(Creator.account_id == subject.account_id)
    )
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


def resolve(client, admin: User, report_id: str) -> dict:
    response = client.post(
        f"{QUEUE}/{report_id}/resolve",
        json={"outcome": "actioned", "note": "Looked at it and acted."},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- the queue -------------------------------------------------------------------------


def test_the_queue_puts_the_nearest_deadline_first(client, db, clock, admin):
    slow = file_report(client, db, clock, "non_payment")  # 7 days
    clock.advance(timedelta(hours=1))
    middle = file_report(client, db, clock, "abuse")  # 36 hours
    clock.advance(timedelta(hours=1))
    urgent = file_report(client, db, clock, "impersonation")  # 2 hours

    items = client.get(QUEUE, headers=admin.headers).json()["items"]

    assert [r["id"] for r in items] == [urgent["id"], middle["id"], slow["id"]]
    assert [r["late"] for r in items] == [False, False, False]


def test_the_queue_pages_by_deadline_without_gaps_or_repeats(client, db, clock, admin):
    filed = [
        file_report(client, db, clock, category)
        for category in (
            "non_payment",
            "abuse",
            "impersonation",
            "spam",
            "intimate_content",
        )
    ]
    by_deadline = [r["id"] for r in sorted(filed, key=lambda r: (r["due_at"], r["id"]))]

    first = client.get(QUEUE, params={"limit": 2}, headers=admin.headers).json()
    second = client.get(
        QUEUE, params={"limit": 2, "cursor": first["next_cursor"]}, headers=admin.headers
    ).json()
    third = client.get(
        QUEUE, params={"limit": 2, "cursor": second["next_cursor"]}, headers=admin.headers
    ).json()

    seen = [r["id"] for page in (first, second, third) for r in page["items"]]
    assert seen == by_deadline
    assert third["next_cursor"] is None


def test_an_open_report_turns_late_once_its_deadline_passes(client, db, clock, admin):
    filed = file_report(client, db, clock, "impersonation")

    clock.advance(timedelta(hours=2))
    at_deadline = client.get(QUEUE, headers=admin.headers).json()["items"]
    clock.advance(timedelta(seconds=1))
    after = client.get(QUEUE, headers=admin.headers).json()["items"]

    assert [(r["id"], r["late"]) for r in at_deadline] == [(filed["id"], False)]
    assert [(r["id"], r["late"]) for r in after] == [(filed["id"], True)]


def test_an_answer_after_the_deadline_is_marked_late_for_good(client, db, clock, admin):
    on_time = file_report(client, db, clock, "impersonation")
    too_late = file_report(client, db, clock, "impersonation")
    clock.advance(timedelta(hours=1))
    answered_on_time = resolve(client, admin, on_time["id"])
    clock.advance(timedelta(hours=2))
    answered_late = resolve(client, admin, too_late["id"])
    clock.advance(timedelta(days=30))

    closed = client.get(
        QUEUE, params={"status": "actioned"}, headers=admin.headers
    ).json()["items"]

    assert (answered_on_time["late"], answered_late["late"]) == (False, True)
    assert {r["id"]: r["late"] for r in closed} == {
        on_time["id"]: False,
        too_late["id"]: True,
    }


# --- the clocks ------------------------------------------------------------------------


def test_the_clocks_count_what_is_open_late_and_next(client, db, clock, admin):
    late = file_report(client, db, clock, "impersonation")
    file_report(client, db, clock, "non_payment")
    clock.advance(timedelta(hours=3))
    soonest_open = file_report(client, db, clock, "intimate_content")

    body = client.get(CLOCKS, headers=admin.headers).json()

    assert (body["open"], body["open_late"]) == (3, 1)
    assert body["next_due_at"] == late["due_at"]  # late, and still the earliest
    assert soonest_open["due_at"] > body["next_due_at"]
    assert body["as_of"] == clock.now.isoformat().replace("+00:00", "Z")
    assert body["clocks"] == [
        {"category": "impersonation", "answer_within_hours": 2},
        {"category": "intimate_content", "answer_within_hours": 2},
        {"category": "abuse", "answer_within_hours": 36},
        {"category": "fake_profile", "answer_within_hours": 36},
        {"category": "other", "answer_within_hours": 36},
        {"category": "spam", "answer_within_hours": 36},
        {"category": "non_payment", "answer_within_hours": 168},
    ]


def test_with_nothing_open_there_is_no_next_deadline(client, admin):
    body = client.get(CLOCKS, headers=admin.headers).json()

    assert (body["open"], body["open_late"], body["next_due_at"]) == (0, 0, None)


def test_the_share_answered_in_time_needs_five_answers(client, db, clock, admin):
    """Five or nothing (D-056): four answers give no share at all."""
    filed = [file_report(client, db, clock, "impersonation") for _ in range(5)]
    clock.advance(timedelta(hours=1))
    for report in filed[:3]:
        resolve(client, admin, report["id"])
    clock.advance(timedelta(hours=2))
    resolve(client, admin, filed[3]["id"])  # late

    four = client.get(CLOCKS, headers=admin.headers).json()
    resolve(client, admin, filed[4]["id"])  # late
    five = client.get(CLOCKS, headers=admin.headers).json()

    assert (four["answered"], four["answered_in_time"]) == (4, 3)
    assert four["answered_in_time_share"] is None
    assert (five["answered"], five["answered_in_time"]) == (5, 3)
    assert five["answered_in_time_share"] == pytest.approx(0.6)


def test_answers_older_than_the_window_are_left_out(client, db, clock, admin):
    old = file_report(client, db, clock, "impersonation")
    resolve(client, admin, old["id"])
    clock.advance(timedelta(days=8))
    recent = file_report(client, db, clock, "impersonation")
    resolve(client, admin, recent["id"])

    week = client.get(CLOCKS, params={"days": 7}, headers=admin.headers).json()
    month = client.get(CLOCKS, params={"days": 30}, headers=admin.headers).json()

    assert (week["days"], week["answered"]) == (7, 1)
    assert (month["days"], month["answered"]) == (30, 2)


@pytest.mark.parametrize("days", ["0", "91", "a week"])
def test_a_window_out_of_range_is_refused(client, admin, days):
    response = client.get(CLOCKS, params={"days": days}, headers=admin.headers)

    assert response.status_code == 422


def test_the_clocks_cost_the_same_queries_however_many_reports(client, db, clock, admin):
    file_report(client, db, clock, "abuse")
    few = queries_for(client, CLOCKS, admin.headers)
    for category in ("impersonation", "non_payment", "spam", "other"):
        file_report(client, db, clock, category)
    many = queries_for(client, CLOCKS, admin.headers)

    assert few == many, f"{few} queries for 1 report, {many} for 5"


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_the_clocks_are_invisible_to_everyone_but_admins(client, db, clock, role):
    user = User(create_account(db, role).id, role, clock)

    assert client.get(CLOCKS, headers=user.headers).status_code == 404
    assert client.get(CLOCKS).status_code == 404
