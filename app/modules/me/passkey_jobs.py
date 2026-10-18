"""Settling passkey resets, and tidying challenges, as a scheduled DBOS workflow (D-113, D-060).

Every minute: a reset a passkey sign-in has cancelled is removed and the
owner told; one whose 7 days are over removes every passkey and turns
passkey-only off, and the owner is told; challenges expired a day or more
are deleted. DBOS records each run under an id fixed by its scheduled
minute; within a run each reset is settled under its row's lock, so even an
overlap would not settle one twice.

No backfill: the next run finds everything still due. The only input is the
scheduled time (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.me import passkey_service

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "passkey-resets-settle"


def run_resets(scheduled_at: datetime) -> passkey_service.ResetRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    return passkey_service.run_resets(SessionLocal, scheduled_at)


@DBOS.step(name="passkeys.settle_resets")
def settle_step(scheduled_at: datetime) -> None:
    run_resets(scheduled_at)


@DBOS.workflow(name="passkeys.settle")
def settle_passkey_resets(scheduled_at: datetime, context: Any) -> None:
    settle_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": settle_passkey_resets,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
