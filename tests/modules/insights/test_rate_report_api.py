"""The quarterly city rate report through the API: public reads, admin publishing (item 84, D-200)."""

import random
import uuid

import pytest
from sqlalchemy import select

from app.modules.admin.models.admin_action import AdminAction
from app.modules.insights import rate_report_service as service
from app.modules.insights.rate_report_models import CityRateReport
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import FIXED_NOW, create_account
from tests.query_counts import queries_for
from tests.rate_reports import World

URL = "/api/v1/rate-reports"
ADMIN_URL = "/api/v1/admin/rate-reports"
REASON = {"reason": "A city's figures were built from a misspelt name."}


def a_quarter() -> str:
    return f"{random.randint(1000, 9999)}-Q{random.randint(1, 4)}"


def built(db, quarter: str | None = None, *, at=FIXED_NOW) -> CityRateReport:
    """A built, unpublished report, its body real."""
    quarter = quarter or a_quarter()
    body = service.build_body(db, quarter, at, agreed_fees=False).model_dump(mode="json")
    row = CityRateReport(
        quarter=quarter,
        method_version=1,
        body=body,
        body_sha256=service.fingerprint(body),
        built_at=at,
        created_at=at,
        updated_at=at,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def admin(db, clock) -> User:
    account = create_account(db, "admin")
    db.commit()  # survives a refused request's rollback, as in the admin tests
    return User(account.id, "admin", clock)


def published(db, admin: User, quarter: str | None = None, **kwargs) -> CityRateReport:
    row = built(db, quarter, **kwargs)
    row.published_at = FIXED_NOW
    row.published_by_account_id = admin.account_id
    db.flush()
    return row


# --- reading ----------------------------------------------------------------------------


def test_a_published_report_is_read_by_anyone(client, db, admin):
    World(db).listed()
    published(db, admin)  # another quarter's, so the right one must be chosen
    row = published(db, admin)

    response = client.get(f"{URL}/{row.quarter}")

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["quarter"] == row.quarter
    assert answer["body_sha256"] == row.body_sha256
    assert service.fingerprint(answer["body"]) == row.body_sha256
    assert answer["method_url"].endswith("docs/RATE_REPORT_METHOD.md")
    assert answer["body"]["agreed_fees_included"] is False
    assert response.headers["Cache-Control"] == "public, max-age=86400"


def test_signed_in_brands_and_creators_read_it_the_same(client, db, clock, admin):
    row = published(db, admin)
    anonymous = client.get(f"{URL}/{row.quarter}").json()

    for user in (brand_user(db, clock), creator_user(db, clock)):
        assert (
            client.get(f"{URL}/{row.quarter}", headers=user.headers).json() == anonymous
        )


def test_an_unchanged_report_answers_304(client, db, admin):
    row = published(db, admin)
    etag = client.get(f"{URL}/{row.quarter}").headers["ETag"]

    again = client.get(f"{URL}/{row.quarter}", headers={"If-None-Match": f"W/{etag}"})

    assert again.status_code == 304
    assert again.headers["ETag"] == etag


def test_an_unpublished_report_reads_as_not_built(client, db):
    row = built(db)

    unpublished = client.get(f"{URL}/{row.quarter}")
    never = client.get(f"{URL}/{a_quarter()}")

    assert unpublished.status_code == never.status_code == 404
    assert unpublished.json()["code"] == never.json()["code"] == "rate_report_not_found"


def test_a_withdrawn_report_answers_410_with_why(client, db, admin):
    row = published(db, admin)
    row.withdrawn_at = FIXED_NOW
    row.withdrawn_reason = REASON["reason"]
    db.flush()

    response = client.get(f"{URL}/{row.quarter}")

    assert response.status_code == 410
    assert response.json()["code"] == "rate_report_withdrawn"
    assert response.json()["detail"] == REASON["reason"]


@pytest.mark.parametrize("quarter", ["2026-Q5", "2026Q1", "26-Q1", "latest"])
def test_a_key_that_is_not_a_quarter_is_refused(client, quarter):
    assert client.get(f"{URL}/{quarter}").status_code == 422


def test_reads_are_rate_limited(client, db, admin):
    row = published(db, admin)
    answers = [client.get(f"{URL}/{row.quarter}").status_code for _ in range(61)]

    assert answers[:60] == [200] * 60
    assert answers[60] == 429


# --- the archive ------------------------------------------------------------------------


def archive(client, **params) -> dict:
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def mine(answer: dict, quarters: set[str]) -> list[str]:
    return [item["quarter"] for item in answer["items"] if item["quarter"] in quarters]


def test_the_archive_lists_published_reports_newest_first(client, db, admin):
    from datetime import timedelta

    older = published(db, admin, at=FIXED_NOW - timedelta(days=90))
    newer = published(db, admin, at=FIXED_NOW)
    hidden = built(db)
    withdrawn = published(db, admin, at=FIXED_NOW - timedelta(days=30))
    withdrawn.withdrawn_at = FIXED_NOW
    withdrawn.withdrawn_reason = REASON["reason"]
    db.flush()

    answer = archive(client, limit=100)
    listed = {item["quarter"]: item for item in answer["items"]}

    assert mine(
        answer, {older.quarter, newer.quarter, hidden.quarter, withdrawn.quarter}
    ) == [
        newer.quarter,
        withdrawn.quarter,
        older.quarter,
    ]
    assert listed[withdrawn.quarter]["withdrawn_at"] is not None
    assert listed[newer.quarter]["body_sha256"] == newer.body_sha256


def test_the_archive_pages_without_gaps_or_repeats(client, db, admin):
    from datetime import timedelta

    rows = [built(db, at=FIXED_NOW - timedelta(days=i)) for i in range(5)]
    for row in rows:
        if row in rows[:3]:
            row.created_at = FIXED_NOW  # ties broken by id, never skipped
        row.published_at = FIXED_NOW
        row.published_by_account_id = admin.account_id
    db.flush()
    wanted = {row.quarter for row in rows}

    seen: list[str] = []
    cursor = None
    while True:
        page = archive(client, limit=2, **({"cursor": cursor} if cursor else {}))
        seen += mine(page, wanted)
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert sorted(seen) == sorted(wanted)
    assert len(seen) == len(set(seen))


def test_a_bad_cursor_is_refused(client):
    response = client.get(URL, params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_cursor"


def test_the_archive_costs_the_same_queries_however_long(client, db, admin):
    published(db, admin)
    short = queries_for(client, URL, {}, {"limit": 100})
    for _ in range(6):
        published(db, admin)

    assert queries_for(client, URL, {}, {"limit": 100}) == short


def test_a_report_read_costs_one_query(client, db, admin):
    row = published(db, admin)

    assert queries_for(client, f"{URL}/{row.quarter}", {}) == 1


# --- publishing and withdrawing (admins only) --------------------------------------------


def publish(client, user: User, quarter: str, **headers):
    return client.post(
        f"{ADMIN_URL}/{quarter}/publish", headers={**user.headers, **headers}
    )


def withdraw(client, user: User, quarter: str, body=REASON):
    return client.post(f"{ADMIN_URL}/{quarter}/withdraw", json=body, headers=user.headers)


def test_an_admin_publishes_a_built_report_and_it_is_logged(client, db, admin):
    row = built(db)

    response = publish(client, admin, row.quarter)

    assert response.status_code == 200, response.text
    assert response.json()["published_at"] is not None
    assert client.get(f"{URL}/{row.quarter}").status_code == 200
    log = db.scalars(
        select(AdminAction).where(
            AdminAction.admin_account_id == admin.account_id,
            AdminAction.action == "publish_rate_report",
        )
    ).all()
    assert [entry.note for entry in log] == [f"Published the {row.quarter} report."]


def test_publishing_twice_is_refused(client, db, admin):
    row = built(db)
    publish(client, admin, row.quarter)

    again = publish(client, admin, row.quarter)

    assert again.status_code == 409
    assert again.json()["code"] == "rate_report_already_published"


def test_a_repeated_tap_publishes_once(client, db, admin):
    row = built(db)
    key = {"Idempotency-Key": str(uuid.uuid4())}

    first = publish(client, admin, row.quarter, **key)
    second = publish(client, admin, row.quarter, **key)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_a_quarter_not_built_cannot_be_published(client, admin):
    response = publish(client, admin, a_quarter())

    assert response.status_code == 404
    assert response.json()["code"] == "rate_report_not_built"


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_anyone_but_an_admin_is_told_it_does_not_exist(client, db, clock, role):
    row = built(db)
    user = brand_user(db, clock) if role == "brand" else creator_user(db, clock)

    for answer in (
        publish(client, user, row.quarter),
        withdraw(client, user, row.quarter),
    ):
        assert answer.status_code == 404
        assert answer.json()["code"] == "not_found"
    assert db.get(CityRateReport, row.id).published_at is None


def test_without_a_login_the_admin_routes_do_not_exist(client, db):
    row = built(db)

    for action in ("publish", "withdraw"):
        answer = client.post(f"{ADMIN_URL}/{row.quarter}/{action}", json=REASON)
        assert answer.status_code == 404


def test_an_admin_withdraws_a_published_report_with_its_reason(client, db, admin):
    row = published(db, admin)

    response = withdraw(client, admin, row.quarter)

    assert response.status_code == 200, response.text
    assert response.json()["withdrawn_reason"] == REASON["reason"]
    assert client.get(f"{URL}/{row.quarter}").status_code == 410
    note = db.scalar(
        select(AdminAction.note).where(
            AdminAction.admin_account_id == admin.account_id,
            AdminAction.action == "withdraw_rate_report",
        )
    )
    assert note == f"Withdrew the {row.quarter} report: {REASON['reason']}"


def test_withdrawals_refuse_what_makes_no_sense(client, db, admin):
    unpublished = built(db)
    done = published(db, admin)
    withdraw(client, admin, done.quarter)

    not_published = withdraw(client, admin, unpublished.quarter)
    twice = withdraw(client, admin, done.quarter)
    nothing = withdraw(client, admin, a_quarter())

    assert (not_published.status_code, not_published.json()["code"]) == (
        409,
        "rate_report_not_published",
    )
    assert (twice.status_code, twice.json()["code"]) == (
        409,
        "rate_report_already_withdrawn",
    )
    assert (nothing.status_code, nothing.json()["code"]) == (404, "rate_report_not_built")


@pytest.mark.parametrize(
    "body", [{}, {"reason": "too short"}, {"reason": "x" * 501}, {**REASON, "extra": 1}]
)
def test_a_withdrawal_needs_a_real_reason(client, db, admin, body):
    row = published(db, admin)

    assert withdraw(client, admin, row.quarter, body).status_code == 422


def test_admin_writes_are_rate_limited(client, db, admin):
    answers = [publish(client, admin, a_quarter()).status_code for _ in range(31)]

    assert answers[:30] == [404] * 30
    assert answers[30] == 429
