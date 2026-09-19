"""Readiness checks: can this process actually serve requests?

`/healthz` answers "is the process up". `/readyz` answers "are the things it
needs reachable" (backend.md section 9). Each check has a short timeout, so a
readiness probe never hangs, and no connection string ever reaches the
response: those contain passwords.
"""

import logging
from dataclasses import dataclass

import redis
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

logger = logging.getLogger(__name__)

# A probe that waits is a probe that fails; these are deliberately short.
DATABASE_TIMEOUT_MS = 2000
REDIS_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool


def check_database() -> CheckResult:
    """One trivial query, with its own statement timeout."""
    try:
        with engine.connect() as connection:
            connection.execute(text(f"SET LOCAL statement_timeout = {DATABASE_TIMEOUT_MS}"))
            connection.execute(text("SELECT 1"))
        return CheckResult("database", True)
    except Exception:
        # The reason goes to the log, never to the caller: it can name hosts.
        logger.warning("readiness.database_unavailable", exc_info=True)
        return CheckResult("database", False)


def check_redis() -> CheckResult:
    """A ping, with connect and read timeouts."""
    client = None
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
        )
        client.ping()
        return CheckResult("redis", True)
    except Exception:
        logger.warning("readiness.redis_unavailable", exc_info=True)
        return CheckResult("redis", False)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def run_readiness_checks() -> list[CheckResult]:
    return [check_database(), check_redis()]
