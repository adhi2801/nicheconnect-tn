"""The free quarterly city rate report (item 84, D-200): built, read, published.

One report a closed quarter, in the Tamil Nadu calendar. A daily job builds
the last closed quarter's report if it has none (`build_due`); it starts
unpublished, an admin publishes it after reading it, and from then on the
database refuses any change to what it says (`rate_report_models`). Readers
see published reports only; a withdrawn one answers 410 with why.

Why a stored snapshot, when every other figure in `insights` is worked out
on read (backend.md section 2): rate cards are edited in place, so a past
quarter's asking prices cannot be worked out again, and a figure someone
quoted must never change under them (D-200, Decision 3).

What the report counts, and the floors, are `rate_report_rules` and
`rate_report_figures`, written up in plain English in
`docs/RATE_REPORT_METHOD.md`. The agreed-fee section is built only while
`RATE_REPORT_AGREED_FEES` is on, and is off (D-200, Decision 1): D-078 says
no public figure is built from a deal until a founder amends it.

Nothing here names anyone: the body holds counts and rounded figures only.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.insights import rate_report_figures as figures
from app.modules.insights import rate_report_rules as rules
from app.modules.insights.exceptions import (
    RateReportAlreadyPublished,
    RateReportAlreadyWithdrawn,
    RateReportNotBuilt,
    RateReportNotFound,
    RateReportNotPublished,
    RateReportWithdrawn,
)
from app.modules.insights.rate_guidance_service import AUDIENCE_BANDS
from app.modules.insights.rate_report_models import CityRateReport
from app.modules.insights.rate_report_schemas import (
    AgreedCellRead,
    AskingCellRead,
    AudienceBandCellRead,
    CityRatesRead,
    MinCountsRead,
    RateReportBody,
)
from app.modules.profiles.models import CHANNEL_PLATFORMS, PACKAGE_FORMATS

METHOD_URL = (
    "https://github.com/adhi2801/nicheconnect-tn/blob/main/docs/RATE_REPORT_METHOD.md"
)
# Every platform and format, in one fixed order, so every city's table has
# the same rows and a missing figure is a visible null, never a missing row.
CELLS: tuple[tuple[str, str], ...] = tuple(
    (platform, package_format)
    for platform in CHANNEL_PLATFORMS
    for package_format in PACKAGE_FORMATS
)


def canonical_json(body: dict[str, Any]) -> bytes:
    """The bytes the fingerprint is taken over: keys sorted, no spaces, and
    plain ASCII, any other letter written as JSON's `\\uXXXX` escape (its
    own), so the bytes are the same whatever a reader's tools do with text."""
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def fingerprint(body: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(body)).hexdigest()


def _asking(platform: str, package_format: str, cell: rules.AskingCell) -> AskingCellRead:
    return AskingCellRead.model_validate(
        {
            "platform": platform,
            "format": package_format,
            "creators": cell.creators,
            "lower_quarter_paise": cell.lower_quarter_paise,
            "median_paise": cell.median_paise,
            "upper_quarter_paise": cell.upper_quarter_paise,
        }
    )


def _agreed(platform: str, package_format: str, cell: rules.AgreedCell) -> AgreedCellRead:
    return AgreedCellRead.model_validate(
        {
            "platform": platform,
            "format": package_format,
            "deals": cell.deals,
            "creators": cell.creators,
            "brands": cell.brands,
            "barter_share_percent": cell.barter_share_percent,
            "lower_quarter_paise": cell.lower_quarter_paise,
            "median_paise": cell.median_paise,
            "upper_quarter_paise": cell.upper_quarter_paise,
        }
    )


def build_body(
    db: Session, quarter: str, built_at: datetime, *, agreed_fees: bool
) -> RateReportBody:
    """One quarter's figures, as they stand at `built_at`.

    A fixed number of queries however many cities there are: the cities,
    asking prices by city, asking prices by audience band, and, when
    `agreed_fees`, the deals of the quarter. Raises NotAQuarter.
    """
    first_day, last_day = rules.quarter_days(quarter)
    cities = figures.listed_cities(db)
    keys = [city.key for city in cities]
    asking = figures.asking_by_city(db, keys)
    bands = figures.asking_by_band(db)
    deals: dict[figures.CellKey, list[rules.Deal]] | None = None
    if agreed_fees:
        start, end = rules.quarter_window(quarter)
        deals = figures.agreed_by_city(db, keys, start, end)

    city_rows = [
        CityRatesRead(
            city=city.name,
            asking_prices=[
                _asking(
                    platform,
                    package_format,
                    asking.get(
                        (city.key, platform, package_format), rules.NOT_ENOUGH_ASKING
                    ),
                )
                for platform, package_format in CELLS
            ],
            agreed_fees=None
            if deals is None
            else [
                _agreed(
                    platform,
                    package_format,
                    rules.agreed_cell(
                        deals.get((city.key, platform, package_format), [])
                    ),
                )
                for platform, package_format in CELLS
            ],
        )
        for city in cities
    ]
    band_rows = []
    for band, _low, _high in AUDIENCE_BANDS:
        for platform, package_format in CELLS:
            found = bands.get((band, platform, package_format))
            cell = found.cell if found is not None else rules.NOT_ENOUGH_ASKING
            band_rows.append(
                AudienceBandCellRead.model_validate(
                    {
                        "audience_band": band,
                        "platform": platform,
                        "format": package_format,
                        "creators": cell.creators,
                        "lower_quarter_paise": cell.lower_quarter_paise,
                        "median_paise": cell.median_paise,
                        "upper_quarter_paise": cell.upper_quarter_paise,
                        "audience_figures_from": None
                        if found is None
                        else found.audience_figures_from,
                    }
                )
            )
    return RateReportBody(
        quarter=quarter,
        method_version=rules.METHOD_VERSION,
        period_from=first_day,
        period_to=last_day,
        as_of=india_date(built_at),
        min_counts=MinCountsRead(
            asking_creators=rules.ASKING_MIN_CREATORS,
            agreed_deals=rules.AGREED_MIN_DEALS,
            agreed_creators=rules.AGREED_MIN_CREATORS,
            agreed_brands=rules.AGREED_MIN_BRANDS,
            agreed_max_brand_share_percent=rules.AGREED_MAX_BRAND_SHARE_PERCENT,
            agreed_quartiles_creators=rules.AGREED_QUARTILES_MIN_CREATORS,
            rounded_to_paise=rules.ROUND_TO_PAISE,
        ),
        agreed_fees_included=agreed_fees,
        cities=city_rows,
        audience_bands=band_rows,
    )


@dataclass(frozen=True)
class BuildRun:
    quarter: str
    built: bool


def build_due(
    db: Session, now: datetime, *, built_at: datetime, agreed_fees: bool
) -> BuildRun:
    """Build the last closed quarter's report, unless it has one. Commits.

    `now` is the run's scheduled time, which decides the quarter, so a run
    retried or delayed past midnight still builds the quarter it was for;
    `built_at` is the clock's time as the figures are read, which the report
    states (`built_at`, and `as_of`, its day).

    Idempotent: a quarter already built is left as it is, and two runs at
    once leave one row, since the second insert does nothing on the unique
    quarter (`ON CONFLICT DO NOTHING`). A quarter is never rebuilt: what was
    true when it closed is what it says.
    """
    quarter = rules.last_closed_quarter(now)
    if db.scalar(select(CityRateReport.id).where(CityRateReport.quarter == quarter)):
        return BuildRun(quarter=quarter, built=False)
    body = build_body(db, quarter, built_at, agreed_fees=agreed_fees).model_dump(
        mode="json"
    )
    inserted = db.execute(
        insert(CityRateReport)
        .values(
            quarter=quarter,
            method_version=rules.METHOD_VERSION,
            body=body,
            body_sha256=fingerprint(body),
            built_at=built_at,
            created_at=built_at,
            updated_at=built_at,
        )
        .on_conflict_do_nothing()
        .returning(CityRateReport.id)
    ).scalar()
    db.commit()
    return BuildRun(quarter=quarter, built=inserted is not None)


# --- reading ----------------------------------------------------------------------------


def published(db: Session, *, limit: int, cursor: str | None) -> Slice[CityRateReport]:
    """Published reports, newest first, withdrawn ones included (they say so).

    A report is built once its quarter has closed, so the order they were
    built in is the quarters' order. One query.
    """
    query = (
        select(CityRateReport)
        .where(CityRateReport.published_at.is_not(None))
        .order_by(CityRateReport.created_at.desc(), CityRateReport.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        query = query.where(
            older_than_cursor(CityRateReport.created_at, CityRateReport.id, cursor)
        )
    return build_slice(
        list(db.scalars(query)), limit, key=lambda row: (row.created_at, row.id)
    )


def read_published(db: Session, quarter: str) -> CityRateReport:
    """One published report. Raises RateReportNotFound for a quarter with no
    published report (an unpublished one included), and RateReportWithdrawn,
    with the reason, for one withdrawn."""
    report = db.scalar(
        select(CityRateReport).where(
            CityRateReport.quarter == quarter, CityRateReport.published_at.is_not(None)
        )
    )
    if report is None:
        raise RateReportNotFound()
    if report.withdrawn_at is not None:
        raise RateReportWithdrawn(report.withdrawn_reason)
    return report


# --- publishing and withdrawing (the admin API's, which logs and commits) -------------


def _locked(db: Session, quarter: str) -> CityRateReport:
    report = db.scalar(
        select(CityRateReport)
        .where(CityRateReport.quarter == quarter)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if report is None:
        db.rollback()
        raise RateReportNotBuilt()
    return report


def publish(
    db: Session, admin_account_id: uuid.UUID, quarter: str, now: datetime
) -> CityRateReport:
    """Publish a built report. Does not commit: the caller logs it first.

    The row is locked before it is checked, so two admins at once publish it
    once, and the other is told it already is. Raises RateReportNotBuilt and
    RateReportAlreadyPublished.
    """
    report = _locked(db, quarter)
    if report.published_at is not None:
        db.rollback()
        raise RateReportAlreadyPublished()
    report.published_at = now
    report.published_by_account_id = admin_account_id
    report.updated_at = now
    return report


def withdraw(db: Session, quarter: str, reason: str, now: datetime) -> CityRateReport:
    """Withdraw a published report, once, with the reason readers are shown.
    Does not commit: the caller logs it first.

    Raises RateReportNotBuilt, RateReportNotPublished and
    RateReportAlreadyWithdrawn.
    """
    report = _locked(db, quarter)
    if report.published_at is None:
        db.rollback()
        raise RateReportNotPublished()
    if report.withdrawn_at is not None:
        db.rollback()
        raise RateReportAlreadyWithdrawn()
    report.withdrawn_at = now
    report.withdrawn_reason = reason
    report.updated_at = now
    return report
