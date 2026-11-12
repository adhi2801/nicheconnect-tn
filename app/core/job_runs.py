"""How a background job's run is bounded (item 118, D-186).

Two rules, after Google SRE's "Addressing Cascading Failures" (a deadline
set once and "check the deadline left at each stage before attempting any
more work"):

1. **One run at a time per schedule**, for every schedule. DBOS starts a run
   at every scheduled moment, so a run still working when the next minute
   comes would overlap it, and with an outside service slow, runs would pile
   up, each holding a database connection from the pool requests use
   (D-093). `run_alone` takes a session advisory lock named for the
   schedule, without waiting: a run that finds it held logs
   `job.already_running` and does nothing. The lock is the database's, so it
   holds across every app instance; it is released when its connection
   closes, so a crashed run never leaves it behind; and it is taken on a
   connection of its own, outside the pool requests use (`_lock_engine`),
   so holding it for a whole run never takes a place a request needs.
   Never waiting is also why it cannot deadlock with anything, account
   erasure included: a lock that is only ever tried is never waited on.
2. **A budget per run**, for every job whose step calls the outside world
   (S3, the Claude API, the DNS and RDAP lookups, Instagram and YouTube,
   the timestamp authorities). Once the run's budget is spent no new item
   is started (`within_budget`), and what is left waits for the next run,
   logged as `job.budget_spent`. Each item already holds its own limits, so
   a run ends at most one item's limit after its budget.
"""

import logging
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.deadline import Deadline

logger = logging.getLogger(__name__)

# The advisory lock's first key, for job runs only. The other two-key locks
# in use are 40 (brief drafts) and 70_070 (proof readings); the one-key locks
# (each phone's, campaign alerts') never meet a two-key one (PostgreSQL 18,
# "Advisory Lock Functions").
RUN_LOCK_NAMESPACE = 118
# A job scheduled every minute: done well before the next run is due.
EVERY_MINUTE_BUDGET_SECONDS = 45.0
# A job run every 15 minutes or once a day: still done before the next.
LONG_BUDGET_SECONDS = 600.0

# Its own connections, one per run while it lasts, never pooled: the lock is
# held for the whole run, and the API's pool is kept for requests (D-093).
_lock_engine = create_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={"options": f"-c statement_timeout={settings.db_statement_timeout_ms}"},
)


@contextmanager
def one_run_at_a_time(schedule: str) -> Iterator[bool]:
    """True while this run holds the schedule's lock; False if another run does."""
    key = func.hashtext(schedule)
    with _lock_engine.connect() as lock:
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


def run_alone(schedule: str, work: Callable[[], object]) -> bool:
    """Do `work` unless another run of `schedule` is under way. True if it ran."""
    with one_run_at_a_time(schedule) as mine:
        if mine:
            work()
        return mine


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
