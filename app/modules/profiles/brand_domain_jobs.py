"""Checking brands' domains, as a scheduled DBOS workflow (item 74, D-106, D-060).

Every minute, up to 20 claims are checked: those a brand asked to have
checked, and verified ones a day after their last check. DBOS records each
run under an id fixed by its scheduled minute, so two app instances never
both run the same one; within a run, claims are taken under SKIP LOCKED with
a lease, so even an overlap would not check one twice.

No backfill: a minute missed while the app was down needs no replay, since
the next run picks up everything still due.

The workflow's only input is the scheduled time. DBOS stores workflow inputs
in Postgres, so no domain or token is ever passed in (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.profiles import brand_domain_service
from app.modules.profiles.domain_lookup import get_domain_lookup

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "brand-domains-check"


def run_checks(scheduled_at: datetime) -> brand_domain_service.CheckRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    return brand_domain_service.run_checks(
        SessionLocal, get_domain_lookup(), scheduled_at
    )


@DBOS.step(name="brand_domains.run_checks")
def checking_step(scheduled_at: datetime) -> None:
    # One step: each claim is applied in its own transaction, only if it
    # still has the token looked up, so a crash halfway is safely redone.
    run_checks(scheduled_at)


@DBOS.workflow(name="brand_domains.check")
def check_brand_domains(scheduled_at: datetime, context: Any) -> None:
    checking_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": check_brand_domains,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
