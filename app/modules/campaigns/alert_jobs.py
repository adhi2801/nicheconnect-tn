"""Sending campaign alerts as a scheduled DBOS workflow (item 43, D-130, D-060).

Every minute, the campaigns published since the last run have their
alerts sent (`alert_service.send_due`): a campaign is told to the
creators whose alert fits within about a minute of going live, never
inside the request that published it.

DBOS records each run under an id fixed by its scheduled minute, so two
app instances never run the same one; batches also take one advisory
lock, and a creator already told about a campaign is never told again, so
even runs that overlap tell nobody twice.

No backfill: a minute missed while the app was down needs no replay, since
the next run finds every send still due. The workflow's only input is the
scheduled time; DBOS stores inputs in Postgres, so no account or campaign
is ever passed in (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.campaigns import alert_service

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "campaign-alerts-send"


def run_sending(scheduled_at: datetime) -> alert_service.AlertRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    return alert_service.send_due(SessionLocal, scheduled_at)


@DBOS.step(name="campaign_alerts.send_due")
def sending_step(scheduled_at: datetime) -> None:
    # One step: each batch is its own transaction and nobody is told twice,
    # so a crash halfway is safely redone from where it stopped.
    run_sending(scheduled_at)


@DBOS.workflow(name="campaign_alerts.send")
def send_campaign_alerts(scheduled_at: datetime, context: Any) -> None:
    sending_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": send_campaign_alerts,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
