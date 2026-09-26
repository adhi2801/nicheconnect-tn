"""The daily checkpoint as a scheduled DBOS workflow (D-060).

DBOS runs this inside the app at 00:10 in Tamil Nadu. The ten minutes let
any transaction still open at midnight commit before its entries are
counted. DBOS records each run under a deterministic id for its scheduled
time, so two app instances never both run it, and with `automatic_backfill`
a day missed while the app was down is run when it comes back.

The workflow's only input is the scheduled time: DBOS stores workflow
inputs in Postgres, so nothing personal may ever be passed in (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.deal_memo import anchor_service
from app.modules.deal_memo.timestamp_authority import default_authorities

# 00:10 in Tamil Nadu is 18:40 UTC the day before. India has no daylight
# saving, so a UTC cron is exact and needs no timezone database.
DAILY_CHECKPOINT_CRON = "40 18 * * *"
SCHEDULE_NAME = "deal-record-daily-checkpoint"


def run_checkpoint(scheduled_at: datetime) -> anchor_service.DailyRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    with SessionLocal() as db:
        return anchor_service.run_daily(db, scheduled_at, default_authorities())


@DBOS.step(name="deal_record.checkpoint_and_stamp")
def checkpoint_step(scheduled_at: datetime) -> None:
    # One step: run_daily is idempotent, so a crash halfway is safely redone,
    # and the timestamp client already retries within backend.md's limits.
    run_checkpoint(scheduled_at)


@DBOS.workflow(name="deal_record.daily_checkpoint")
def daily_checkpoint(scheduled_at: datetime, context: Any) -> None:
    checkpoint_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": daily_checkpoint,
            "schedule": DAILY_CHECKPOINT_CRON,
            "automatic_backfill": True,
        }
    ]
