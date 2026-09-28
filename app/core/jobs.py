"""The job runner: DBOS, inside the app (D-047, D-060).

DBOS keeps workflow state in Postgres, in its own `dbos` schema, which it
creates and upgrades itself (D-060 point 1). There is no broker and no worker
process to deploy: jobs run in the app's own process, and several app
instances share the work safely.

Off unless `RUN_JOBS=true`, so tests and laptops never start a scheduler by
accident. DBOS opens no listening port; it would only reach out to DBOS's
hosted Conductor service if given a key, and it is not.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dbos import DBOS, DBOSConfig
from fastapi import FastAPI

from app.core.config import settings
from app.modules.deal_memo import anchor_jobs

DBOS_SCHEMA = "dbos"


def dbos_config(*, schema: str = DBOS_SCHEMA) -> DBOSConfig:
    return {
        "name": "nicheconnect-backend",
        "system_database_url": settings.database_url,
        "dbos_system_schema": schema,
        "run_migrations": True,
    }


def start(*, schema: str = DBOS_SCHEMA) -> None:
    """Launch DBOS and put every schedule in place."""
    DBOS(config=dbos_config(schema=schema))
    DBOS.launch()
    DBOS.apply_schedules(anchor_jobs.schedules())


def stop() -> None:
    DBOS.destroy()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.run_jobs:
        start()
    try:
        yield
    finally:
        if settings.run_jobs:
            stop()
