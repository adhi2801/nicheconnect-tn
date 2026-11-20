"""Building or publishing one quarter's rate report at once happens once (item 84, D-200).

Real committed connections, started together on a barrier, with every write
held open a moment, so the bad ordering happens on every run (testing.md
section 4).
"""

import random
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, text

from app.db.session import SessionLocal
from app.modules.admin import rate_report_service as admin_service
from app.modules.admin.models.admin_action import AdminAction
from app.modules.auth.models.account import Account
from app.modules.insights import rate_report_rules as rules
from app.modules.insights import rate_report_service as service
from app.modules.insights.exceptions import RateReportAlreadyPublished
from app.modules.insights.rate_report_models import CityRateReport
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW
from tests.owner import owner_engine

THREADS = 4


def far_moment() -> datetime:
    """A moment whose last closed quarter no other test builds."""
    return datetime(random.randint(3000, 8999), 2, 3, 0, 30, tzinfo=UTC)


def remove(quarters: list[str], admins: list[uuid.UUID]) -> None:
    # A published report and the admin log are sealed, so they go on the
    # owner's connection with the triggers set aside (tests/record_cleanup.py).
    with owner_engine.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(
            delete(CityRateReport).where(CityRateReport.quarter.in_(quarters))
        )
        connection.execute(
            delete(AdminAction).where(AdminAction.admin_account_id.in_(admins))
        )
    with SessionLocal() as session:
        session.execute(delete(Account).where(Account.id.in_(admins)))
        session.commit()


def race(work) -> tuple[list[object], list[BaseException]]:
    barrier = threading.Barrier(THREADS)
    outcomes: list[object] = []
    errors: list[BaseException] = []

    def one(index: int) -> None:
        barrier.wait()
        try:
            outcomes.append(work(index))
        except BaseException as error:  # pragma: no cover - reported by the test
            errors.append(error)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes, errors


@pytest.fixture
def moment() -> Iterator[datetime]:
    now = far_moment()
    try:
        yield now
    finally:
        remove([rules.last_closed_quarter(now)], [])


def test_four_builds_at_once_leave_one_report(moment, monkeypatch):
    # The window between "no report yet" and the insert, held open: working
    # out the figures is where a real build spends its time.
    real = service.build_body

    def slow_body(*args, **kwargs):
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "build_body", slow_body)

    def build(_: int) -> bool:
        with SessionLocal() as session:
            return service.build_due(session, moment, agreed_fees=False).built

    outcomes, errors = race(build)

    assert errors == []
    assert sorted(outcomes) == [False] * (THREADS - 1) + [True]
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count()).where(
                    CityRateReport.quarter == rules.last_closed_quarter(moment)
                )
            )
            == 1
        )


@pytest.fixture
def built_report() -> Iterator[dict[str, object]]:
    now = far_moment()
    with SessionLocal() as session:
        service.build_due(session, now, agreed_fees=False)
        admins = [
            create_account(session, "admin", phone=unique_test_phone())
            for _ in range(THREADS)
        ]
        session.commit()
        ids = {
            "quarter": rules.last_closed_quarter(now),
            "admins": [a.id for a in admins],
        }
    try:
        yield ids
    finally:
        remove([ids["quarter"]], ids["admins"])


def test_four_admins_publishing_at_once_publish_it_once(built_report, slow_writes):
    def publish(index: int) -> str:
        with SessionLocal() as session:
            admin = session.get_one(Account, built_report["admins"][index])
            try:
                admin_service.publish(
                    session, admin, built_report["quarter"], CONCURRENCY_NOW
                )
            except RateReportAlreadyPublished:
                return "already"
            return "published"

    outcomes, errors = race(publish)

    assert errors == []
    assert sorted(outcomes) == ["already"] * (THREADS - 1) + ["published"]
    with SessionLocal() as session:
        logged = session.scalar(
            select(func.count()).where(
                AdminAction.action == "publish_rate_report",
                AdminAction.admin_account_id.in_(built_report["admins"]),
            )
        )
    assert logged == 1


def test_a_session_holding_an_old_copy_still_sees_it_published(built_report):
    """The lock re-reads the row: a copy loaded before another admin published
    must not let a second publish through."""
    first, second = built_report["admins"][:2]
    with SessionLocal() as stale:
        # An unpublished copy, held, so it stays in this session's memory.
        old_copy = stale.scalars(
            select(CityRateReport).where(
                CityRateReport.quarter == built_report["quarter"]
            )
        ).one()
        assert old_copy.published_at is None
        with SessionLocal() as other:
            admin_service.publish(
                other,
                other.get_one(Account, first),
                built_report["quarter"],
                CONCURRENCY_NOW,
            )

        with pytest.raises(RateReportAlreadyPublished):
            admin_service.publish(
                stale,
                stale.get_one(Account, second),
                built_report["quarter"],
                CONCURRENCY_NOW,
            )
