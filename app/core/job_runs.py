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
   logged as `job.budget_spent`. An item started just before the budget
   ends still runs to its end, and an item makes several calls in turn,
   each with its own whole limit, so a run can last its budget plus one
   item's calls at their limits, as built today:

   | Job (budget) | One item's calls at their limits | Run at most |
   |---|---|---|
   | proof cleaning (45 s) | S3 describe, read, write, delete: 4 x 30 s | 165 s |
   | proof reading (45 s) | S3 read 30 s, Claude 150 s | 225 s |
   | brief drafting (45 s) | Claude 150 s | 195 s |
   | data exports (45 s) | one S3 destroy or write, 30 s | 75 s |
   | brand domain checks (45 s) | TXT at two resolvers 2 x 15 s, RDAP's file and the registry 2 x 15 s | 105 s |
   | account deletions (10 min) | S3 destroy 30 s for each export file the account still has | 600 s + 30 s a file |
   | daily checkpoint stamps (10 min) | two timestamp authorities, 2 x 15 s | 630 s |
   | connection refresh (10 min) | the platform's refresh and its profile, 2 x 15 s | 630 s |

   The database's own work adds to these, each statement held to its
   statement timeout. An S3 call that never answers ends within its 30 s
   by the client's own configuration (two tries, at most 28 s; 17.0 s
   measured on 18 November 2026, `app.core.storage`); it can outlast them
   only in the one way that module names and Adhi accepted on 15 November
   2026, so the S3 rows hold unless a store trickles its answer's headers
   a byte at a time. One run at a time
   (rule 1) keeps a long run from overlapping the next: those runs find
   the lock taken and do nothing.
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

# How soon a lock held by a lost host is let go. A crashed run's connection
# closes and its lock with it; a host that vanishes (its task stopped
# without a word, its network cut) closes nothing, and the database would
# keep the session, and the lock, until its operating system gave up on the
# connection: about 2 hours 11 minutes by Linux's defaults (tcp_keepalive_time
# 7200 s, then 9 probes 75 s apart). Asked to probe after 30 s of quiet, every
# 10 s, and to give up after 3 unanswered, the database ends the session
# within about a minute (30 + 3 x 10 = 60 s), so a schedule is held up by a
# lost run for a minute or two, not for hours. The same on our side (libpq's
# `keepalives_*`), so a database that vanishes is noticed as soon.
KEEPALIVE_IDLE_SECONDS = 30
KEEPALIVE_INTERVAL_SECONDS = 10
KEEPALIVE_COUNT = 3

# Its own connections, one per run while it lasts, never pooled: the lock is
# held for the whole run, and the API's pool is kept for requests (D-093).
# At most one per schedule holds a lock at a time, 12 across every
# container; a run that finds its schedule taken has one only for the try
# (docs/ARCHITECTURE_SCALE.md S9). A session's advisory lock needs the
# session itself, so behind a pooler in transaction mode (item 113) these
# must keep a session of their own (session mode, or straight to the
# database).
_lock_engine = create_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={
        "options": (
            f"-c statement_timeout={settings.db_statement_timeout_ms}"
            f" -c tcp_keepalives_idle={KEEPALIVE_IDLE_SECONDS}"
            f" -c tcp_keepalives_interval={KEEPALIVE_INTERVAL_SECONDS}"
            f" -c tcp_keepalives_count={KEEPALIVE_COUNT}"
        ),
        "keepalives": 1,
        "keepalives_idle": KEEPALIVE_IDLE_SECONDS,
        "keepalives_interval": KEEPALIVE_INTERVAL_SECONDS,
        "keepalives_count": KEEPALIVE_COUNT,
    },
)


@contextmanager
def one_run_at_a_time(schedule: str) -> Iterator[bool]:
    """True while this run holds the schedule's lock; False if another run does.

    The lock is let go by closing its connection, which `NullPool` really
    closes, however the run ends: a session's advisory locks end with it.
    """
    key = func.hashtext(schedule)
    with _lock_engine.connect() as lock:
        held = bool(
            lock.scalar(select(func.pg_try_advisory_lock(RUN_LOCK_NAMESPACE, key)))
        )
        # The lock is the session's: commit so no transaction stays open.
        lock.commit()
        if not held:
            logger.warning("job.already_running schedule=%s", schedule)
        yield held


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
