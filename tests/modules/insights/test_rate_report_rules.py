"""The quarterly rate report's rules, without a database (item 84, D-200).

Every floor is tested at its boundary, from both sides, with at least two
of every kind of thing (testing.md section 2).
"""

from datetime import UTC, date, datetime

import pytest

from app.modules.insights import rate_report_rules as rules
from app.modules.insights.rate_report_rules import Deal

# --- quarters ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("quarter", "first", "last"),
    [
        ("2026-Q1", date(2026, 1, 1), date(2026, 3, 31)),
        ("2026-Q2", date(2026, 4, 1), date(2026, 6, 30)),
        ("2026-Q3", date(2026, 7, 1), date(2026, 9, 30)),
        ("2026-Q4", date(2026, 10, 1), date(2026, 12, 31)),
        ("2028-Q1", date(2028, 1, 1), date(2028, 3, 31)),
    ],
)
def test_each_quarter_has_its_calendar_days(quarter, first, last):
    assert rules.quarter_days(quarter) == (first, last)
    assert rules.quarter_of(first) == rules.quarter_of(last) == quarter


@pytest.mark.parametrize(
    "key", ["2026-Q0", "2026-Q5", "26-Q1", "2026Q1", "2026-q1", "0000-Q1", " 2026-Q1", ""]
)
def test_anything_else_is_not_a_quarter(key):
    with pytest.raises(rules.NotAQuarter):
        rules.parse_quarter(key)


def test_a_quarter_starts_and_ends_at_midnight_in_tamil_nadu():
    start, end = rules.quarter_window("2026-Q2")

    assert start == datetime(2026, 3, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 6, 30, 18, 30, tzinfo=UTC)


def test_the_quarter_before_q1_is_last_year_s_q4():
    assert rules.previous_quarter("2027-Q1") == "2026-Q4"
    assert rules.previous_quarter("2026-Q3") == "2026-Q2"


@pytest.mark.parametrize(
    ("now", "closed"),
    [
        # 23:59 on 31 March in Tamil Nadu: Q1 has not ended yet.
        (datetime(2026, 3, 31, 18, 29, tzinfo=UTC), "2025-Q4"),
        # 00:00 on 1 April there: it has.
        (datetime(2026, 3, 31, 18, 30, tzinfo=UTC), "2026-Q1"),
        (datetime(2026, 11, 20, 6, 0, tzinfo=UTC), "2026-Q3"),
    ],
)
def test_the_last_closed_quarter_turns_at_tamil_nadu_midnight(now, closed):
    assert rules.last_closed_quarter(now) == closed


# --- numbers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("paise", "rounded"),
    [
        (0, 0),
        (4_999, 0),
        (5_000, 10_000),
        (14_999, 10_000),
        (615_000, 620_000),
        (649_999.5, 650_000),
    ],
)
def test_figures_round_to_the_nearest_hundred_rupees_half_up(paise, rounded):
    assert rules.round_paise(paise) == rounded


def test_percentiles_match_postgresql_s_percentile_cont():
    values = [100.0, 200.0, 400.0, 800.0]

    assert rules.percentile_cont(values, 0.5) == 300.0
    assert rules.percentile_cont(values, 0.25) == 175.0
    assert rules.percentile_cont(values, 0.75) == 500.0
    assert rules.percentile_cont([7.0], 0.5) == 7.0


# --- asking prices ----------------------------------------------------------------------


def test_four_creators_asking_are_not_enough_to_say():
    assert rules.asking_cell(4, 400_000, 500_000, 600_000) == rules.NOT_ENOUGH_ASKING


def test_five_creators_asking_show_rounded_quartiles():
    cell = rules.asking_cell(5, 412_345, 505_000, 649_999)

    assert cell == rules.AskingCell(
        creators=5,
        lower_quarter_paise=410_000,
        median_paise=510_000,
        upper_quarter_paise=650_000,
    )


@pytest.mark.parametrize("missing", ["lower", "median", "upper"])
def test_a_cell_missing_a_figure_says_not_enough(missing):
    figures = {"lower": 1.0, "median": 2.0, "upper": 3.0, missing: None}

    assert rules.asking_cell(9, **figures) == rules.NOT_ENOUGH_ASKING


# --- agreed fees ------------------------------------------------------------------------


def deals(spec: list[tuple[str, str, int | None]]) -> list[Deal]:
    return [Deal(creator=c, brand=b, fee_paise=fee) for c, b, fee in spec]


def spread(creators: int, brands: int, fee: int = 500_000) -> list[Deal]:
    """One deal per creator, brands taken in turn."""
    return [
        Deal(creator=f"c{i}", brand=f"b{i % brands}", fee_paise=fee + i * 10_000)
        for i in range(creators)
    ]


def test_five_deals_five_creators_three_brands_are_enough():
    assert rules.enough_to_show(spread(5, 3))


def test_four_deals_are_not():
    assert not rules.enough_to_show(spread(4, 3))


def test_five_deals_from_four_creators_are_not():
    cell = [*spread(4, 3), Deal(creator="c0", brand="b2", fee_paise=500_000)]

    assert len(cell) == 5
    assert not rules.enough_to_show(cell)


def test_two_brands_are_not_enough():
    assert not rules.enough_to_show(spread(6, 2))


def test_a_brand_behind_exactly_half_the_deals_is_allowed():
    cell = deals(
        [
            ("c1", "b1", 1),
            ("c2", "b1", 1),
            ("c3", "b1", 1),
            ("c4", "b2", 1),
            ("c5", "b3", 1),
            ("c6", "b2", 1),
        ]
    )

    assert rules.enough_to_show(cell)


def test_a_brand_behind_more_than_half_is_not():
    cell = deals(
        [
            ("c1", "b1", 1),
            ("c2", "b1", 1),
            ("c3", "b1", 1),
            ("c4", "b2", 1),
            ("c5", "b3", 1),
        ]
    )

    assert not rules.enough_to_show(cell)


def test_too_few_deals_say_nothing_at_all():
    assert rules.agreed_cell(spread(4, 3)) == rules.NOT_ENOUGH_AGREED


def test_a_cell_below_ten_creators_shows_the_median_only():
    cell = rules.agreed_cell(spread(5, 3))

    assert cell.deals == cell.creators == 5
    assert cell.brands == 3
    assert cell.barter_share_percent == 0
    assert cell.median_paise == 520_000
    assert cell.lower_quarter_paise is None
    assert cell.upper_quarter_paise is None


def test_ten_creators_show_the_quarters_too():
    cell = rules.agreed_cell(spread(10, 4))

    assert cell.creators == 10
    assert cell.lower_quarter_paise == 520_000
    assert cell.median_paise == 550_000
    assert cell.upper_quarter_paise == 570_000


def test_each_creator_counts_once_with_their_own_median():
    # c0 made three deals at 1,000,000 paise; alone it would drag the median.
    cell = spread(5, 3, fee=100_000) + deals(
        [("c0", "b1", 1_000_000), ("c0", "b2", 1_000_000)]
    )

    shown = rules.agreed_cell(cell)

    assert shown.deals == 7
    assert shown.creators == 5
    # c0's own median is 1,000,000; the others 110,000 to 140,000.
    assert shown.median_paise == 130_000


def test_barter_deals_are_counted_as_a_share_never_a_price():
    paid = spread(5, 3)
    barter = deals([("c5", "b0", None), ("c6", "b1", None), ("c7", "b2", None)])

    cell = rules.agreed_cell(paid + barter)

    assert cell.deals == 8
    assert cell.barter_share_percent == 38  # 3 of 8, half up
    assert cell.median_paise == 520_000


def test_barter_deals_alone_show_counts_but_no_fee():
    cell = rules.agreed_cell(deals([(f"c{i}", f"b{i % 3}", None) for i in range(5)]))

    assert cell.deals == 5
    assert cell.barter_share_percent == 100
    assert cell.median_paise is None


def test_paid_deals_must_meet_the_floors_on_their_own():
    # Five deals in the cell, but only four paid: the fee is not shown.
    cell = rules.agreed_cell(spread(4, 3) + deals([("c9", "b1", None)]))

    assert cell.deals == 5
    assert cell.barter_share_percent == 20
    assert cell.median_paise is None
