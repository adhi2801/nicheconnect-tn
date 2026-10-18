"""Building data exports, and destroying unclaimed ones, as a scheduled DBOS workflow (D-111, D-060).

Every minute: up to 10 exports asked for are built and their owners told,
and every file 24 hours past ready and never downloaded is destroyed. DBOS
records each run under an id fixed by its scheduled minute, so two app
instances never both run the same one; within a run, an export is marked
ready only if it still waits, so even an overlap would not mark one twice.

No backfill: a minute missed while the app was down needs no replay, since
the next run finds everything still waiting or due.

The workflow's only input is the scheduled time. DBOS stores workflow inputs
in Postgres, so no account's data ever passes through them (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.core.storage import get_file_store
from app.db.session import SessionLocal
from app.modules.me import data_export_service

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "data-exports-build"


def run_exports(scheduled_at: datetime) -> data_export_service.ExportRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    return data_export_service.run_exports(SessionLocal, get_file_store(), scheduled_at)


@DBOS.step(name="data_exports.run")
def export_step(scheduled_at: datetime) -> None:
    # One step: each export is built and marked in its own transactions,
    # only while it still waits, so a crash halfway is safely redone.
    run_exports(scheduled_at)


@DBOS.workflow(name="data_exports.build")
def build_data_exports(scheduled_at: datetime, context: Any) -> None:
    export_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": build_data_exports,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
