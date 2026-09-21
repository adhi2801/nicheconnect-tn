"""GET /api/v1/applications/me/feedback, end to end through real applications.

The local database may hold seed data, so open-campaign figures are checked
as the change caused by this test's own campaigns, and creators live in a
city no seed data uses.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import engine
from app.modules.campaigns.application_router import READ_LIMIT
from tests.deal_flow import CAMPAIGNS_URL, PITCH, User, brand_user
from tests.factories import build_creator, create_account

URL = "/api/v1/applications/me/feedback"
TEST_CITY = "Kolli Hills"


def creator_in_test_city(db, clock, niches=("fitness",)) -> User:
    creator = build_creator(
        db, handle=f"fb{uuid.uuid4().hex[:12]}", city=TEST_CITY, niches=list(niches)
    )
    db.add(creator)
    db.flush()
    return User(creator.account_id, "creator", clock)


def open_campaign(client: TestClient, brand: User, **overrides) -> str:
    body = {
        "title": "Morning run club launch",
        "description": "Two reels about our new trail shoes.",
        "campaign_type": "paid",
        "budget_min_paise": 300_000,
        "budget_max_paise": 800_000,
        "cities": [TEST_CITY],
        "niches": ["fitness"],
        "deliverables": "2 reels",
    }
    body.update(overrides)
    campaign_id = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers).json()[
        "id"
    ]
    published = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers
    )
    assert published.status_code == 200, published.text
    return str(campaign_id)


def apply(client, creator: User, campaign_id: str, quote: int | None = None) -> str:
    body: dict[str, object] = {"pitch": PITCH}
    if quote is not None:
        body["quoted_amount_paise"] = quote
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications", json=body, headers=creator.headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def reject(client, brand: User, application_id: str, reason: str) -> None:
    response = client.post(
        f"/api/v1/applications/{application_id}/reject",
        json={"reason": reason},
        headers=brand.headers,
    )
    assert response.status_code == 200, response.text


def feedback_of(client, creator: User) -> dict:
    response = client.get(URL, headers=creator.headers)
    assert response.status_code == 200, response.text
    return response.json()


@contextmanager
def count_queries() -> Iterator[list[str]]:
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


# --- what it says -------------------------------------------------------------


def test_a_creator_who_never_applied_sees_zeros_and_every_key(client, db, clock):
    body = feedback_of(client, creator_in_test_city(db, clock))

    assert body["applications"] == 0
    assert body["rejections"] == 0
    assert body["most_common_reason"] is None
    assert body["by_status"]["rejected"] == 0
    assert body["rejections_by_reason"]["budget_mismatch"] == 0
    assert body["as_of"] == "2026-09-17"


def test_the_most_common_reason_appears_from_three_rejections(client, db, clock):
    brand, creator = brand_user(db, clock), creator_in_test_city(db, clock)
    for reason in ("budget_mismatch", "budget_mismatch", "timing"):
        reject(
            client, brand, apply(client, creator, open_campaign(client, brand)), reason
        )

    body = feedback_of(client, creator)

    assert body["rejections"] == 3
    assert body["by_status"]["rejected"] == 3
    assert body["rejections_by_reason"]["budget_mismatch"] == 2
    assert body["most_common_reason"] == "budget_mismatch"


def test_quotes_above_the_stated_maximum_are_counted(client, db, clock):
    brand, creator = brand_user(db, clock), creator_in_test_city(db, clock)
    apply(client, creator, open_campaign(client, brand), quote=900_000)
    apply(client, creator, open_campaign(client, brand), quote=500_000)

    body = feedback_of(client, creator)

    assert body["quotes_compared"] == 2
    assert body["quotes_above_budget"] == 1


def test_open_campaigns_count_only_what_the_creator_can_still_apply_to(client, db, clock):
    brand, creator = brand_user(db, clock), creator_in_test_city(db, clock)
    before = feedback_of(client, creator)

    open_campaign(client, brand)  # counts: niche and city
    open_campaign(client, brand, cities=["Madurai"])  # counts: niche only
    applied = open_campaign(client, brand)
    apply(client, creator, applied)  # already applied: not counted
    open_campaign(client, brand, niches=["beauty"])  # another niche: not counted
    open_campaign(client, brand, applications_close_on="2026-09-18")
    clock.advance(timedelta(days=2))  # that one has now stopped taking applications
    after = feedback_of(client, creator)

    assert (
        after["open_campaigns_in_your_niches"] - before["open_campaigns_in_your_niches"]
        == 2
    )
    assert (
        after["open_campaigns_in_your_niches_and_city"]
        - before["open_campaigns_in_your_niches_and_city"]
        == 1
    )


def test_another_creators_rejections_never_appear(client, db, clock):
    brand, creator = brand_user(db, clock), creator_in_test_city(db, clock)
    other = creator_in_test_city(db, clock)
    reject(client, brand, apply(client, other, open_campaign(client, brand)), "timing")

    assert feedback_of(client, creator)["rejections"] == 0


def test_profile_facts_are_reported(client, db, clock):
    body = feedback_of(client, creator_in_test_city(db, clock))

    assert body["has_bio"] is True
    assert body["passport_published"] is False


# --- who may read it -----------------------------------------------------------


def test_a_brand_cannot_read_it(client, db, clock):
    response = client.get(URL, headers=brand_user(db, clock).headers)

    assert response.status_code == 403
    assert response.json()["code"] == "role_not_allowed"


def test_a_creator_without_a_profile_is_told_to_finish_it(client, db, clock):
    account = create_account(db, "creator")

    response = client.get(URL, headers=User(account.id, "creator", clock).headers)

    assert response.status_code == 409
    assert response.json()["code"] == "creator_profile_required"


def test_it_needs_a_token(client):
    response = client.get(URL)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_it_is_rate_limited(client, db, clock):
    creator = creator_in_test_city(db, clock)
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get(URL, headers=creator.headers).status_code == 200

    response = client.get(URL, headers=creator.headers)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"


# --- cost -------------------------------------------------------------------------


def test_the_number_of_queries_does_not_grow_with_applications(client, db, clock):
    brand, creator = brand_user(db, clock), creator_in_test_city(db, clock)
    apply(client, creator, open_campaign(client, brand))
    with count_queries() as one:
        feedback_of(client, creator)

    for _ in range(4):
        apply(client, creator, open_campaign(client, brand))
    with count_queries() as five:
        feedback_of(client, creator)

    assert len(five) == len(one)
