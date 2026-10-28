"""Reading cleaned proof files as a scheduled DBOS workflow (D-070, D-060).

Every minute, up to five cleaned files are read, checked and sealed, oldest
first. With reading switched off (the default, until the validation pack
answers) each run returns at once and calls nothing.

DBOS records each run under an id fixed by its scheduled minute, so two app
instances never run the same one; each file is also claimed with an advisory
lock, so even runs that overlap never read one file twice.

No backfill: a minute missed while the app was down needs no replay, since
the next run picks up everything still due. The workflow's only input is the
scheduled time; DBOS stores inputs in Postgres, so no file, account or key is
ever passed in (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.core.storage import get_file_store
from app.db.session import SessionLocal
from app.modules.deal_memo import proof_reading_service
from app.modules.deal_memo.proof_reader import get_reader

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "proof-files-read"


def run_reading(scheduled_at: datetime) -> proof_reading_service.ReadingRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    with SessionLocal() as db:
        return proof_reading_service.read_due(
            db, get_file_store(), get_reader(), scheduled_at
        )


@DBOS.step(name="proof_files.read_due")
def reading_step(scheduled_at: datetime) -> None:
    # One step: each file is its own transaction and a read file is never
    # due again, so a crash halfway is safely redone from where it stopped.
    run_reading(scheduled_at)


@DBOS.workflow(name="proof_files.read")
def read_proof_files(scheduled_at: datetime, context: Any) -> None:
    reading_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": read_proof_files,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
