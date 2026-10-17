"""Making phone number changes once their 72 hours are over, as a scheduled DBOS workflow (item 80, D-108, D-060).

Every minute, every change whose wait is over is made, each in its own
transaction under both numbers' locks (phone_change_service.make_change).
DBOS records each run under an id fixed by its scheduled minute, so two app
instances never both run the same one; within a run, everything is checked
again under the locks, so even an overlap would not make a change twice.

No backfill: a minute missed while the app was down needs no replay, since
the next run finds every change still due.

The workflow's only input is the scheduled time. DBOS stores workflow inputs
in Postgres, so no phone number is ever passed in (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.me import phone_change_service

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "phone-changes-make"


def run_changes(scheduled_at: datetime) -> phone_change_service.ChangeRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    return phone_change_service.run_changes(SessionLocal, scheduled_at)


@DBOS.step(name="phone_changes.run")
def change_step(scheduled_at: datetime) -> None:
    # One step: each change is made in its own transaction, only if it is
    # still due, so a crash halfway is safely redone.
    run_changes(scheduled_at)


@DBOS.workflow(name="phone_changes.make")
def make_phone_changes(scheduled_at: datetime, context: Any) -> None:
    change_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": make_phone_changes,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
