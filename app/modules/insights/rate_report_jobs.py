"""Building the quarterly city rate report, as a scheduled DBOS workflow (item 84, D-200).

Every day at 06:00 in Tamil Nadu, the last closed quarter's report is built
if it has none (`rate_report_service.build_due`). Daily rather than once at
each quarter's start, so a run missed while the app was down, or one that
failed, heals itself the next morning, with no catch-up logic to get wrong;
on every other day of the quarter the run finds the report already built
and does one small query.

A quarter that closed more than three days ago and still has no report means
the job has failed every morning since: that is logged as an error, which
reaches error tracking (D-074).

DBOS records each run under an id fixed by its scheduled time, so two app
instances never both run the same one; the unique quarter makes even an
overlap build one row. No backfill: the next run does what a missed one
would have. The workflow's only input is the scheduled time (D-060 point 5).
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from dbos import DBOS, ScheduleInput

from app.core.clock import india_date
from app.core.config import settings
from app.core.job_runs import run_alone
from app.db.session import SessionLocal
from app.modules.insights import rate_report_rules as rules
from app.modules.insights import rate_report_service

logger = logging.getLogger(__name__)

# 06:00 in Tamil Nadu is 00:30 UTC. India has no daylight saving, so a UTC
# cron is exact and needs no timezone database.
DAILY_CRON = "30 0 * * *"
SCHEDULE_NAME = "city-rate-report-build"
# How long after a quarter closes its report may be missing before it is an
# error someone must look at.
OVERDUE_AFTER = timedelta(days=3)


def _clock() -> datetime:
    return datetime.now(UTC)


def run_build(
    scheduled_at: datetime, clock: Callable[[], datetime] = _clock
) -> rate_report_service.BuildRun:
    """The work itself, callable without DBOS (tests, and a manual rerun).

    The scheduled time decides the quarter; the report says when it was
    really built, which `clock` tells (a retry runs later than scheduled).
    """
    try:
        with SessionLocal() as db:
            run = rate_report_service.build_due(
                db,
                scheduled_at,
                built_at=clock(),
                agreed_fees=settings.rate_report_agreed_fees,
            )
    except Exception:
        quarter = rules.last_closed_quarter(scheduled_at)
        closed_on = rules.quarter_days(quarter)[1] + timedelta(days=1)
        if india_date(scheduled_at) - closed_on >= OVERDUE_AFTER:
            logger.error("rate_report.overdue quarter=%s", quarter)
        raise
    logger.info("rate_report.run quarter=%s built=%s", run.quarter, run.built)
    return run


@DBOS.step(name="rate_report.build", retries_allowed=True, max_attempts=3)
def build_step(scheduled_at: datetime) -> None:
    # One step: building is idempotent, so a retry or a crash halfway is
    # safely redone. One run at a time per schedule (item 118, D-186).
    run_alone(SCHEDULE_NAME, lambda: run_build(scheduled_at))


@DBOS.workflow(name="rate_report.daily")
def build_rate_report(scheduled_at: datetime, context: Any) -> None:
    build_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": build_rate_report,
            "schedule": DAILY_CRON,
            "automatic_backfill": False,
        }
    ]
