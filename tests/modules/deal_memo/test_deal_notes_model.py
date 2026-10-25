"""The deal_note table's rules, each broken with raw SQL (item 17, D-128).

The database refuses a note from nobody, an empty or overlong note, and
any change to one once written (database.md section 3); the app's own
login may not even try (test_app_role.py).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.modules.deal_memo.test_memo_deliverables_model import (
    parents,  # noqa: F401 - fixture
)


def insert(db, memo_id, side: str = "'brand'", body: str = "'A note.'") -> None:
    db.execute(
        text(
            f"INSERT INTO deal_note (deal_memo_id, author_side, body) VALUES (:m, {side}, {body})"  # noqa: S608 - fixed SQL from the parameters below
        ),
        {"m": memo_id},
    )


@pytest.mark.parametrize(
    ("side", "body", "rule"),
    [
        ("'admin'", "'A note.'", "ck_deal_note_author_side_allowed"),
        ("'brand'", "'   '", "ck_deal_note_body_length"),
        ("'brand'", "repeat('x', 1001)", "ck_deal_note_body_length"),
    ],
)
def test_the_database_refuses_a_bad_note(db, parents, side, body, rule):  # noqa: F811
    with pytest.raises(IntegrityError, match=rule):
        insert(db, parents["memo_deliverable"], side, body)


@pytest.mark.owner
@pytest.mark.parametrize(
    "change",
    ["UPDATE deal_note SET body = 'Rewritten.'", "DELETE FROM deal_note"],
)
def test_a_note_once_written_cannot_be_changed(db, parents, change):  # noqa: F811
    insert(db, parents["memo_deliverable"])

    with pytest.raises(IntegrityError, match="deal_note is append-only"):
        db.execute(text(change))
