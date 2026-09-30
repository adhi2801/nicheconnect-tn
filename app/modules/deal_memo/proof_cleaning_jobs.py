"""Cleaning proof files as a scheduled DBOS workflow (D-065, D-060).

Every minute, the files attached to proofs since the last run are cleaned,
up to 20 at a time. DBOS records each run under an id fixed by its scheduled
minute, so two app instances never both run the same one; within a run, each
file is locked with SKIP LOCKED, so even an overlap would not clean one twice.

No backfill: a minute missed while the app was down needs no replay, since
the next run picks up everything still queued.

The workflow's only input is the scheduled time. DBOS stores workflow inputs
in Postgres, so no file, account or key is ever passed in (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.core.storage import get_file_store
from app.db.session import SessionLocal
from app.modules.deal_memo import proof_cleaning_service

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "proof-files-clean"


def run_cleaning(scheduled_at: datetime) -> proof_cleaning_service.CleaningRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    with SessionLocal() as db:
        return proof_cleaning_service.clean_attached(db, get_file_store(), scheduled_at)


@DBOS.step(name="proof_files.clean_attached")
def cleaning_step(scheduled_at: datetime) -> None:
    # One step: each file is its own transaction and a cleaned file is never
    # queued again, so a crash halfway is safely redone from where it stopped.
    run_cleaning(scheduled_at)


@DBOS.workflow(name="proof_files.clean")
def clean_proof_files(scheduled_at: datetime, context: Any) -> None:
    cleaning_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": clean_proof_files,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
