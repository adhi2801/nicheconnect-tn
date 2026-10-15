"""Warning the admins about report deadlines, as a scheduled DBOS workflow (item 51, D-060).

Every 5 minutes, every open report due within 30 minutes, or past its
deadline unanswered, warns the admins once per stage
(report_clock_service.py). The shortest clock is 2 hours, so a report is
warned about between 25 and 30 minutes before its deadline, and within 5
minutes of passing it.

DBOS records each run under an id fixed by its scheduled time, so two app
instances never both run the same one; within a run, reports are taken with
SKIP LOCKED and marked as warned in the same transaction, so even an overlap
would not warn twice. No backfill: a run missed while the app was down needs
no replay, since the next run finds everything still owed a warning.

The workflow's only input is the scheduled time (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.admin import report_clock_service

EVERY_FIVE_MINUTES_CRON = "*/5 * * * *"
SCHEDULE_NAME = "report-clocks-warn"


def run_warnings(scheduled_at: datetime) -> report_clock_service.WarningRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    with SessionLocal() as db:
        return report_clock_service.warn_admins(db, scheduled_at)


@DBOS.step(name="report_clocks.warn_admins")
def warning_step(scheduled_at: datetime) -> None:
    # One step: each batch is its own transaction and a warned report is
    # never warned again, so a crash halfway is safely redone.
    run_warnings(scheduled_at)


@DBOS.workflow(name="report_clocks.warn")
def warn_about_report_deadlines(scheduled_at: datetime, context: Any) -> None:
    warning_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": warn_about_report_deadlines,
            "schedule": EVERY_FIVE_MINUTES_CRON,
            "automatic_backfill": False,
        }
    ]
