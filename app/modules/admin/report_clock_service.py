"""The report queue against its legal clocks (item 51, D-103).

Two jobs, both worked out from the report table as it stands:

- **Warning the admins.** A report nearing its deadline (report_clocks.DUE_SOON
  before it) and a report past it unanswered each warn every active admin
  once: an in-app notification that cannot be muted, and an error-level log
  line, which reaches the founders through error tracking (D-074) and stays
  in the logs kept 180 days (CERT-In). A clock nobody is told about is a
  clock that runs out; a 2-hour one can run out between two looks at the
  queue.
- **The figures.** How many are open, how many are late now, the next
  deadline, and how many answered in the last days were answered in time.

The warning is sent at most once per stage per report: the time it was sent
is written on the report in the same transaction as the notifications, and
the rows are taken with SKIP LOCKED, so two runs at once never warn twice and
never wait on each other. The log lines are written after the commit
(backend.md section 5): a run that fails to commit warns nobody, and the next
run tries again.

What a warning carries: the report's id, its category and its deadline.
Never the note, the reporter, or the reported side: that is for the queue,
behind the admin login.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.export import to_json_value
from app.modules.admin import report_clocks
from app.modules.admin.models.report import Report
from app.modules.auth.models.account import Account
from app.modules.notifications import service as notifications

logger = logging.getLogger(__name__)

# Reports warned about per transaction. A run keeps taking batches until one
# comes back short, so a burst is warned about in one run, a batch at a time;
# but never more than MAX_BATCHES, so a run always ends, even if a mark failed
# to stick: anything left is the next run's, 5 minutes later.
BATCH = 50
MAX_BATCHES = 20
MIN_SAMPLE = 5
MAX_DAYS = 90


_TEMPLATES = {
    "due_soon": "report.due_soon report_id=%s category=%s due_at=%s",
    "overdue": "report.overdue report_id=%s category=%s due_at=%s",
}


@dataclass(frozen=True)
class Warned:
    report_id: uuid.UUID
    stage: str  # "due_soon" or "overdue"
    category: str
    due_at: datetime


@dataclass(frozen=True)
class WarningRun:
    due_soon: int
    overdue: int


def _waiting_for_a_warning(now: datetime) -> Select[Report]:
    """Open reports owed a warning: due soon and not yet warned, or late and
    not yet warned that they are late. Served by ix_report_status_due_at."""
    return (
        select(Report)
        .where(
            Report.status == "open",
            Report.due_at <= now + report_clocks.DUE_SOON,
            or_(
                Report.due_soon_alerted_at.is_(None),
                # Late only once past it: answering at the deadline is in
                # time (report_clocks.is_late).
                and_(Report.overdue_alerted_at.is_(None), Report.due_at < now),
            ),
        )
        .order_by(Report.due_at, Report.id)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    )


def _active_admins(db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Account.id).where(
                Account.role == "admin", Account.suspended_at.is_(None)
            )
        ).all()
    )


def _warn_batch(db: Session, now: datetime) -> list[Warned]:
    """One batch, in one transaction. Returns what was warned about."""
    reports = list(db.scalars(_waiting_for_a_warning(now)).all())
    if not reports:
        db.rollback()
        return []
    admins = _active_admins(db)
    warned: list[Warned] = []
    for report in reports:
        if report.due_at < now:
            stage = "overdue"
            report.overdue_alerted_at = now
            # A report found already late (the job was down) is not also
            # warned as due soon: that moment has passed.
            if report.due_soon_alerted_at is None:
                report.due_soon_alerted_at = now
        else:
            stage = "due_soon"
            report.due_soon_alerted_at = now
        report.updated_at = now
        for admin_id in admins:
            notifications.record(
                db,
                account_id=admin_id,
                notification_type=f"report_{stage}",
                now=now,
                details={
                    "report_id": str(report.id),
                    "category": report.category,
                    "due_at": to_json_value(report.due_at),
                },
            )
        warned.append(Warned(report.id, stage, report.category, report.due_at))
    db.commit()
    return warned


def warn_admins(db: Session, now: datetime) -> WarningRun:
    """Warn about every report owed a warning at `now`. Safe to run twice."""
    due_soon = overdue = 0
    for _ in range(MAX_BATCHES):
        warned = _warn_batch(db, now)
        for item in warned:
            # Error level on purpose: it is what reaches the founders (D-074).
            # Ids and a category only, never a person (backend.md section 9).
            # One template per stage, so error tracking keeps "due soon" and
            # "late" as two issues rather than one.
            logger.error(
                _TEMPLATES[item.stage],
                item.report_id,
                item.category,
                to_json_value(item.due_at),
            )
            if item.stage == "overdue":
                overdue += 1
            else:
                due_soon += 1
        if len(warned) < BATCH:
            break
    return WarningRun(due_soon=due_soon, overdue=overdue)


# --- the figures ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClockFigures:
    as_of: datetime
    open: int
    open_late: int
    next_due_at: datetime | None
    days: int
    answered: int
    answered_in_time: int
    answered_in_time_share: float | None
    clocks: list[tuple[str, int]]


def figures(db: Session, *, now: datetime, days: int) -> ClockFigures:
    """The queue against its clocks, in one query. Totals only, so reading it
    names nobody and needs no entry in the admin log (D-061)."""
    since = now - timedelta(days=days)
    is_open = Report.status == "open"
    answered_recently = and_(~is_open, Report.resolved_at >= since)
    row = db.execute(
        select(
            func.count().filter(is_open),
            func.count().filter(is_open, Report.due_at < now),
            func.min(Report.due_at).filter(is_open),
            func.count().filter(answered_recently),
            func.count().filter(answered_recently, Report.resolved_at <= Report.due_at),
        )
    ).one()
    open_now, open_late, next_due_at, answered, in_time = row
    clocks = sorted(
        (
            (category, int(within.total_seconds() // 3600))
            for category, within in report_clocks.ANSWER_WITHIN.items()
        ),
        key=lambda pair: (pair[1], pair[0]),
    )
    return ClockFigures(
        as_of=now,
        open=open_now,
        open_late=open_late,
        next_due_at=next_due_at,
        days=days,
        answered=answered,
        answered_in_time=in_time,
        answered_in_time_share=(in_time / answered if answered >= MIN_SAMPLE else None),
        clocks=clocks,
    )
