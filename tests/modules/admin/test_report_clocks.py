"""How long each kind of report may wait (item 51): the rule, without a database."""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.admin import report_clocks
from app.modules.auth.models.account import REPORT_CATEGORIES

FILED = datetime(2026, 10, 15, 21, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("category", "within"),
    [
        # Rule 3(2)(b), as amended in 2026: impersonation and intimate images.
        ("impersonation", timedelta(hours=2)),
        ("intimate_content", timedelta(hours=2)),
        # Content rule 3(1)(b) prohibits, as amended: 36 hours.
        ("abuse", timedelta(hours=36)),
        ("fake_profile", timedelta(hours=36)),
        ("spam", timedelta(hours=36)),
        ("other", timedelta(hours=36)),
        # Any other grievance: 7 days.
        ("non_payment", timedelta(days=7)),
    ],
)
def test_each_category_has_the_clock_the_rules_give_it(category, within):
    assert report_clocks.due_at(category, FILED) == FILED + within


def test_every_category_has_a_clock_and_none_is_longer_than_seven_days():
    assert set(report_clocks.ANSWER_WITHIN) == set(REPORT_CATEGORIES)
    assert len(REPORT_CATEGORIES) == 7  # the list read is not empty
    assert max(report_clocks.ANSWER_WITHIN.values()) == report_clocks.LONGEST
    assert timedelta(days=7) == report_clocks.LONGEST


def test_answered_exactly_at_the_deadline_is_in_time():
    due = FILED + timedelta(hours=2)

    assert not report_clocks.is_late(due, resolved_at=due, now=due + timedelta(days=1))


def test_answered_a_moment_after_the_deadline_is_late():
    due = FILED + timedelta(hours=2)

    assert report_clocks.is_late(
        due, resolved_at=due + timedelta(microseconds=1), now=due
    )


def test_an_open_report_is_late_only_once_its_deadline_has_passed():
    due = FILED + timedelta(hours=2)

    assert not report_clocks.is_late(due, resolved_at=None, now=due)
    assert report_clocks.is_late(due, resolved_at=None, now=due + timedelta(seconds=1))


def test_an_answer_in_time_stays_in_time_however_long_ago():
    due = FILED + timedelta(hours=36)

    assert not report_clocks.is_late(
        due, resolved_at=FILED + timedelta(hours=1), now=FILED + timedelta(days=400)
    )
