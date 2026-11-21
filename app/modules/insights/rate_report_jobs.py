"""Building the quarterly city rate report, as a scheduled DBOS workflow (item 84, D-200).

Every day at 06:00 in Tamil Nadu, the last closed quarter's report is built
if it has none (`rate_report_service.build_due`). Daily rather than once at
each quarter's start, so a run missed while the app was down, or one that
failed, heals itself the next morning, with no catch-up logic to get wrong;
on every other day of the quarter the run finds the report already built
and does one small query.

Every run, whether its build succeeded, failed after its tries or did
nothing, then checks once (`rate_report_service.health`, a step of its own,
so the build's retries do not repeat it) and logs, as errors reaching error
tracking (D-074): every closed quarter with no report three days after it
closed, a quarter missed for longer than a quarter included (it is never
built late: its asking prices cannot be worked out again), in one line; and
every report built more than 14 days ago and still unpublished, in another.

DBOS records each run under an id fixed by its scheduled time, so two app
instances never both run the same one; the unique quarter makes even an
overlap build one row. No backfill: the next run does what a missed one
would have. The workflow's only input is the scheduled time (D-060 point 5).
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.core.config import settings
from app.core.job_runs import run_alone
from app.db.session import SessionLocal
from app.modules.auth.dependencies import get_now
from app.modules.insights import rate_report_service

logger = logging.getLogger(__name__)

# 06:00 in Tamil Nadu is 00:30 UTC. India has no daylight saving, so a UTC
# cron is exact and needs no timezone database.
DAILY_CRON = "30 0 * * *"
SCHEDULE_NAME = "city-rate-report-build"


def run_build(
    scheduled_at: datetime, clock: Callable[[], datetime] = get_now
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
    except Exception as error:
        # A try failing is a warning: DBOS tries again, and the run's check
        # says whether a report is really overdue.
        logger.warning("rate_report.run_failed error=%s", type(error).__name__)
        raise
    logger.info("rate_report.run quarter=%s built=%s", run.quarter, run.built)
    return run


def run_check(scheduled_at: datetime) -> rate_report_service.Health:
    """Log, once, what someone must look at (see the module's notes)."""
    with SessionLocal() as db:
        found = rate_report_service.health(db, scheduled_at)
    if found.overdue:
        logger.error("rate_report.overdue quarters=%s", ",".join(found.overdue))
    if found.unpublished:
        logger.error(
            "rate_report.unpublished quarters=%s days=%d",
            ",".join(found.unpublished),
            rate_report_service.UNPUBLISHED_AFTER.days,
        )
    return found


@DBOS.step(name="rate_report.build", retries_allowed=True, max_attempts=3)
def build_step(scheduled_at: datetime) -> None:
    # One step: building is idempotent, so a retry or a crash halfway is
    # safely redone. One run at a time per schedule (item 118, D-186).
    run_alone(SCHEDULE_NAME, lambda: run_build(scheduled_at))


@DBOS.step(name="rate_report.check")
def check_step(scheduled_at: datetime) -> None:
    run_check(scheduled_at)


@DBOS.workflow(name="rate_report.daily")
def build_rate_report(scheduled_at: datetime, context: Any) -> None:
    try:
        build_step(scheduled_at)
    finally:
        # Once a run, after the build's last try, whether it worked or not.
        check_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": build_rate_report,
            "schedule": DAILY_CRON,
            "automatic_backfill": False,
        }
    ]
