"""Direct offers' expiry and erasure, as a scheduled DBOS workflow (D-189, D-060).

Every hour, at a quarter past: offers whose 14 days ran out are marked
expired, their number and name erased, and offers that ended without a deal
30 days ago are deleted (`direct_offer_service.expire_and_erase`). An hour
is the most a number outlives its offer's end. It calls nothing outside the
database, so item 118's limits on outside calls have nothing to bound here.
No backfill: each run takes up to 1,000 offers of each kind
(`direct_offer_service.JOB_BATCH`), oldest work first in no particular
order, and the next run takes the rest. Each run logs its counts, never a
number or a name.

The workflow's only input is the scheduled time: DBOS stores workflow
inputs in Postgres, so nothing personal may ever be passed in (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.deal_memo import direct_offer_service

HOURLY_CRON = "15 * * * *"
SCHEDULE_NAME = "direct-offers-expire-and-erase"


def run(scheduled_at: datetime) -> direct_offer_service.JobRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    with SessionLocal() as db:
        return direct_offer_service.expire_and_erase(db, scheduled_at)


@DBOS.step(name="direct_offers.expire_and_erase")
def expire_and_erase_step(scheduled_at: datetime) -> None:
    # One step: the work is idempotent, so a crash halfway is safely redone.
    run(scheduled_at)


@DBOS.workflow(name="direct_offers.hourly")
def hourly(scheduled_at: datetime, context: Any) -> None:
    expire_and_erase_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": hourly,
            "schedule": HOURLY_CRON,
            "automatic_backfill": False,
        }
    ]
