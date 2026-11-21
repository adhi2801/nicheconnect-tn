"""What holds for every input of the rate report's rules (item 84, D-200; Hypothesis)."""

from collections import Counter
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import india_date
from app.modules.insights import rate_report_rules as rules
from app.modules.insights.rate_report_rules import Deal

fees = st.one_of(st.none(), st.integers(min_value=1, max_value=50_000_000))
cells = st.lists(
    st.builds(
        Deal,
        creator=st.integers(min_value=0, max_value=14),
        brand=st.integers(min_value=0, max_value=6),
        fee_paise=fees,
    ),
    max_size=40,
)
quarters = st.builds(
    lambda year, number: f"{year:04d}-Q{number}",
    st.integers(min_value=2000, max_value=2100),
    st.integers(min_value=1, max_value=4),
)
moments = st.datetimes(
    min_value=datetime(2001, 1, 1),  # noqa: DTZ001 - Hypothesis wants naive bounds
    max_value=datetime(2099, 12, 31),  # noqa: DTZ001
    timezones=st.just(UTC),
)


@given(cells)
def test_no_figure_shown_rests_on_fewer_than_its_floors(deals):
    cell = rules.agreed_cell(deals)

    if cell.deals is None:
        return
    assert cell.deals >= rules.AGREED_MIN_DEALS
    assert cell.creators is not None and cell.creators >= rules.AGREED_MIN_CREATORS
    assert cell.brands is not None and cell.brands >= rules.AGREED_MIN_BRANDS
    assert max(Counter(d.brand for d in deals).values()) * 2 <= len(deals)
    paid = [d for d in deals if d.fee_paise is not None]
    if cell.median_paise is not None:
        assert rules.enough_to_show(paid)
    if cell.lower_quarter_paise is not None:
        assert len({d.creator for d in paid}) >= rules.AGREED_QUARTILES_MIN_CREATORS


@given(cells)
def test_every_fee_shown_is_rounded_and_inside_the_range_of_fees(deals):
    cell = rules.agreed_cell(deals)
    paid = [d.fee_paise for d in deals if d.fee_paise is not None]
    for figure in (cell.lower_quarter_paise, cell.median_paise, cell.upper_quarter_paise):
        if figure is None:
            continue
        assert figure % rules.ROUND_TO_PAISE == 0
        assert rules.round_paise(min(paid)) <= figure <= rules.round_paise(max(paid))


@given(st.integers(min_value=1, max_value=14), cells)
def test_no_cell_equals_one_creator_s_lone_fee(lone, deals):
    """A cell is never one person's price: one creator's deals alone never show."""
    only_one = [Deal(creator=lone, brand=d.brand, fee_paise=d.fee_paise) for d in deals]

    assert rules.agreed_cell(only_one).median_paise is None


@given(st.floats(min_value=0, max_value=1e10), st.floats(min_value=0, max_value=1e10))
def test_rounding_never_reverses_order(a, b):
    low, high = sorted((a, b))

    assert rules.round_paise(low) <= rules.round_paise(high)
    assert abs(rules.round_paise(a) - a) <= rules.ROUND_TO_PAISE / 2


@given(quarters)
def test_quarters_follow_each_other_with_no_gap_or_overlap(quarter):
    start, end = rules.quarter_window(quarter)
    _, before_end = rules.quarter_window(rules.previous_quarter(quarter))

    assert before_end == start < end
    assert india_date(start) == rules.quarter_days(quarter)[0]
    assert india_date(end - timedelta(microseconds=1)) == rules.quarter_days(quarter)[1]


@given(quarters)
def test_next_and_previous_quarter_undo_each_other(quarter):
    assert rules.previous_quarter(rules.next_quarter(quarter)) == quarter
    assert rules.next_quarter(rules.previous_quarter(quarter)) == quarter


@given(st.sets(quarters, max_size=12), moments, st.integers(min_value=0, max_value=120))
def test_overdue_quarters_are_closed_unbuilt_and_in_order(built, now, grace_days):
    grace = timedelta(days=grace_days)
    last = rules.last_closed_quarter(now)

    overdue = rules.overdue_quarters(built, now, grace)

    assert not set(overdue) & built
    assert all(rules.parse_quarter(q) <= rules.parse_quarter(last) for q in overdue)
    assert overdue == sorted(overdue, key=rules.parse_quarter)
    assert len(overdue) == len(set(overdue))
    # Every quarter strictly between the oldest built and the last closed
    # that was not built is overdue, whatever the grace.
    known = [q for q in built if rules.parse_quarter(q) <= rules.parse_quarter(last)]
    if known:
        quarter = rules.next_quarter(min(known, key=rules.parse_quarter))
        while rules.parse_quarter(quarter) < rules.parse_quarter(last):
            assert (quarter in overdue) == (quarter not in built)
            quarter = rules.next_quarter(quarter)


@given(moments)
def test_the_last_closed_quarter_has_ended_and_the_next_has_not(now):
    closed = rules.last_closed_quarter(now)
    _, end = rules.quarter_window(closed)

    assert end <= now
    assert rules.quarter_window(rules.quarter_of(india_date(now)))[0] == end


@given(
    st.integers(min_value=0, max_value=4),
    st.lists(st.floats(0, 1e9), min_size=1, max_size=20),
)
def test_percentiles_lie_between_the_smallest_and_largest(step, values):
    fraction = step / 4

    assert min(values) <= rules.percentile_cont(values, fraction) <= max(values)
