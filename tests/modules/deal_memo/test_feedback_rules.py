"""When feedback may be given and seen (item 77, D-136): the pure rule, and what always holds."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.deal_memo.feedback_rules import (
    FEEDBACK_WINDOW,
    may_answer,
    revealed,
    window_ends,
)

DONE = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_answers_open_when_a_deal_finishes_and_close_after_fourteen_days():
    assert may_answer(None, False, DONE) == "not_finished"
    assert may_answer(DONE, False, DONE) is None
    assert may_answer(DONE, False, DONE + FEEDBACK_WINDOW - timedelta(seconds=1)) is None
    assert may_answer(DONE, False, DONE + FEEDBACK_WINDOW) == "closed"
    assert may_answer(DONE, True, DONE) == "already_given"


def test_an_answer_is_hidden_until_both_answered_or_the_window_closes():
    ends = window_ends(DONE)

    assert revealed(False, ends, DONE) is False
    assert revealed(True, ends, DONE) is True
    assert revealed(False, ends, ends) is True


offsets = st.integers(min_value=-30 * 24 * 3600, max_value=60 * 24 * 3600)


@given(st.booleans(), offsets, offsets)
def test_once_shown_an_answer_stays_shown(other_answered, first, later):
    ends = window_ends(DONE)
    earlier, after = sorted(
        (DONE + timedelta(seconds=first), DONE + timedelta(seconds=later))
    )

    if revealed(other_answered, ends, earlier):
        assert revealed(other_answered, ends, after)


@given(offsets)
def test_the_other_side_answering_only_ever_reveals(offset):
    now = DONE + timedelta(seconds=offset)
    ends = window_ends(DONE)

    assert revealed(True, ends, now) >= revealed(False, ends, now)


@given(offsets)
def test_nobody_may_answer_once_answers_are_shown_by_the_clock(offset):
    """The window closing both reveals and stops answers: no answer arrives late, seeing the other."""
    now = DONE + timedelta(seconds=offset)

    if revealed(False, window_ends(DONE), now):
        assert may_answer(DONE, False, now) == "closed"
