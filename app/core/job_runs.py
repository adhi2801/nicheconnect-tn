"""How a background job's run is bounded (item 118, D-186).

Two rules for every job whose step calls the outside world (S3, the Claude
API, WhatsApp, the DNS and RDAP lookups, Instagram and YouTube, the
timestamp authorities):

1. **One run at a time per schedule.** DBOS starts a run at every scheduled
   moment, so a run still working when the next minute comes would overlap
   it, and with an outside service slow, runs would pile up, each holding a
   database connection from the pool requests use (D-093). `one_run_at_a_time`
   takes a session advisory lock named for the schedule, without waiting: a
   run that finds it held logs `job.already_running` and does nothing. The
   lock is the database's, so it holds across every app instance, and it is
   released when its connection closes, so a crashed run never leaves it.
2. **A budget per run.** Once the run's budget is spent no new item is
   started (`within_budget`), and what is left waits for the next run, logged
   as `job.budget_spent`. Each item already holds its own limits, so a run
   ends at most one item's limit after its budget.
"""

import logging
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from sqlalchemy import func, select

from app.core.deadline import Deadline
from app.db.session import engine

logger = logging.getLogger(__name__)


# The advisory lock's first key, for job runs only; the others in use are
# 40 (brief drafts) and 70_070 (proof readings), each per item.
RUN_LOCK_NAMESPACE = 118
# A job scheduled every minute: done well before the next run is due.
EVERY_MINUTE_BUDGET_SECONDS = 45.0
# A job run every 15 minutes or once a day: still done before the next.
LONG_BUDGET_SECONDS = 600.0


@contextmanager
def one_run_at_a_time(schedule: str) -> Iterator[bool]:
    """True while this run holds the schedule's lock; False if another run does."""
    with engine.connect() as lock:
        key = func.hashtext(schedule)
        held = bool(
            lock.scalar(select(func.pg_try_advisory_lock(RUN_LOCK_NAMESPACE, key)))
        )
        # The lock is the session's: commit so no transaction stays open.
        lock.commit()
        if not held:
            logger.warning("job.already_running schedule=%s", schedule)
            yield False
            return
        try:
            yield True
        finally:
            lock.execute(select(func.pg_advisory_unlock(RUN_LOCK_NAMESPACE, key)))
            lock.commit()


def within_budget[T](
    items: Iterable[T], budget: Deadline | None, job: str
) -> Iterator[T]:
    """The items, one by one, until `budget` is spent. None is no budget (a test or a rerun)."""
    queue = list(items)
    for done, item in enumerate(queue):
        if budget is not None and budget.expired():
            logger.warning("job.budget_spent job=%s left=%d", job, len(queue) - done)
            return
        yield item
