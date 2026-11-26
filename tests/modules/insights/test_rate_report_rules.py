"""The quarterly rate report's rules, without a database (item 84, D-200).

Every floor is tested at its boundary, from both sides, with at least two
of every kind of thing (testing.md section 2).
"""

from datetime import UTC, date, datetime, timedelta

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
    with pytest.raises(rules.NotAQuarter) as refused:
        rules.parse_quarter(key)

    assert str(refused.value) == key


def test_the_first_year_is_a_year():
    assert rules.parse_quarter("0001-Q1") == (1, 1)


def test_a_quarter_starts_and_ends_at_midnight_in_tamil_nadu():
    start, end = rules.quarter_window("2026-Q2")

    assert start == datetime(2026, 3, 31, 18, 30, tzinfo=UTC)
    assert end == datetime(2026, 6, 30, 18, 30, tzinfo=UTC)


def test_the_quarter_after_q4_is_next_year_s_q1():
    assert rules.next_quarter("2026-Q4") == "2027-Q1"
    assert rules.next_quarter("2026-Q1") == "2026-Q2"


# 2026-Q3 closed at midnight ending 30 September in Tamil Nadu; 06:00 there,
# two and three days on.
TWO_DAYS_ON = datetime(2026, 10, 3, 0, 30, tzinfo=UTC)
THREE_DAYS_ON = datetime(2026, 10, 4, 0, 30, tzinfo=UTC)
GRACE = timedelta(days=3)


def test_the_last_closed_quarter_is_overdue_only_after_its_grace():
    assert rules.overdue_quarters(set(), TWO_DAYS_ON, GRACE) == []
    assert rules.overdue_quarters(set(), THREE_DAYS_ON, GRACE) == ["2026-Q3"]
    assert rules.overdue_quarters({"2026-Q3"}, THREE_DAYS_ON, GRACE) == []


def test_a_gap_since_the_first_report_is_overdue_however_old():
    built = {"2025-Q3", "2026-Q1", "2026-Q3"}

    assert rules.overdue_quarters(built, THREE_DAYS_ON, GRACE) == [
        "2025-Q4",
        "2026-Q2",
    ]
    # Inside the last quarter's grace, an older gap is still said.
    assert rules.overdue_quarters({"2026-Q1"}, TWO_DAYS_ON, GRACE) == ["2026-Q2"]


def test_quarters_after_the_last_closed_are_ignored():
    assert rules.overdue_quarters({"2026-Q3", "2027-Q2"}, THREE_DAYS_ON, GRACE) == []
    assert rules.overdue_quarters({"2027-Q2"}, THREE_DAYS_ON, GRACE) == ["2026-Q3"]


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


def test_a_cell_below_ten_paid_creators_shows_counts_but_no_fee():
    """D-201: the median no longer appears alone on five to nine voices,
    even where the p% rule would allow it (five brands, fees alike)."""
    paid = spread(9, 5)
    assert rules.enough_to_show(paid) and rules.fees_protected(paid)

    cell = rules.agreed_cell(paid)

    assert cell.deals == cell.creators == 9
    assert cell.brands == 5
    assert cell.barter_share_percent == 0
    assert cell.median_paise is None
    assert cell.lower_quarter_paise is None
    assert cell.upper_quarter_paise is None


def test_ten_creators_show_the_median_and_the_quarters():
    cell = rules.agreed_cell(spread(10, 4))

    assert cell.creators == 10
    assert cell.lower_quarter_paise == 520_000
    assert cell.median_paise == 550_000
    assert cell.upper_quarter_paise == 570_000


def test_each_creator_counts_once_with_their_own_median():
    # c0 made three deals at 300,000 paise; alone they would drag the median.
    cell = spread(10, 4, fee=100_000) + deals(
        [("c0", "b1", 300_000), ("c0", "b2", 300_000)]
    )

    shown = rules.agreed_cell(cell)

    assert shown.deals == 12
    assert shown.creators == 10
    # c0's own median is 300,000; the others 110,000 to 190,000: the
    # median of the ten is 155,000, rounded half up.
    assert shown.median_paise == 160_000


def test_barter_deals_are_counted_as_a_share_never_a_price():
    paid = spread(10, 4)
    barter = deals([("c10", "b0", None), ("c11", "b1", None), ("c12", "b2", None)])

    cell = rules.agreed_cell(paid + barter)

    assert cell.deals == 13
    assert cell.barter_share_percent == 23  # 3 of 13, half up
    assert cell.median_paise == 550_000


# --- the p% rule (D-201) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("contributions", "safe"),
    [
        ([100, 50, 40, 10], True),  # 10 left after the top three: exactly 10%
        ([100, 50, 40, 9], False),  # 9 is not
        ([1_005, 500, 400, 100], False),  # 100 is just under 10% of 1,005
        ([100, 50, 10], False),  # the second and third together know the first
        ([100, 100, 5, 5, 4], False),
        ([100, 100, 5, 5, 5], True),
        ([1_000, 1, 1, 1], False),
        ([100], False),
        ([], False),
    ],
)
def test_the_p_percent_rule_for_two_who_collude_at_its_edge(contributions, safe):
    assert rules.p_percent_safe(contributions) is safe


@pytest.mark.parametrize(
    ("contributions", "safe"),
    [([100, 50, 10], True), ([100, 50, 9], False), ([100, 100], False)],
)
def test_the_plain_p_percent_rule_is_the_coalition_of_one(contributions, safe):
    assert rules.p_percent_safe(contributions, coalition=1) is safe


def test_three_brands_never_show_a_fee_against_two_who_collude():
    """With three brands, the other two know everything but the third's."""
    assert not rules.fees_protected(spread(12, 3))
    assert rules.agreed_cell(spread(12, 3)).median_paise is None


def test_the_rule_is_ten_percent_against_two():
    assert (rules.AGREED_P_PERCENT, rules.AGREED_P_COALITION) == (10, 2)


def test_the_p_percent_rule_does_not_care_about_order():
    assert rules.p_percent_safe([10, 100, 50]) is rules.p_percent_safe([100, 50, 10])


def test_brands_a_and_b_together_cannot_read_brand_c_s_fee():
    """The review's example: A and B each pay small fees, C one large fee.
    Every count floor is met (10 creators, 3 brands, no brand over half),
    but A and B together, knowing their own fees, could read C's fee off a
    published figure. The p% rule suppresses the fee figures."""
    cell = deals(
        [(f"a{i}", "A", 10_000) for i in range(5)]
        + [(f"b{i}", "B", 10_000) for i in range(4)]
        + [("c0", "C", 5_000_000)]
    )
    assert rules.enough_to_show(cell)
    assert len({deal.creator for deal in cell}) == 10

    shown = rules.agreed_cell(cell)

    assert shown.deals == 10 and shown.brands == 3  # the counts still show
    assert shown.median_paise is None
    assert shown.lower_quarter_paise is shown.upper_quarter_paise is None


def test_one_creator_s_large_fees_are_protected_too():
    """Safe brand by brand, but one creator's fees dwarf the other nine's."""
    cell = [
        Deal(creator=f"c{i}", brand=f"b{i % 5}", fee_paise=10_000) for i in range(9)
    ] + [Deal(creator="big", brand=f"b{i}", fee_paise=700_000) for i in range(4)]
    by_brand = [720_000, 720_000, 720_000, 720_000, 10_000]
    assert rules.p_percent_safe(by_brand)
    assert rules.enough_to_show(cell)

    assert not rules.fees_protected(cell)
    assert rules.agreed_cell(cell).median_paise is None


def test_barter_deals_alone_show_counts_but_no_fee():
    cell = rules.agreed_cell(deals([(f"c{i}", f"b{i % 3}", None) for i in range(5)]))

    assert cell.deals == 5
    assert cell.barter_share_percent == 100
    assert cell.median_paise is None


def test_paid_deals_must_meet_the_floors_on_their_own():
    # Eleven deals in the cell, but only nine paid: the fee is not shown.
    cell = rules.agreed_cell(
        spread(9, 3) + deals([("c90", "b1", None), ("c91", "b2", None)])
    )

    assert cell.deals == 11
    assert cell.barter_share_percent == 18
    assert cell.median_paise is None


def test_a_brand_s_fees_are_summed_before_the_rule():
    """No one deal of the large brand stands out, but its five together are
    most of the money: summed per brand, the cell is not safe."""
    cell = [Deal(creator=f"big{i}", brand="big", fee_paise=100_000) for i in range(5)]
    cell += [Deal(creator=f"c{i}", brand=f"b{i % 4}", fee_paise=10_000) for i in range(5)]
    assert rules.enough_to_show(cell)
    assert rules.p_percent_safe([100_000, 10_000, 10_000, 10_000, 10_000])

    assert not rules.fees_protected(cell)
