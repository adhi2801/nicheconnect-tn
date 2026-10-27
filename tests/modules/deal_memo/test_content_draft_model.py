"""The content_draft table's rules, each broken with raw SQL (item 27, D-140).

The database refuses an empty or overlong draft, a link that is not one, a
status, answer or approval that does not fit the others, and a second
draft waiting, a second approved, or two with one round number.
"""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.modules.deal_memo.test_memo_deliverables_model import (
    parents,  # noqa: F401 - fixture
)

GOOD: dict[str, Any] = {
    "round": 1,
    "body": "The caption.",
    "content_url": None,
    "note": None,
    "status": "submitted",
    "changes_note": None,
    "approved_at": None,
    "answered_at": None,
    "auto_approved": False,
}


def insert(db, memo_id, **overrides: Any) -> None:
    values = {**GOOD, **overrides, "m": memo_id}
    db.execute(
        text(
            "INSERT INTO content_draft (deal_memo_id, round, body, content_url, note,"
            " status, changes_note, approved_at, answered_at, auto_approved) VALUES (:m,"
            " :round, :body, :content_url, :note, :status, :changes_note, :approved_at,"
            " :answered_at, :auto_approved)"
        ),
        values,
    )


def test_a_good_draft_is_kept(db, parents):  # noqa: F811
    insert(db, parents["memo_deliverable"])

    found = db.execute(
        text("SELECT round, status FROM content_draft WHERE deal_memo_id = :m"),
        {"m": parents["memo_deliverable"]},
    ).one()
    assert tuple(found) == (1, "submitted")


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        (
            {"status": "rejected", "answered_at": "2026-10-27T10:00:00Z"},
            "ck_content_draft_status_allowed",
        ),
        ({"body": "   "}, "ck_content_draft_body_length"),
        ({"body": "x" * 5001}, "ck_content_draft_body_length"),
        ({"content_url": "http://example.com/d"}, "ck_content_draft_content_url_https"),
        ({"note": "x" * 1001}, "ck_content_draft_note_length"),
        (
            {"changes_note": "Fix it, please."},
            "ck_content_draft_changes_note_matches_status",
        ),
        (
            {"status": "changes_requested", "answered_at": "2026-10-27T10:00:00Z"},
            "ck_content_draft_changes_note_matches_status",
        ),
        (
            {
                "status": "changes_requested",
                "changes_note": "No",
                "answered_at": "2026-10-27T10:00:00Z",
            },
            "ck_content_draft_changes_note_length",
        ),
        (
            {"status": "approved", "answered_at": "2026-10-27T10:00:00Z"},
            "ck_content_draft_approved_at_matches_status",
        ),
        (
            {"status": "approved", "approved_at": "2026-10-27T10:00:00Z"},
            "ck_content_draft_answered_at_matches_status",
        ),
        (
            {"answered_at": "2026-10-27T10:00:00Z"},
            "ck_content_draft_answered_at_matches_status",
        ),
        (
            {"approved_at": "2026-10-27T10:00:00Z"},
            "ck_content_draft_approved_at_matches_status",
        ),
        ({"auto_approved": True}, "ck_content_draft_auto_approved_is_approved"),
        ({"round": 0}, "ck_content_draft_round_positive"),
    ],
)
def test_the_database_refuses_a_bad_draft(db, parents, overrides, rule):  # noqa: F811
    with pytest.raises(IntegrityError, match=rule), db.begin_nested():
        insert(db, parents["memo_deliverable"], **overrides)


def test_one_draft_waits_per_memo(db, parents):  # noqa: F811
    insert(db, parents["memo_deliverable"])

    with pytest.raises(IntegrityError, match="uq_content_draft_open"), db.begin_nested():
        insert(db, parents["memo_deliverable"], round=2)


def test_one_draft_is_approved_per_memo(db, parents):  # noqa: F811
    approved = {
        "status": "approved",
        "approved_at": "2026-10-27T10:00:00Z",
        "answered_at": "2026-10-27T10:00:00Z",
    }
    insert(db, parents["memo_deliverable"], **approved)

    with (
        pytest.raises(IntegrityError, match="uq_content_draft_approved"),
        db.begin_nested(),
    ):
        insert(db, parents["memo_deliverable"], round=2, **approved)


def test_each_round_is_numbered_once(db, parents):  # noqa: F811
    changed = {
        "status": "changes_requested",
        "changes_note": "Add the ad label.",
        "answered_at": "2026-10-27T10:00:00Z",
    }
    insert(db, parents["memo_deliverable"], **changed)

    with pytest.raises(IntegrityError, match="uq_content_draft_round"), db.begin_nested():
        insert(db, parents["memo_deliverable"], **changed)


def test_a_draft_holds_its_memo(db, parents):  # noqa: F811
    insert(db, parents["memo_deliverable"])

    with (
        pytest.raises(IntegrityError, match="fk_content_draft_deal_memo_id_deal_memo"),
        db.begin_nested(),
    ):
        db.execute(
            text("DELETE FROM memo_deliverable WHERE deal_memo_id = :m"),
            {"m": parents["memo_deliverable"]},
        )
        db.execute(
            text("DELETE FROM deal_memo WHERE id = :m"),
            {"m": parents["memo_deliverable"]},
        )
