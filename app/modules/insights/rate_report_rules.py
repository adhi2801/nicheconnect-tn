"""The quarterly city rate report's rules, as pure functions (item 84, D-200).

Everything here is a function of its inputs, with no database, so every
branch is tested directly, its properties are tested by Hypothesis, and the
nightly mutation run reads it (testing.md section 2). The queries that feed
it are `rate_report_figures`; the plain-English method is
`docs/RATE_REPORT_METHOD.md`, method version 1.

**Quarters** are Tamil Nadu calendar quarters, keyed `YYYY-Qn`: Q1 is 1
January to 31 March, and a quarter runs from midnight at its start in Tamil
Nadu to midnight after its last day (half-open, as `end_of_india_day`).

**Asking prices** (D-056, D-078, reused exactly): each creator's own median
first, in SQL; a cell shows its lower quarter, median and upper quarter only
when at least 5 creators are behind it. Never a minimum or a maximum: each of
those is one person's price.

**Agreed fees** (Decision 2, option A), from accepted memos with exactly one
deliverable of quantity 1, so the fee is for one platform and format:

- a cell needs at least 5 deals, 5 distinct creators and 3 distinct brands,
  and no single brand behind more than half of its deals (a dominance rule,
  after the (n, k) rules statistics offices apply to magnitude tables:
  `docs/RATE_REPORT_METHOD.md` section 4);
- the fee figures need the same of the paid deals alone; barter deals are
  counted in the cell and shown as a share, never as a price;
- each creator's own median first, so one creator with many deals counts once;
- the median only, until the paid deals rest on at least 10 creators, then
  the quarters too.

**Every figure is rounded to the nearest ₹100** (half up), so a published
figure is not one person's exact price. Below its floor a figure is None,
meaning *not enough to say*: never zero, never an estimate (D-038).
"""

import math
import re
from collections import Counter, defaultdict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.core.clock import IST_OFFSET, end_of_india_day, india_date

METHOD_VERSION = 1

ASKING_MIN_CREATORS = 5  # as city figures and fair-rate guidance (D-056, D-078)
AGREED_MIN_DEALS = 5
AGREED_MIN_CREATORS = 5
AGREED_MIN_BRANDS = 3
AGREED_MAX_BRAND_SHARE_PERCENT = 50
AGREED_QUARTILES_MIN_CREATORS = 10
ROUND_TO_PAISE = 10_000  # ₹100

_QUARTER = re.compile(r"^([0-9]{4})-Q([1-4])$")


class NotAQuarter(ValueError):
    """A key that is not `YYYY-Qn`."""


# --- quarters ---------------------------------------------------------------------------


def parse_quarter(quarter: str) -> tuple[int, int]:
    """(year, quarter number) from `YYYY-Qn`. Raises NotAQuarter."""
    match = _QUARTER.fullmatch(quarter)
    if match is None or int(match.group(1)) < 1:
        raise NotAQuarter(quarter)
    return int(match.group(1)), int(match.group(2))


def quarter_of(day: date) -> str:
    """The quarter a Tamil Nadu calendar day falls in."""
    return f"{day.year:04d}-Q{(day.month - 1) // 3 + 1}"


def quarter_days(quarter: str) -> tuple[date, date]:
    """The quarter's first and last day."""
    year, number = parse_quarter(quarter)
    first = date(year, 3 * number - 2, 1)
    if number == 4:
        return first, date(year, 12, 31)
    return first, date(year, 3 * number + 1, 1) - timedelta(days=1)


def quarter_window(quarter: str) -> tuple[datetime, datetime]:
    """The moments the quarter starts and ends, in UTC, half-open.

    A memo accepted at 23:59 on 31 March in Tamil Nadu (18:29 UTC) is Q1's;
    one accepted at 00:00 on 1 April there (18:30 UTC on 31 March) is Q2's.
    """
    first, last = quarter_days(quarter)
    return datetime.combine(first, time(0), UTC) - IST_OFFSET, end_of_india_day(last)


def previous_quarter(quarter: str) -> str:
    year, number = parse_quarter(quarter)
    return f"{year - 1:04d}-Q4" if number == 1 else f"{year:04d}-Q{number - 1}"


def last_closed_quarter(now: datetime) -> str:
    """The newest quarter that has wholly ended in Tamil Nadu at `now`."""
    return previous_quarter(quarter_of(india_date(now)))


# --- numbers ----------------------------------------------------------------------------


def round_paise(value: float) -> int:
    """To the nearest ₹100, a half going up. Monotone: a larger input never
    rounds lower."""
    return math.floor(value / ROUND_TO_PAISE + 0.5) * ROUND_TO_PAISE


def percentile_cont(values: Sequence[float], fraction: float) -> float:
    """PostgreSQL's `percentile_cont`: linear between the two nearest values,
    so a quartile worked out here means what one worked out in SQL means."""
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


# --- asking prices ----------------------------------------------------------------------


@dataclass(frozen=True)
class AskingCell:
    creators: int | None
    lower_quarter_paise: int | None
    median_paise: int | None
    upper_quarter_paise: int | None


NOT_ENOUGH_ASKING = AskingCell(None, None, None, None)


def asking_cell(
    creators: int, lower: float | None, median: float | None, upper: float | None
) -> AskingCell:
    """One cell from the SQL's count and quartiles of per-creator medians."""
    if creators < ASKING_MIN_CREATORS or lower is None or median is None or upper is None:
        return NOT_ENOUGH_ASKING
    return AskingCell(
        creators=creators,
        lower_quarter_paise=round_paise(lower),
        median_paise=round_paise(median),
        upper_quarter_paise=round_paise(upper),
    )


# --- agreed fees ------------------------------------------------------------------------


@dataclass(frozen=True)
class Deal:
    """One accepted memo in a cell: who agreed it, and its fee (None: barter)."""

    creator: Hashable
    brand: Hashable
    fee_paise: int | None


@dataclass(frozen=True)
class AgreedCell:
    deals: int | None
    creators: int | None
    brands: int | None
    barter_share_percent: int | None
    lower_quarter_paise: int | None
    median_paise: int | None
    upper_quarter_paise: int | None


NOT_ENOUGH_AGREED = AgreedCell(None, None, None, None, None, None, None)


def enough_to_show(deals: Sequence[Deal]) -> bool:
    """The floors: deals, distinct creators, distinct brands, and no brand
    behind more than half of the deals."""
    if len(deals) < AGREED_MIN_DEALS:
        return False
    if len({deal.creator for deal in deals}) < AGREED_MIN_CREATORS:
        return False
    by_brand = Counter(deal.brand for deal in deals)
    if len(by_brand) < AGREED_MIN_BRANDS:
        return False
    most = max(by_brand.values())
    return most * 100 <= AGREED_MAX_BRAND_SHARE_PERCENT * len(deals)


def _per_creator_medians(fees: Sequence[tuple[Hashable, int]]) -> list[float]:
    """Each creator's own median fee: one creator counts once, however many
    deals they made."""
    by_creator: dict[Hashable, list[float]] = defaultdict(list)
    for creator, fee in fees:
        by_creator[creator].append(fee)
    return [percentile_cont(own, 0.5) for own in by_creator.values()]


def agreed_cell(deals: Sequence[Deal]) -> AgreedCell:
    """One city, platform and format's agreed fees for a quarter."""
    if not enough_to_show(deals):
        return NOT_ENOUGH_AGREED
    barter = sum(1 for deal in deals if deal.fee_paise is None)
    shown = AgreedCell(
        deals=len(deals),
        creators=len({deal.creator for deal in deals}),
        brands=len({deal.brand for deal in deals}),
        # Half up, in whole numbers: 1 of 8 is 13%.
        barter_share_percent=(200 * barter + len(deals)) // (2 * len(deals)),
        lower_quarter_paise=None,
        median_paise=None,
        upper_quarter_paise=None,
    )
    paid = [deal for deal in deals if deal.fee_paise is not None]
    if not enough_to_show(paid):
        return shown
    medians = _per_creator_medians(
        [(deal.creator, deal.fee_paise) for deal in paid if deal.fee_paise is not None]
    )
    with_quarters = len(medians) >= AGREED_QUARTILES_MIN_CREATORS
    return AgreedCell(
        deals=shown.deals,
        creators=shown.creators,
        brands=shown.brands,
        barter_share_percent=shown.barter_share_percent,
        lower_quarter_paise=(
            round_paise(percentile_cont(medians, 0.25)) if with_quarters else None
        ),
        median_paise=round_paise(percentile_cont(medians, 0.5)),
        upper_quarter_paise=(
            round_paise(percentile_cont(medians, 0.75)) if with_quarters else None
        ),
    )
