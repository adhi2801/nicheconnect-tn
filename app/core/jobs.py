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
from app.modules.admin import report_clock_jobs
from app.modules.campaigns import alert_jobs
from app.modules.deal_memo import anchor_jobs, proof_cleaning_jobs, proof_reading_jobs
from app.modules.me import (
    account_deletion_jobs,
    connection_jobs,
    data_export_jobs,
    passkey_jobs,
    phone_change_jobs,
)
from app.modules.profiles import brand_domain_jobs

DBOS_SCHEMA = "dbos"


def dbos_config(*, schema: str = DBOS_SCHEMA) -> DBOSConfig:
    return {
        "name": "nicheconnect-backend",
        "system_database_url": settings.database_url,
        "dbos_system_schema": schema,
        # Production migrates DBOS in the release step, as the owner
        # (app/db/prepare.py); the app's own login may not create schemas.
        "run_migrations": settings.dbos_migrate_at_start,
    }


def start(*, schema: str = DBOS_SCHEMA) -> None:
    """Launch DBOS and put every schedule in place."""
    DBOS(config=dbos_config(schema=schema))
    DBOS.launch()
    DBOS.apply_schedules(
        anchor_jobs.schedules()
        + proof_cleaning_jobs.schedules()
        + proof_reading_jobs.schedules()
        + report_clock_jobs.schedules()
        + brand_domain_jobs.schedules()
        + phone_change_jobs.schedules()
        + data_export_jobs.schedules()
        + passkey_jobs.schedules()
        + account_deletion_jobs.schedules()
        + alert_jobs.schedules()
        + connection_jobs.schedules()
    )


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
