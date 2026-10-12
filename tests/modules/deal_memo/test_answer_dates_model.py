"""The database holds the three new rules itself (items 24, 25 and 28, D-089).

Each forbidden row is written past the code, and the database refuses it.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import FIXED_NOW
from tests.modules.deal_memo.test_deal_memo_model import build_memo, make_application


def refused(db, statement: str, params: dict, constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc_info, db.begin_nested():
        db.execute(text(statement), params)
    assert constraint in str(exc_info.value)


def a_memo(db, **overrides):
    memo = build_memo(db, **overrides)
    db.add(memo)
    db.flush()
    return memo


# Whole statements, never assembled from strings (ruff S608).
SET_DECLINED_AT = "UPDATE deal_memo SET declined_at = :value WHERE id = :id"
SET_MESSAGE = "UPDATE deal_memo SET change_request_message = :value WHERE id = :id"


def set_memo(db, memo, statement: str, value: object, constraint: str) -> None:
    refused(db, statement, {"id": memo.id, "value": value}, constraint)


# --- deal_memo.declined_at ---------------------------------------------------------------


@pytest.mark.parametrize("status", ["draft", "sent", "accepted", "cancelled"])
def test_only_a_declined_memo_has_a_decline_date(db, status):
    fields = {"cancellation_kind": "withdrawn_early"} if status == "cancelled" else {}
    memo = a_memo(db, status=status, **fields)

    set_memo(db, memo, SET_DECLINED_AT, FIXED_NOW, "declined_at_only_if_declined")


def test_a_declined_memo_takes_its_date(db):
    memo = a_memo(db, status="declined", declined_at=FIXED_NOW)

    assert memo.declined_at == FIXED_NOW


def test_a_memo_declined_before_the_column_may_have_none(db):
    memo = a_memo(db, status="declined")

    assert memo.declined_at is None


# --- deal_memo.change_request_message ----------------------------------------------------

RULE = "change_request_message_needs_request"


def test_a_memo_never_sent_back_carries_no_request(db):
    memo = a_memo(db, status="sent", revision_count=0)

    set_memo(db, memo, SET_MESSAGE, "Two reels, not three.", RULE)


@pytest.mark.parametrize("message", ["abcd", "  abcd  ", "x" * 1001])
def test_a_request_outside_5_to_1000_trimmed_characters_is_refused(db, message):
    memo = a_memo(db, status="change_requested", revision_count=1)

    set_memo(db, memo, SET_MESSAGE, message, RULE)


@pytest.mark.parametrize("message", ["abcde", "x" * 1000])
def test_a_request_at_either_limit_is_kept(db, message):
    memo = a_memo(
        db, status="change_requested", revision_count=1, change_request_message=message
    )

    assert memo.change_request_message == message


# --- application.first_answered_at -------------------------------------------------------

ANSWERED = "first_answered_at_only_if_answered"


def set_application(db, application, constraint: str) -> None:
    refused(
        db,
        "UPDATE application SET first_answered_at = :at WHERE id = :id",
        {"at": FIXED_NOW, "id": application.id},
        constraint,
    )


def test_an_application_still_waiting_has_no_answer(db):
    set_application(db, make_application(db, status="submitted"), ANSWERED)


def test_an_invitation_never_has_the_brands_first_answer(db):
    invitation = make_application(db, origin="invited", pitch=None, status="accepted")

    set_application(db, invitation, ANSWERED)


@pytest.mark.parametrize("status", ["shortlisted", "accepted", "rejected", "withdrawn"])
def test_an_answered_application_takes_the_date(db, status):
    fields = {"rejection_reason": "budget_mismatch"} if status == "rejected" else {}
    application = make_application(
        db, status=status, first_answered_at=FIXED_NOW, **fields
    )

    assert application.first_answered_at == FIXED_NOW
