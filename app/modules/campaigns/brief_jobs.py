"""Drafting the waiting campaign briefs, and deleting week-old ones, as a scheduled DBOS workflow (item 40, D-156).

Every minute: drafts past their week go, then up to 10 waiting are drafted,
within the day's ceiling. DBOS records each run under an id fixed by its
scheduled minute, so two app instances never run the same one; within a
run, each draft is claimed by an advisory lock and written only if it still
waits, so even an overlap never drafts one twice.

The workflow's only input is the scheduled time: no brand's words pass
through DBOS's stored inputs (D-060 point 5).
"""

from datetime import datetime
from typing import Any

from dbos import DBOS, ScheduleInput

from app.db.session import SessionLocal
from app.modules.campaigns import brief_service
from app.modules.campaigns.brief_drafter import get_drafter

EVERY_MINUTE_CRON = "* * * * *"
SCHEDULE_NAME = "brief-drafts"


def run_drafting(scheduled_at: datetime) -> brief_service.DraftRun:
    """The work itself, callable without DBOS (tests, and a manual rerun)."""
    with SessionLocal() as db:
        return brief_service.run(db, get_drafter(), scheduled_at)


@DBOS.step(name="brief_drafts.run")
def drafting_step(scheduled_at: datetime) -> None:
    run_drafting(scheduled_at)


@DBOS.workflow(name="brief_drafts.draft")
def draft_briefs(scheduled_at: datetime, context: Any) -> None:
    drafting_step(scheduled_at)


def schedules() -> list[ScheduleInput]:
    return [
        {
            "schedule_name": SCHEDULE_NAME,
            "workflow_fn": draft_briefs,
            "schedule": EVERY_MINUTE_CRON,
            "automatic_backfill": False,
        }
    ]
