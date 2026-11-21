"""Building the quarterly city rate report from the database (item 84, D-200).

Every test that filters or groups builds at least two of each thing behind
it (testing.md section 2), in a city of its own.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.insights import rate_report_rules as rules
from app.modules.insights import rate_report_service as service
from app.modules.insights.rate_report_models import CityRateReport
from app.modules.insights.rate_report_schemas import RateReportBody
from tests.query_counts import count_queries
from tests.rate_reports import BUILT, World, suspend

REEL = ("instagram", "reel")
QUARTER = "2026-Q2"


def body(db, *, agreed_fees: bool = False) -> RateReportBody:
    return service.build_body(db, QUARTER, BUILT, agreed_fees=agreed_fees)


def city_of(report: RateReportBody, world: World):
    found = [row for row in report.cities if row.city == world.city]
    assert len(found) <= 1
    return found[0] if found else None


def asking(report: RateReportBody, world: World, cell=REEL):
    city = city_of(report, world)
    assert city is not None, f"{world.city} is not listed"
    return next(row for row in city.asking_prices if (row.platform, row.format) == cell)


def agreed(report: RateReportBody, world: World, cell=REEL):
    city = city_of(report, world)
    assert city is not None and city.agreed_fees is not None
    return next(row for row in city.agreed_fees if (row.platform, row.format) == cell)


# --- asking prices ----------------------------------------------------------------------


def test_five_creators_asking_give_rounded_quartiles(db):
    world, other = World(db), World(db)
    for price in (400_000, 450_000, 500_000, 550_000, 612_345):
        world.creator(prices={REEL: [price]})
    for price in (1_000_000, 1_100_000, 1_200_000, 1_300_000, 1_400_000):
        other.creator(prices={REEL: [price]})

    report = body(db)

    assert asking(report, world).model_dump() == {
        "platform": "instagram",
        "format": "reel",
        "creators": 5,
        "lower_quarter_paise": 450_000,
        "median_paise": 500_000,
        "upper_quarter_paise": 550_000,
    }
    assert asking(report, other).median_paise == 1_200_000


def test_four_creators_asking_are_not_enough_to_say(db):
    world = World(db)
    world.listed(1)
    for price in (400_000, 450_000, 500_000, 550_000):
        world.creator(prices={REEL: [price]})

    cell = asking(body(db), world)

    assert cell.creators is cell.median_paise is cell.lower_quarter_paise is None


def test_each_creator_counts_once_with_their_own_median(db):
    world = World(db)
    for price in (400_000, 450_000, 500_000, 550_000):
        world.creator(prices={REEL: [price]})
    world.creator(prices={REEL: [9_000_000, 9_000_000, 9_000_000]})

    cell = asking(body(db), world)

    assert cell.creators == 5
    assert cell.median_paise == 500_000


@pytest.mark.parametrize(
    "left_out",
    [
        {"passport": False},
        {"rate_card": False},
        {"suspended": True},
        {"city": "Somewhere else entirely"},
    ],
)
def test_only_published_active_creators_of_the_city_count(db, left_out):
    world = World(db)
    world.listed(1)
    for price in (400_000, 450_000, 500_000, 550_000):
        world.creator(prices={REEL: [price]})
    left_out = dict(left_out)  # a copy: the parameter is reused on a rerun
    suspended = left_out.pop("suspended", False)
    fifth = world.creator(prices={REEL: [600_000]}, **left_out)
    if suspended:
        suspend(db, fifth.account_id)

    assert asking(body(db), world).creators is None


def test_a_city_is_matched_whatever_its_case_or_spaces(db):
    world = World(db)
    for index, spelling in enumerate(
        (
            world.city,
            world.city.upper(),
            f"  {world.city} ",
            world.city,
            world.city.lower(),
        )
    ):
        world.creator(prices={REEL: [400_000 + index * 50_000]}, city=spelling)

    assert asking(body(db), world).creators == 5


@pytest.mark.parametrize("letters", ["İzmir", "ΣΑΣ"])
def test_a_city_python_and_postgres_lower_differently_still_has_figures(db, letters):
    """Python lowers "İ" to two characters and a last "Σ" to "ς"; PostgreSQL
    does neither. The city is matched on the database's own key, so its
    cells are filled, never left null by a key that matches nobody."""
    world = World(db, city=f"{letters} {uuid.uuid4().hex[:8]}")
    for price in (400_000, 450_000, 500_000, 550_000, 600_000):
        world.creator(prices={REEL: [price]})

    cell = asking(body(db), world)

    assert cell.creators == 5
    assert cell.median_paise == 500_000


def test_a_city_with_fewer_than_five_published_creators_is_not_listed(db):
    world, listed = World(db), World(db)
    for _ in range(4):
        world.creator(prices={REEL: [500_000]})
    world.creator(passport=False, prices={REEL: [500_000]})
    listed.listed()

    report = body(db)

    assert city_of(report, world) is None
    assert city_of(report, listed) is not None


def test_every_city_has_every_platform_and_format_in_one_order(db):
    world = World(db)
    world.listed()

    city = city_of(body(db), world)

    assert [(row.platform, row.format) for row in city.asking_prices] == list(
        service.CELLS
    )
    assert len(service.CELLS) == 14


def test_audience_bands_count_creators_by_their_own_channel(db):
    """Statewide, so measured as the change this test's creators make."""
    before = body(db)
    world = World(db)
    for price in (400_000, 450_000, 500_000, 550_000, 600_000):
        world.creator(prices={REEL: [price]}, followers=20_000)
    for price in (900_000, 950_000):
        world.creator(prices={REEL: [price]}, followers=200_000)

    after = body(db)

    def band(report, label):
        return next(
            row
            for row in report.audience_bands
            if (row.audience_band, row.platform, row.format) == (label, *REEL)
        )

    grown = (band(after, "10k_50k").creators or 0) - (
        band(before, "10k_50k").creators or 0
    )
    assert grown == 5
    assert band(after, "10k_50k").audience_figures_from is not None
    assert len(after.audience_bands) == 5 * 14


def test_a_creator_on_a_band_s_edge_counts_in_the_band_above(db):
    """The same edges as fair-rate guidance (`asking_prices.in_band`):
    10,000 followers is 10k_50k's first count; 50,000 is 50k_100k's."""
    before = body(db)
    world = World(db)
    for price in (400_000, 450_000, 500_000, 550_000, 600_000):
        world.creator(prices={REEL: [price]}, followers=10_000)
    world.creator(prices={REEL: [900_000]}, followers=50_000)

    after = body(db)

    def grown(label: str) -> int:
        def count(report: RateReportBody) -> int:
            return next(
                row.creators or 0
                for row in report.audience_bands
                if (row.audience_band, row.platform, row.format) == (label, *REEL)
            )

        return count(after) - count(before)

    assert grown("10k_50k") == 5
    assert grown("under_10k") == 0


# --- agreed fees ------------------------------------------------------------------------


def agreed_world(db, good: int = 5) -> tuple[World, list]:
    world = World(db)
    creators = [world.creator() for _ in range(6)]
    brands = [world.brand() for _ in range(3)]
    for index in range(good):
        world.deal(creators[index], brands[index % 3], fee=400_000 + index * 50_000)
    return world, creators + brands


def test_agreed_fees_are_left_out_while_switched_off(db):
    world, _ = agreed_world(db)

    report = body(db, agreed_fees=False)

    assert report.agreed_fees_included is False
    assert city_of(report, world).agreed_fees is None


def test_five_deals_five_creators_three_brands_show_the_median(db):
    world, _ = agreed_world(db)
    other, _ = agreed_world(db)

    report = body(db, agreed_fees=True)
    cell = agreed(report, world)

    assert report.agreed_fees_included is True
    assert (cell.deals, cell.creators, cell.brands) == (5, 5, 3)
    assert cell.median_paise == 500_000
    assert cell.lower_quarter_paise is None
    assert agreed(report, other).deals == 5


@pytest.mark.parametrize(
    "excluded",
    [
        {"status": "cancelled"},
        {"status": "sent"},
        {"deliverables": [("instagram", "reel", 1), ("instagram", "story", 1)]},
        {"deliverables": [("instagram", "reel", 2)]},
        # The moment before the quarter began in Tamil Nadu, and the moment it ended.
        {"accepted": datetime(2026, 3, 31, 18, 29, 59, tzinfo=UTC)},
        {"accepted": datetime(2026, 6, 30, 18, 30, tzinfo=UTC)},
        {"suspended": "creator"},
        {"suspended": "brand"},
    ],
)
def test_a_deal_that_does_not_count_leaves_the_cell_below_its_floor(db, excluded):
    world, people = agreed_world(db, good=4)
    creator, brand = people[4], people[7]
    excluded = dict(excluded)  # a copy: the parameter is reused on a rerun
    suspended = excluded.pop("suspended", None)
    world.deal(creator, brand, **excluded)
    if suspended == "creator":
        suspend(db, creator.account_id)
    if suspended == "brand":
        suspend(db, brand.account_id)

    assert agreed(body(db, agreed_fees=True), world).deals is None


@pytest.mark.parametrize(
    "accepted",
    [
        datetime(2026, 3, 31, 18, 30, tzinfo=UTC),
        datetime(2026, 6, 30, 18, 29, 59, tzinfo=UTC),
    ],
)
def test_a_deal_at_the_quarter_s_first_and_last_moment_counts(db, accepted):
    world, people = agreed_world(db, good=4)
    world.deal(people[4], people[7], accepted=accepted)

    assert agreed(body(db, agreed_fees=True), world).deals == 5


def test_a_deal_counts_in_its_one_deliverable_s_cell(db):
    world, people = agreed_world(db, good=0)
    for index in range(5):
        world.deal(
            people[index], people[6 + index % 3], deliverables=[("youtube", "short", 1)]
        )

    report = body(db, agreed_fees=True)

    assert agreed(report, world, ("youtube", "short")).deals == 5
    assert agreed(report, world).deals is None


def test_barter_deals_count_as_a_share(db):
    world, people = agreed_world(db, good=5)
    world.deal(people[5], people[6], fee=None)

    cell = agreed(body(db, agreed_fees=True), world)

    assert cell.deals == 6
    assert cell.barter_share_percent == 17
    assert cell.median_paise == 500_000


# --- what the body holds ----------------------------------------------------------------


def test_the_body_names_nobody(db):
    world, people = agreed_world(db)
    for price in (400_000, 450_000, 500_000, 550_000, 600_000):
        people.append(world.creator(prices={REEL: [price]}))

    text = json.dumps(body(db, agreed_fees=True).model_dump(mode="json"))

    for row in people:
        assert str(row.id) not in text
        assert str(row.account_id) not in text
        for field in ("handle", "display_name", "name", "email"):
            value = getattr(row, field, None)
            if value and value not in ("Acme", "Priya Eats"):
                assert value not in text


def test_the_build_costs_the_same_queries_for_one_city_or_three(db):
    def queries() -> int:
        with count_queries() as statements:
            body(db, agreed_fees=True)
        return len(statements)

    first, _ = agreed_world(db)
    first.creator(prices={REEL: [500_000]})
    one = queries()
    for _ in range(2):
        more, _ = agreed_world(db)
        more.creator(prices={REEL: [500_000]})

    assert queries() == one == 4


# --- building once a quarter ------------------------------------------------------------

FAR = datetime(2031, 2, 3, 0, 30, tzinfo=UTC)  # a quarter no other test builds
# A run scheduled at FAR but retried until past midnight in Tamil Nadu.
FAR_LATER = datetime(2031, 2, 3, 19, 0, tzinfo=UTC)


def test_the_last_closed_quarter_is_built_unpublished_and_fingerprinted(db):
    World(db).listed()

    run = service.build_due(db, FAR, built_at=FAR_LATER, agreed_fees=False)
    row = db.scalar(select(CityRateReport).where(CityRateReport.quarter == "2030-Q4"))

    assert run == service.BuildRun(quarter="2030-Q4", built=True)
    assert row.published_at is None
    assert row.method_version == rules.METHOD_VERSION
    # When it was really built, not when the run was scheduled.
    assert row.built_at == row.created_at == row.updated_at == FAR_LATER
    assert row.body["as_of"] == "2031-02-04"
    assert row.body_sha256 == service.fingerprint(row.body)
    assert RateReportBody.model_validate(row.body).quarter == "2030-Q4"


def test_a_built_quarter_s_figures_are_never_worked_out_again(db, monkeypatch):
    service.build_due(db, FAR, built_at=FAR, agreed_fees=False)

    def no_second_build(*args, **kwargs):
        raise AssertionError("a built quarter was worked out again")

    monkeypatch.setattr(service, "build_body", no_second_build)

    assert service.build_due(db, FAR, built_at=FAR, agreed_fees=False).built is False


def test_a_page_of_the_archive_reads_one_row_past_the_page(db):
    """Enough to know whether there is a next page, never the whole table."""
    from sqlalchemy import event

    from app.db.session import engine

    limits: list[object] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FROM city_rate_report" in statement and "LIMIT" in statement:
            limits.append(parameters)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        service.published(db, limit=7, cursor=None)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    [parameters] = limits
    assert 8 in dict(parameters).values()


def test_a_built_quarter_is_never_built_again(db):
    service.build_due(db, FAR, built_at=FAR, agreed_fees=False)
    World(db).listed()  # the figures move; the report must not

    again = service.build_due(
        db, FAR + timedelta(days=1), built_at=FAR + timedelta(days=1), agreed_fees=False
    )

    assert again == service.BuildRun(quarter="2030-Q4", built=False)
    assert db.scalar(select(func.count()).where(CityRateReport.quarter == "2030-Q4")) == 1


def test_the_fingerprint_is_sha256_of_canonical_json():
    import hashlib

    data = {"b": [1, "₹"], "a": None}

    assert service.canonical_json(data) == b'{"a":null,"b":[1,"\u20b9"]}'
    assert (
        service.fingerprint(data)
        == hashlib.sha256(service.canonical_json(data)).hexdigest()
    )
