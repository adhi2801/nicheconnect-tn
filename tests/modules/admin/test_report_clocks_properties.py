"""What holds for every report, whenever it is filed (item 51, D-090)."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.admin import report_clocks
from app.modules.auth.models.account import REPORT_CATEGORIES

categories = st.sampled_from(REPORT_CATEGORIES)
# Hypothesis takes naive bounds and adds the zone itself (timezones=).
moments = st.datetimes(
    min_value=datetime(2026, 2, 20),  # noqa: DTZ001
    max_value=datetime(2040, 1, 1),  # noqa: DTZ001
    timezones=st.just(UTC),
)
gaps = st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=30))


@given(categories, moments)
def test_a_deadline_is_after_filing_and_within_the_longest_clock(category, filed):
    due = report_clocks.due_at(category, filed)

    # The same rule the database holds: ck_report_due_within_seven_days.
    assert filed < due <= filed + report_clocks.LONGEST


@given(categories, moments)
def test_a_deadline_is_one_of_the_three_clocks_the_rules_set(category, filed):
    within = report_clocks.due_at(category, filed) - filed

    assert within in {timedelta(hours=2), timedelta(hours=36), timedelta(days=7)}


@given(categories, moments, gaps, gaps)
def test_an_open_report_once_late_stays_late(category, filed, first, later):
    due = report_clocks.due_at(category, filed)
    now = filed + first

    if report_clocks.is_late(due, None, now):
        assert report_clocks.is_late(due, None, now + later)


@given(categories, moments, gaps, gaps)
def test_whether_an_answer_was_late_never_changes_afterwards(
    category, filed, answered_after, looked_after
):
    due = report_clocks.due_at(category, filed)
    resolved = filed + answered_after

    assert report_clocks.is_late(due, resolved, resolved) == report_clocks.is_late(
        due, resolved, resolved + looked_after
    )
    assert report_clocks.is_late(due, resolved, resolved) == (resolved > due)
