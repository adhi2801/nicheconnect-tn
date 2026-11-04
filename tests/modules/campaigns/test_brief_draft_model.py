"""The brief draft table's rules, each broken with raw SQL (item 40, D-156)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import build_brand

IDEA = "'Our millet laddu box for Pongal, two reels from Madurai.'"


@pytest.fixture
def brand_id(db) -> uuid.UUID:
    brand = build_brand(db, email=f"brief-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    return brand.id


def draft(db, brand_id, columns: str, values: str) -> None:
    db.execute(
        text(
            f"INSERT INTO campaign_brief_draft (brand_id, {columns}) VALUES (:b, {values})"  # noqa: S608 - fixed SQL from the parameters below
        ),
        {"b": brand_id},
    )


@pytest.mark.parametrize(
    ("columns", "values", "rule"),
    [
        ("idea, status", f"{IDEA}, 'lost'", "ck_campaign_brief_draft_status_allowed"),
        ("idea", "'too short'", "ck_campaign_brief_draft_idea_length"),
        ("idea, status", f"{IDEA}, 'ready'", "ck_campaign_brief_draft_draft_when_ready"),
        (
            "idea, draft",
            f"{IDEA}, '{{}}'::jsonb",
            "ck_campaign_brief_draft_draft_when_ready",
        ),
        (
            "idea, status",
            f"{IDEA}, 'failed'",
            "ck_campaign_brief_draft_failure_when_failed",
        ),
        (
            "idea, failure",
            f"{IDEA}, 'refusal'",
            "ck_campaign_brief_draft_failure_when_failed",
        ),
        ("idea, attempts", f"{IDEA}, 4", "ck_campaign_brief_draft_attempts_bounded"),
    ],
)
def test_the_database_refuses_a_bad_draft(db, brand_id, columns, values, rule):
    with pytest.raises(IntegrityError, match=rule):
        draft(db, brand_id, columns, values)


def test_a_good_draft_is_accepted(db, brand_id):
    draft(db, brand_id, "idea", IDEA)
