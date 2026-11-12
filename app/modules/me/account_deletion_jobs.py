"""Erasing accounts once their 30 days are over, as a scheduled DBOS workflow (item 6, D-122, D-060).

Every 15 minutes, every account whose wait is over is erased, each in its
own transaction under its locks (account_deletion_service.erase). A
deletion takes effect within 15 minutes of its date, a delay nobody waiting
30 days notices, for a quarter of the runs. DBOS records each run under an
id fixed by its scheduled time, so two app instances never both run the
same one; within a run, everything is checked again under the locks, so
even an overlap would not erase an account twice.

No backfill: a run missed while the app was down needs no replay, since
the next run finds every account still due.

The workflow's only input is the scheduled time. DBOS stores workflow inputs
in Postgres, so no account's data ever passes through them (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.core.deadline import Deadline
from app.core.job_runs import LONG_BUDGET_SECONDS, run_alone
from app.core.storage import get_file_store
from app.db.session import SessionLocal
from app.modules.me import account_deletion_service

EVERY_15_MINUTES_CRON = "*/15 * * * *"
SCHEDULE_NAME = "account-deletions-erase"


def run_deletions(
    scheduled_at: datetime, budget: Deadline | None = None
) -> account_deletion_service.DeletionRun:
    """The work itself, callable without DBOS (tests, and a manual rerun).

    No budget unless one is given: the scheduled step gives its own.
    """
    return account_deletion_service.run_deletions(
        SessionLocal, get_file_store(), scheduled_at, budget=budget
    )


@DBOS.step(name="account_deletions.run")
def deletion_step(scheduled_at: datetime) -> None:
    # One step: each account is erased in its own transaction, only if it
    # is still due, so a crash halfway is safely redone.
    # One run at a time per schedule (item 118, D-186).
    run_alone(
        SCHEDULE_NAME, lambda: run_deletions(scheduled_at, Deadline(LONG_BUDGET_SECONDS))
    )


@DBOS.workflow(name="account_deletions.erase")
def erase_accounts(scheduled_at: datetime, context: Any) -> None:
    deletion_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": erase_accounts,
            "schedule": EVERY_15_MINUTES_CRON,
            "automatic_backfill": False,
        }
    ]
