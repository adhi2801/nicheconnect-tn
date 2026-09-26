"""The job runner (D-060): DBOS really launched against Postgres, then removed.

These tests commit for real, because DBOS keeps its own connections. They use
a throwaway schema for DBOS's state and a date in 2020 for the checkpoint, so
no deal is covered, and they remove everything they wrote afterwards.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from dbos import DBOS
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.core import jobs
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.modules.deal_memo import anchor_jobs, anchor_service
from app.modules.deal_memo.anchor_models import DealRecordCheckpoint, DealRecordTimestamp
from app.modules.deal_memo.timestamp_authority import Stamp

TEST_SCHEMA = "dbos_test"
# 18:40 UTC on 1 January 2020 is 00:10 on 2 January in Tamil Nadu.
SCHEDULED = datetime(2020, 1, 1, 18, 40, tzinfo=UTC)
CHECKPOINT_DAY_START = anchor_service.covers_until(date(2020, 1, 2))


class FakeAuthority:
    def __init__(self, name: str) -> None:
        self.name = name

    def stamp(self, fingerprint: bytes) -> Stamp:
        return Stamp(token=b"fake-" + self.name.encode(), signed_at=SCHEDULED)


def remove_test_checkpoint() -> None:
    with SessionLocal() as db:
        db.execute(text("SET LOCAL session_replication_role = replica"))
        ids = select(DealRecordCheckpoint.id).where(
            DealRecordCheckpoint.covers_until == CHECKPOINT_DAY_START
        )
        db.execute(
            delete(DealRecordTimestamp).where(DealRecordTimestamp.checkpoint_id.in_(ids))
        )
        db.execute(
            delete(DealRecordCheckpoint).where(
                DealRecordCheckpoint.covers_until == CHECKPOINT_DAY_START
            )
        )
        db.commit()


@pytest.fixture
def launched(monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(
        anchor_jobs,
        "default_authorities",
        lambda: [FakeAuthority("digicert"), FakeAuthority("sectigo")],
    )
    remove_test_checkpoint()
    jobs.start(schema=TEST_SCHEMA)
    try:
        yield
    finally:
        # Keep the registry: the workflows stay decorated for other tests.
        DBOS.destroy(destroy_registry=False)
        remove_test_checkpoint()
        with SessionLocal() as db:
            db.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
            db.commit()


def test_the_daily_checkpoint_is_scheduled_as_specified(launched):
    schedule = DBOS.get_schedule(anchor_jobs.SCHEDULE_NAME)

    assert schedule is not None
    assert schedule["schedule"] == anchor_jobs.DAILY_CHECKPOINT_CRON


def test_the_workflow_writes_and_stamps_the_days_checkpoint(launched):
    anchor_jobs.daily_checkpoint(SCHEDULED, None)

    with SessionLocal() as db:
        checkpoint = db.scalars(
            select(DealRecordCheckpoint).where(
                DealRecordCheckpoint.covers_until == CHECKPOINT_DAY_START
            )
        ).one()
        authorities = db.scalars(
            select(DealRecordTimestamp.authority).where(
                DealRecordTimestamp.checkpoint_id == checkpoint.id
            )
        ).all()
    assert checkpoint.leaf_count == 0  # nothing was recorded before 2020
    assert sorted(authorities) == ["digicert", "sectigo"]


def test_dbos_keeps_its_state_in_its_own_schema(launched):
    with SessionLocal() as db:
        tables = db.scalars(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = :s"
            ),
            {"s": TEST_SCHEMA},
        ).all()

    assert "workflow_status" in tables


def test_the_app_does_not_start_jobs_unless_asked(monkeypatch):
    monkeypatch.setattr(settings, "run_jobs", False)
    started: list[bool] = []
    monkeypatch.setattr(jobs, "start", lambda **_: started.append(True))

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

    assert started == []


def test_the_app_starts_and_stops_jobs_when_asked(monkeypatch):
    monkeypatch.setattr(settings, "run_jobs", True)
    calls: list[str] = []
    monkeypatch.setattr(jobs, "start", lambda **_: calls.append("start"))
    monkeypatch.setattr(jobs, "stop", lambda: calls.append("stop"))

    with TestClient(app):
        assert calls == ["start"]

    assert calls == ["start", "stop"]
