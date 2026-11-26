"""The monthly restore test: is the backup a database the app can run on? (item 90, D-205)

GitLab lost about 5,000 projects in 2017 because every backup method had
silently failed and nobody tested a restore (`docs/standards/database.md`
section 0). So on the 1st of each month, at 02:30 in Tamil Nadu, a task of
its own (`infra/modules/app/restore_check.tf`) runs `python -m
app.db.restore_check`, which:

1. deletes any copy an earlier run left behind;
2. restores this environment's database, to its latest restorable moment
   (every third month, to a random second in the window instead), into a
   private, encrypted scratch copy (`app/db/restore_copy.py`);
3. checks the copy against production, both read as the app's own login:
   the migration version is this image's head; pgvector is 0.8.2 or later;
   DBOS's schema is there; the login holds item 97's rights, no more and no
   fewer; each sealed table holds exactly production's rows made up to 10
   minutes before the restore moment (count and md5); every other table at
   least production's rows made by then, and at most 1% more (rows
   production has deleted since);
4. measures the recovery time (asking for the restore to a checked copy) and
   the data that would have been lost (the request to the latest restorable
   moment) against D-168's targets, 1 hour and 5 minutes;
5. deletes the copy, with no final snapshot, whatever happened, and stops
   waiting at 90 minutes;
6. writes one result line, and checks in with Sentry's cron monitor, so a
   failure, a missed target or a run that never happened is an alert.

Nothing read leaves AWS: the line and the check-in hold numbers, table names
and the names of the checks that failed, never a row or a hash's input.
"""

import json
import logging
import random
import secrets
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import boto3
import sentry_sdk
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from botocore.config import Config
from sentry_sdk.crons import MonitorStatus, capture_checkin
from sqlalchemy import Connection, create_engine, make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.core.clock import india_date
from app.core.config import Settings, settings
from app.core.deadline import Deadline, DeadlinePassed
from app.core.error_tracking import init_error_tracking
from app.core.jobs import DBOS_SCHEMA
from app.core.structured_logs import configure_logging
from app.db.prepare import alembic_config
from app.db.restore_copy import Copy, CopyFailed, CopyNotReady, RestoreCopies
from app.db.roles import APP_WRITER

logger = logging.getLogger(__name__)

# D-168's recovery targets, and the run's own limit.
RTO_TARGET = timedelta(hours=1)
RPO_TARGET = timedelta(minutes=5)
TIME_LIMIT = timedelta(minutes=90)
# Rows made this close to the restore moment may be in production and not
# yet in the copy (a transaction's clock starts before it commits).
SETTLE = timedelta(minutes=10)
# How many more rows the copy may hold than production, for the same rows:
# the ones production deleted since the restore moment.
DRIFT = 0.01
PGVECTOR_FLOOR = (0, 8, 2)
# The seven append-only tables (database.md section 3, item 97's SEALED),
# and the one never deleted from (item 52).
SEALED = frozenset(
    {
        "admin_action",
        "deal_feedback",
        "deal_note",
        "deal_record_checkpoint",
        "deal_record_entry",
        "deal_record_timestamp",
        "dispute_event",
    }
)
KEPT = frozenset({"takedown"})
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
# Each table's moment of making; a table with neither is compared whole.
MADE_AT = ("created_at", "recorded_at")
MONITOR_SLUG = "restore-check"
MONITOR_CONFIG = {
    "schedule": {"type": "crontab", "value": "30 2 1 * *"},
    "timezone": "Asia/Kolkata",
    "checkin_margin": 30,
    "max_runtime": 120,
    "failure_issue_threshold": 1,
    "recovery_threshold": 1,
}
# RDS answers in seconds; botocore's standard retry mode, three tries.
RDS_CONFIG = Config(
    connect_timeout=3, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"}
)


class NotConfigured(RuntimeError):
    """The task's three settings are not all set."""


@dataclass(frozen=True)
class Outcome:
    """What one run found and measured."""

    problems: list[str]
    restore_time: datetime
    latest: bool
    rto: timedelta | None
    rpo: timedelta
    swept: int

    @property
    def ok(self) -> bool:
        return not self.problems


# --- pure rules -----------------------------------------------------------------------


def expected_rights(table: str) -> tuple[bool, ...]:
    """Item 97's rights on one table, in PRIVILEGES' order."""
    if table == "alembic_version":
        return (True, False, False, False, False, False, False)
    if table in SEALED:
        return (True, True, False, False, False, False, False)
    if table in KEPT:
        return (True, True, True, False, False, False, False)
    return (True, True, True, True, False, False, False)


def version_at_least(found: str, floor: tuple[int, ...]) -> bool:
    """Whether a dotted version is the floor or later; an unreadable one is not."""
    try:
        parts = tuple(int(part) for part in found.split("."))
    except ValueError:
        return False
    return parts >= floor


def count_problem(table: str, production: int, copy: int) -> str | None:
    """A table's rows made before the cut-off: the copy holds production's, at most 1% more."""
    if copy < production:
        return f"rows: {table} has {copy} in the copy, {production} in production"
    if copy > production * (1 + DRIFT):
        return f"rows: {table} has {copy} in the copy, over 1% more than {production}"
    return None


def setting_problems(copy: Copy) -> list[str]:
    """The copy is private, encrypted, deletable and keeps no backups of its own."""
    problems = []
    if copy.public:
        problems.append("copy: publicly accessible")
    if not copy.encrypted:
        problems.append("copy: not encrypted")
    if copy.deletion_protection:
        problems.append("copy: deletion protection on")
    if copy.backups_kept_days != 0:
        problems.append("copy: keeps backups")
    return problems


def target_problems(rto: timedelta | None, rpo: timedelta) -> list[str]:
    """D-168: back within an hour, at most five minutes lost."""
    problems = []
    if rto is not None and rto > RTO_TARGET:
        problems.append(f"target: restore took {rto.total_seconds():.0f} s, over 3600")
    if rpo > RPO_TARGET:
        problems.append(f"target: {rpo.total_seconds():.0f} s would be lost, over 300")
    return problems


def restore_moment(
    day: date, earliest: datetime, latest: datetime, rng: random.Random
) -> datetime | None:
    """None (the latest moment), or every third month a random second in the window.

    The latest moment proves last night's backup; a random one proves the
    whole window can be restored to, not only its end.
    """
    if day.month % 3 != 0:
        return None
    span = int((latest - earliest).total_seconds())
    return earliest + timedelta(seconds=rng.randint(0, max(span, 0)))


def copy_url(production_url: str, copy: Copy) -> str:
    """Production's URL, the app's login and all, pointed at the copy."""
    return (
        make_url(production_url)
        .set(host=copy.host, port=copy.port)
        .render_as_string(hide_password=False)
    )


def image_heads() -> set[str]:
    """The migration heads this image was built with."""
    return set(ScriptDirectory.from_config(alembic_config()).get_heads())


# --- the checks on the copy -------------------------------------------------------------


def migration_problems(copy: Connection, heads: Collection[str]) -> list[str]:
    found = set(MigrationContext.configure(copy).get_current_heads())
    if found == set(heads):
        return []
    return [
        f"migration: copy at {', '.join(sorted(found)) or 'none'}, "
        f"image at {', '.join(sorted(heads))}"
    ]


def extension_problems(copy: Connection) -> list[str]:
    problems = []
    vector = copy.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if vector is None:
        problems.append("pgvector: not installed")
    elif not version_at_least(vector, PGVECTOR_FLOOR):
        problems.append(f"pgvector: {vector}, older than 0.8.2")
    dbos = copy.execute(
        text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"),
        {"schema": DBOS_SCHEMA},
    ).scalar()
    if dbos is None:
        problems.append("dbos: schema missing")
    return problems


def rights_problems(copy: Connection) -> list[str]:
    """The login holds no power of its own, and exactly item 97's rights on every table."""
    problems = []
    powers = copy.execute(
        text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls,"
            " pg_has_role(current_user, :writer, 'MEMBER')"
            " FROM pg_roles WHERE rolname = current_user"
        ),
        {"writer": APP_WRITER},
    ).one()
    if tuple(powers) != (False, False, False, False, False, True):
        problems.append("rights: the login has powers of its own or is not app_writer")
    checks = ", ".join(
        f"has_table_privilege(current_user, format('public.%I', tablename), '{p}')"
        for p in PRIVILEGES
    )
    rows = copy.execute(
        text(f"SELECT tablename, {checks} FROM pg_tables WHERE schemaname = 'public'")  # noqa: S608 - PRIVILEGES is the fixed tuple above
    ).all()
    if not rows:
        problems.append("rights: no table found")
    for table, *granted in rows:
        if tuple(granted) != expected_rights(table):
            problems.append(f"rights: {table} grants the wrong rights")
    return problems


def _tables(connection: Connection) -> dict[str, str | None]:
    """Every public table, with the column that says when each row was made."""
    rows = connection.execute(
        text(
            "SELECT t.tablename, ("
            "  SELECT c.column_name FROM information_schema.columns c"
            "  WHERE c.table_schema = 'public' AND c.table_name = t.tablename"
            "  AND c.column_name = ANY(:made_at)"
            "  ORDER BY array_position(:made_at, c.column_name::text) LIMIT 1"
            ") FROM pg_tables t WHERE t.schemaname = 'public'"
        ),
        {"made_at": list(MADE_AT)},
    ).all()
    return {table: made_at for table, made_at in rows}


def _rows(
    connection: Connection, table: str, made_at: str | None, cutoff: datetime, *, sealed: bool
) -> tuple[int, str]:
    """The table's rows made up to the cut-off: their count, and for a sealed table an md5."""
    quote = connection.dialect.identifier_preparer.quote
    where = "" if made_at is None else f" WHERE t.{quote(made_at)} <= :cutoff"
    if sealed:
        statement = (
            "SELECT count(*), coalesce(md5(string_agg(h, '' ORDER BY h)), '')"  # noqa: S608 - names from the catalogue, quoted by the dialect
            f" FROM (SELECT md5(t::text) AS h FROM {quote(table)} AS t{where}) AS rows"
        )
    else:
        statement = f"SELECT count(*), '' FROM {quote(table)} AS t{where}"  # noqa: S608 - names from the catalogue, quoted by the dialect
    count, digest = connection.execute(text(statement), {"cutoff": cutoff}).one()
    return int(count), str(digest)


def row_problems(
    production: Connection, copy: Connection, *, cutoff: datetime, deadline: Deadline
) -> list[str]:
    """Each table's rows made up to the cut-off, the copy against production."""
    tables = _tables(production)
    in_copy = set(_tables(copy))
    problems = []
    if not tables:
        problems.append("rows: no table found in production")
    for table, made_at in sorted(tables.items()):
        if deadline.expired():
            raise DeadlinePassed("comparing rows")
        if table not in in_copy:
            problems.append(f"rows: {table} missing from the copy")
            continue
        sealed = table in SEALED
        wanted = _rows(production, table, made_at, cutoff, sealed=sealed)
        found = _rows(copy, table, made_at, cutoff, sealed=sealed)
        if sealed:
            if found != wanted:
                problems.append(f"sealed: {table} differs from production")
        else:
            problem = count_problem(table, wanted[0], found[0])
            if problem is not None:
                problems.append(problem)
    return problems


def database_problems(
    production_url: str,
    copy_url: str,
    *,
    cutoff: datetime,
    heads: Collection[str],
    deadline: Deadline,
) -> list[str]:
    """Every check on the copy, each statement cut to the time the run has left."""
    timeout_ms = max(1000, int(deadline.remaining() * 1000))
    options = {"options": f"-c statement_timeout={timeout_ms}", "connect_timeout": 10}
    production_engine = create_engine(production_url, poolclass=NullPool, connect_args=options)
    copy_engine = create_engine(copy_url, poolclass=NullPool, connect_args=options)
    try:
        with production_engine.connect() as production, copy_engine.connect() as copy:
            return (
                migration_problems(copy, heads)
                + extension_problems(copy)
                + rights_problems(copy)
                + row_problems(production, copy, cutoff=cutoff, deadline=deadline)
            )
    finally:
        production_engine.dispose()
        copy_engine.dispose()


# --- the run --------------------------------------------------------------------------


def run(
    copies: RestoreCopies,
    *,
    production_url: str,
    heads: Collection[str],
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    rng: random.Random,
    clock: Callable[[], float] = time.monotonic,
) -> Outcome:
    """One restore test, its copy deleted whatever happens."""
    deadline = Deadline(TIME_LIMIT.total_seconds(), clock)
    swept = copies.sweep()
    earliest, latest = copies.window()
    requested_at = now()
    rpo = requested_at - latest
    chosen = restore_moment(india_date(requested_at), earliest, latest, rng)
    restore_time = latest if chosen is None else chosen
    identifier = copies.name(requested_at)
    problems: list[str] = []
    rto: timedelta | None = None
    try:
        copies.start(identifier, chosen)
        copy = copies.wait(identifier, deadline, sleep)
        problems += setting_problems(copy)
        problems += database_problems(
            production_url,
            copy_url(production_url, copy),
            cutoff=restore_time - SETTLE,
            heads=heads,
            deadline=deadline,
        )
        rto = now() - requested_at
    except CopyFailed as stopped:
        problems.append(f"restore: stopped in state {stopped}")
    except (CopyNotReady, DeadlinePassed):
        problems.append("restore: not done within 90 minutes")
    except SQLAlchemyError as error:
        problems.append(f"database: {type(error).__name__}")
    finally:
        copies.delete(identifier)
    problems += target_problems(rto, rpo)
    return Outcome(
        problems=problems,
        restore_time=restore_time,
        latest=chosen is None,
        rto=rto,
        rpo=rpo,
        swept=len(swept),
    )


def record(outcome: Outcome) -> None:
    """The one result line; an error line too when it failed, which Sentry turns into an issue."""
    line = {
        "ok": outcome.ok,
        "restore_time": outcome.restore_time.astimezone(UTC).isoformat(timespec="seconds"),
        "latest": outcome.latest,
        "rto_seconds": None if outcome.rto is None else round(outcome.rto.total_seconds()),
        "rto_target_seconds": round(RTO_TARGET.total_seconds()),
        "rpo_seconds": round(outcome.rpo.total_seconds()),
        "rpo_target_seconds": round(RPO_TARGET.total_seconds()),
        "copies_swept": outcome.swept,
        "problems": outcome.problems,
    }
    logger.info("restore_check.result %s", json.dumps(line, sort_keys=True))
    if not outcome.ok:
        logger.error("restore_check.failed problems=%d", len(outcome.problems))


def heartbeat(
    status: str, *, check_in_id: str | None = None, duration: float | None = None
) -> str | None:
    """A check-in to Sentry's cron monitor: its slug, status and duration, nothing else."""
    return capture_checkin(
        monitor_slug=MONITOR_SLUG,
        check_in_id=check_in_id,
        status=status,
        duration=duration,
        monitor_config=MONITOR_CONFIG,  # type: ignore[arg-type] - Sentry's TypedDict
    )


def copies_from(config: Settings) -> RestoreCopies:
    """The task's copies, from its three settings; NotConfigured without them."""
    source = config.restore_check_source_db
    subnet_group = config.restore_check_subnet_group
    security_group = config.restore_check_security_group
    if source is None or subnet_group is None or security_group is None:
        raise NotConfigured("RESTORE_CHECK_SOURCE_DB, _SUBNET_GROUP and _SECURITY_GROUP")
    rds = boto3.client("rds", region_name=config.aws_region, config=RDS_CONFIG)
    return RestoreCopies(
        rds, source=source, subnet_group=subnet_group, security_group=security_group
    )


def main(config: Settings = settings) -> int:
    """The task's entry point: 0 when the restore passed every check and target."""
    configure_logging(config.log_format)
    init_error_tracking(config)
    started = time.monotonic()
    check_in = heartbeat(MonitorStatus.IN_PROGRESS)
    try:
        outcome = run(
            copies_from(config),
            production_url=config.database_url,
            heads=image_heads(),
            now=lambda: datetime.now(UTC),
            sleep=time.sleep,
            rng=secrets.SystemRandom(),
        )
        record(outcome)
        ok = outcome.ok
    except Exception:
        logger.exception("restore_check.crashed")
        ok = False
    heartbeat(
        MonitorStatus.OK if ok else MonitorStatus.ERROR,
        check_in_id=check_in,
        duration=time.monotonic() - started,
    )
    sentry_sdk.flush()
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - the restore-check task's entry point
    raise SystemExit(main())
