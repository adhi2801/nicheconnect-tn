"""Keeping connected accounts current, as a daily DBOS workflow (item 29, D-134, D-060).

At 08:00 Tamil Nadu time every active connection is renewed if due and
read again (`profiles.connection_refresh_service`). The job sits here, in
`me`, because a connection that expires tells its creator, and `profiles`
may not reach `notifications` (they are siblings, backend.md section 1):
the notice is recorded in the same transaction that marks it expired, so
the creator hears exactly once.

DBOS records each run under an id fixed by its scheduled time, so two app
instances never both run it. No backfill: a day missed needs no replay,
since tokens are renewed 30 days before they lapse. The workflow's only
input is the scheduled time (D-060 point 5). Off, it reads nothing.
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.auth.models.creator import Creator
from app.modules.notifications import service as notifications
from app.modules.profiles import connection_refresh_service as refresh
from app.modules.profiles.connection_models import ConnectedAccount

# 02:30 UTC is 08:00 in Tamil Nadu: a notice that arrives in the morning.
DAILY_CRON = "30 2 * * *"
SCHEDULE_NAME = "connections-refresh"


def tell_creator(db: Session, connection: ConnectedAccount) -> None:
    """The creator's notice that a connection stopped working. Never commits."""
    account_id = db.scalar(
        select(Creator.account_id).where(Creator.id == connection.creator_id)
    )
    if account_id is None:
        return
    notifications.record(
        db,
        account_id=account_id,
        notification_type="connection_expired",
        now=connection.updated_at,
        details={"platform": connection.platform},
    )


def run_refresh(scheduled_at: datetime) -> refresh.RefreshRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    return refresh.refresh_all(SessionLocal, scheduled_at, tell_creator)


@DBOS.step(name="connections.refresh_all")
def refresh_step(scheduled_at: datetime) -> None:
    # One step: each connection is its own transactions, and one already
    # read today is simply read again, so a crash halfway is safely redone.
    run_refresh(scheduled_at)


@DBOS.workflow(name="connections.refresh")
def refresh_connections(scheduled_at: datetime, context: Any) -> None:
    refresh_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": refresh_connections,
            "schedule": DAILY_CRON,
            "automatic_backfill": False,
        }
    ]
