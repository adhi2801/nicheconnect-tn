"""The deal_feedback table's rules, each broken with raw SQL (item 77, D-136).

The database refuses a score out of range, a blank or overlong note, a
second answer from one side, and any change to an answer once given
(database.md section 3); the app's own login may not even try
(test_app_role.py).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.modules.deal_memo.test_memo_deliverables_model import (
    parents,  # noqa: F401 - fixture
)


def insert(db, memo_id, **change) -> None:
    v = {
        "side": "'brand'",
        "brief": "5",
        "reliability": "4",
        "easy": "5",
        "note": "NULL",
        "ends": "now() + interval '14 days'",
    } | change
    values = f"(:m, {v['side']}, {v['brief']}, {v['reliability']}, {v['easy']}, {v['note']}, {v['ends']}, now())"
    sql = f"INSERT INTO deal_feedback (deal_memo_id, author_side, brief, reliability, easy, note, window_ends_at, created_at) VALUES {values}"  # noqa: S608 - fixed SQL from the parameters above
    db.execute(text(sql), {"m": memo_id})


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ({"side": "'admin'"}, "ck_deal_feedback_author_side_allowed"),
        ({"brief": "0"}, "ck_deal_feedback_brief_in_range"),
        ({"reliability": "6"}, "ck_deal_feedback_reliability_in_range"),
        ({"easy": "0"}, "ck_deal_feedback_easy_in_range"),
        ({"note": "'   '"}, "ck_deal_feedback_note_length"),
        ({"note": "repeat('x', 501)"}, "ck_deal_feedback_note_length"),
        ({"ends": "now() - interval '1 day'"}, "ck_deal_feedback_window_after_written"),
    ],
)
def test_the_database_refuses_bad_feedback(db, parents, change, rule):  # noqa: F811
    with pytest.raises(IntegrityError, match=rule):
        insert(db, parents["memo_deliverable"], **change)


def test_one_answer_a_side(db, parents):  # noqa: F811
    insert(db, parents["memo_deliverable"])

    with pytest.raises(IntegrityError, match="uq_deal_feedback_side"):
        insert(db, parents["memo_deliverable"], brief="1")


@pytest.mark.owner
@pytest.mark.parametrize(
    "change",
    ["UPDATE deal_feedback SET brief = 1", "DELETE FROM deal_feedback"],
)
def test_an_answer_once_given_cannot_be_changed(db, parents, change):  # noqa: F811
    insert(db, parents["memo_deliverable"])

    with pytest.raises(IntegrityError, match="deal_feedback is append-only"):
        db.execute(text(change))
