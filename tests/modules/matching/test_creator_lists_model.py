"""The creator_list tables' rules, each broken with raw SQL (item 66, D-129).

The database refuses a blank or overlong name, one name twice for a brand,
and a creator twice on one list; removing a list, a brand or a creator
takes the lines that belong to it (database.md section 3).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from tests.factories import build_brand, build_creator


@pytest.fixture
def ids(db) -> dict[str, uuid.UUID]:
    brand = build_brand(db, email=f"lists-{uuid.uuid4().hex[:12]}@example.com")
    creator = build_creator(db, handle=f"l{uuid.uuid4().hex[:12]}")
    db.add_all([brand, creator])
    db.flush()
    return {"brand": brand.id, "creator": creator.id}


def new_list(db, brand_id, name: str = "'Madurai food'") -> uuid.UUID:
    return db.execute(
        text(
            f"INSERT INTO creator_list (brand_id, name) VALUES (:b, {name}) RETURNING id"  # noqa: S608 - fixed SQL from the parameters below
        ),
        {"b": brand_id},
    ).scalar_one()


def new_entry(db, list_id, creator_id) -> None:
    db.execute(
        text("INSERT INTO creator_list_entry (list_id, creator_id) VALUES (:l, :c)"),
        {"l": list_id, "c": creator_id},
    )


def lines(db, list_id) -> int:
    return db.execute(
        text("SELECT count(*) FROM creator_list_entry WHERE list_id = :l"), {"l": list_id}
    ).scalar_one()


@pytest.mark.parametrize("name", ["''", "'   '"])
def test_the_database_refuses_a_blank_name(db, ids, name):
    with pytest.raises(IntegrityError, match="ck_creator_list_name_length"):
        new_list(db, ids["brand"], name)


def test_the_database_refuses_an_overlong_name(db, ids):
    with pytest.raises(DataError, match="value too long"):
        new_list(db, ids["brand"], "repeat('x', 61)")


def test_a_brand_has_one_list_by_each_name(db, ids):
    new_list(db, ids["brand"])

    with pytest.raises(IntegrityError, match="uq_creator_list_name"):
        new_list(db, ids["brand"])


def test_a_creator_is_on_a_list_once(db, ids):
    list_id = new_list(db, ids["brand"])
    new_entry(db, list_id, ids["creator"])

    with pytest.raises(IntegrityError, match="uq_creator_list_entry_once"):
        new_entry(db, list_id, ids["creator"])


def test_removing_a_list_removes_its_lines(db, ids):
    list_id = new_list(db, ids["brand"])
    new_entry(db, list_id, ids["creator"])

    db.execute(text("DELETE FROM creator_list WHERE id = :l"), {"l": list_id})

    assert lines(db, list_id) == 0


def test_removing_a_creator_removes_their_lines_but_not_the_list(db, ids):
    list_id = new_list(db, ids["brand"])
    new_entry(db, list_id, ids["creator"])

    db.execute(text("DELETE FROM creator WHERE id = :c"), {"c": ids["creator"]})

    assert lines(db, list_id) == 0
    assert (
        db.execute(
            text("SELECT count(*) FROM creator_list WHERE id = :l"), {"l": list_id}
        ).scalar_one()
        == 1
    )
