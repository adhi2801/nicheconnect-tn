"""List endpoints must not run one query per row (testing.md section 6).

Each test counts the SQL statements a request makes, then checks the count
does not grow when the number of rows grows. A regression that loads related
data row by row would fail here, not in production.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.rate_limit import limiter
from app.db.session import engine, get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.tokens import create_access_token
from tests.factories import FIXED_NOW, build_brand, build_campaign, build_creator

CAMPAIGNS_URL = "/api/v1/campaigns"
DISCOVER_URL = f"{CAMPAIGNS_URL}/discover"
PITCH = "I run a Madurai street-food page with 12,000 local followers."


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: FIXED_NOW
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


@contextmanager
def count_queries() -> Iterator[list[str]]:
    """Collect every SQL statement run inside the block."""
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def auth(account_id, role: str) -> dict[str, str]:
    token, _ = create_access_token(account_id, role, FIXED_NOW)
    return {"Authorization": f"Bearer {token}"}


def make_brand(db):
    brand = build_brand(db)
    brand.email = f"brand-{brand.account_id}@example.com"
    db.add(brand)
    db.flush()
    return brand


def make_campaigns(db, brand, count: int, status: str = "open") -> None:
    for index in range(count):
        db.add(
            build_campaign(
                db,
                brand_id=brand.id,
                title=f"Campaign {index}",
                status=status,
                created_at=FIXED_NOW - timedelta(minutes=index),
                updated_at=FIXED_NOW,
            )
        )
    db.flush()


def queries_for(client, url: str, headers: dict) -> int:
    with count_queries() as statements:
        response = client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    return len(statements)


def test_campaign_discovery_query_count_does_not_grow_with_rows(client, db):
    brand = make_brand(db)
    creator = build_creator(db)
    db.add(creator)
    db.flush()
    headers = auth(creator.account_id, "creator")
    make_campaigns(db, brand, 3)

    with_three = queries_for(client, DISCOVER_URL, headers)
    make_campaigns(db, brand, 17)
    with_twenty = queries_for(client, DISCOVER_URL, headers)

    assert with_three == with_twenty, (
        f"{with_three} queries for 3 rows, {with_twenty} for 20: the endpoint "
        "is querying per row"
    )
    # Account lookup + the list itself; a small, stable budget.
    assert with_twenty <= 4


def test_my_campaigns_query_count_does_not_grow_with_rows(client, db):
    brand = make_brand(db)
    headers = auth(brand.account_id, "brand")
    make_campaigns(db, brand, 3, status="draft")

    with_three = queries_for(client, CAMPAIGNS_URL, headers)
    make_campaigns(db, brand, 17, status="draft")
    with_twenty = queries_for(client, CAMPAIGNS_URL, headers)

    assert with_three == with_twenty
    # Account, brand profile, then the list.
    assert with_twenty <= 5


def test_application_list_query_count_does_not_grow_with_rows(client, db):
    brand = make_brand(db)
    campaign = build_campaign(db, brand_id=brand.id, status="open")
    db.add(campaign)
    db.flush()
    headers = auth(brand.account_id, "brand")
    url = f"{CAMPAIGNS_URL}/{campaign.id}/applications"

    def add_applications(count: int, start: int) -> None:
        import uuid

        from app.modules.campaigns.models import Application

        for index in range(start, start + count):
            # A handle space of its own: local sample data uses creator.NNNN.
            creator = build_creator(db, handle=f"qc{uuid.uuid4().hex[:12]}")
            db.add(creator)
            db.flush()
            db.add(
                Application(
                    campaign_id=campaign.id,
                    creator_id=creator.id,
                    pitch=PITCH,
                    status="submitted",
                    status_changed_at=FIXED_NOW,
                    created_at=FIXED_NOW - timedelta(minutes=index),
                    updated_at=FIXED_NOW,
                )
            )
        db.flush()

    add_applications(3, 0)
    with_three = queries_for(client, url, headers)
    add_applications(17, 3)
    with_twenty = queries_for(client, url, headers)

    assert with_three == with_twenty
    assert with_twenty <= 6


def test_reading_one_campaign_is_a_handful_of_queries(client, db):
    brand = make_brand(db)
    campaign = build_campaign(db, brand_id=brand.id, status="open")
    db.add(campaign)
    db.flush()

    count = queries_for(
        client, f"{CAMPAIGNS_URL}/{campaign.id}", auth(brand.account_id, "brand")
    )

    assert count <= 4
