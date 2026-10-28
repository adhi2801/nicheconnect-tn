"""The deliverables tables' rules, and the memo's terms version, each broken with raw SQL (D-127).

The database holds them, so no bug or hand-written query can store a line
that is not a real platform and format, a count of nothing, two lines in
one place, or a terms version the record cannot read (database.md section 3).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import build_brand, build_campaign, build_creator


@pytest.fixture
def parents(db) -> dict[str, uuid.UUID]:
    """A campaign, and a memo on an application to it."""
    brand = build_brand(db, email=f"dl-{uuid.uuid4().hex[:10]}@example.com")
    creator = build_creator(db, handle=f"dl{uuid.uuid4().hex[:12]}")
    db.add_all([brand, creator])
    db.flush()
    campaign = build_campaign(db, status="open", brand_id=brand.id)
    db.add(campaign)
    db.flush()
    application = db.execute(
        text(
            "INSERT INTO application (campaign_id, creator_id, pitch, status, status_changed_at)"
            " VALUES (:c, :k, 'A Madurai food page, for a model test.', 'accepted', now())"
            " RETURNING id"
        ),
        {"c": campaign.id, "k": creator.id},
    ).scalar_one()
    memo = db.execute(
        text(
            "INSERT INTO deal_memo (application_id, deliverables, fee_amount_paise, status)"
            " VALUES (:a, '2 reels', 500000, 'draft') RETURNING id"
        ),
        {"a": application},
    ).scalar_one()
    return {"campaign_deliverable": campaign.id, "memo_deliverable": memo}


PARENT_COLUMN = {
    "campaign_deliverable": "campaign_id",
    "memo_deliverable": "deal_memo_id",
}


def insert(db, table: str, parent: uuid.UUID, **overrides) -> None:
    values = {
        "position": "0",
        "platform": "'instagram'",
        "format": "'reel'",
        "quantity": "2",
        "note": "NULL",
    }
    values.update(overrides)
    db.execute(
        text(
            f"INSERT INTO {table} ({PARENT_COLUMN[table]}, {', '.join(values)})"  # noqa: S608 - fixed SQL from the parameters below
            f" VALUES (:p, {', '.join(values.values())})"
        ),
        {"p": parent},
    )


@pytest.mark.parametrize("table", list(PARENT_COLUMN))
@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"platform": "'tiktok'"}, "platform_allowed"),
        ({"format": "'carousel'"}, "format_allowed"),
        ({"quantity": "0"}, "quantity_range"),
        ({"quantity": "21"}, "quantity_range"),
        ({"position": "-1"}, "position_range"),
        ({"position": "10"}, "position_range"),
        ({"note": "'  '"}, "note_length"),
        ({"note": "repeat('x', 201)"}, "note_length"),
    ],
)
def test_the_database_refuses_a_bad_line(db, parents, table, overrides, rule):
    with pytest.raises(IntegrityError, match=f"ck_{table}_{rule}"):
        insert(db, table, parents[table], **overrides)


@pytest.mark.parametrize("table", list(PARENT_COLUMN))
def test_two_lines_never_share_a_place(db, parents, table):
    insert(db, table, parents[table])

    with pytest.raises(IntegrityError, match=f"uq_{table}_place"):
        insert(db, table, parents[table], format="'story'")


def test_a_memo_with_a_list_cannot_be_deleted(db, parents):
    insert(db, "memo_deliverable", parents["memo_deliverable"])

    with pytest.raises(
        IntegrityError, match="fk_memo_deliverable_deal_memo_id_deal_memo"
    ):
        db.execute(
            text("DELETE FROM deal_memo WHERE id = :m"),
            {"m": parents["memo_deliverable"]},
        )


@pytest.mark.parametrize("version", ["0", "4"])
def test_a_terms_version_the_record_cannot_read_is_refused(db, parents, version):
    with pytest.raises(IntegrityError, match="ck_deal_memo_terms_version_known"):
        db.execute(
            text(f"UPDATE deal_memo SET terms_version = {version} WHERE id = :m"),  # noqa: S608 - a fixed number from the parameters above
            {"m": parents["memo_deliverable"]},
        )


def test_a_new_memo_is_terms_version_3(db, parents):
    """Version 3 adds the draft review to the seal (item 27, D-140)."""
    version = db.execute(
        text("SELECT terms_version FROM deal_memo WHERE id = :m"),
        {"m": parents["memo_deliverable"]},
    ).scalar_one()

    assert version == 3
