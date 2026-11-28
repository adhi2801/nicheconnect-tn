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
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.modules.admin import rate_report_service as admin_service
from app.modules.admin.models.admin_action import AdminAction
from app.modules.auth.models.account import Account
from app.modules.insights import rate_report_rules as rules
from app.modules.insights import rate_report_service as service
from app.modules.insights.exceptions import (
    RateReportAlreadyPublished,
    RateReportNotWithdrawn,
)
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
            return service.build_due(
                session, moment, built_at=moment, agreed_fees=False
            ).built

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
        service.build_due(session, now, built_at=now, agreed_fees=False)
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


def test_four_admins_rebuilding_a_withdrawn_quarter_at_once_build_it_once(
    built_report, slow_writes, monkeypatch
):
    """D-201: the newest version is locked, and the database refuses a second
    report of the same quarter and version; the others are told cleanly."""
    with SessionLocal() as session:
        first = session.get_one(Account, built_report["admins"][0])
        admin_service.publish(session, first, built_report["quarter"], CONCURRENCY_NOW)
        admin_service.withdraw(
            session,
            first,
            built_report["quarter"],
            "A figure was built from a wrong city.",
            CONCURRENCY_NOW,
        )
    monkeypatch.setattr(rules, "METHOD_VERSION", 2)

    def rebuild(index: int) -> str:
        with SessionLocal() as session:
            admin = session.get_one(Account, built_report["admins"][index])
            try:
                admin_service.rebuild(
                    session, admin, built_report["quarter"], CONCURRENCY_NOW
                )
            except RateReportNotWithdrawn:
                return "refused"
            return "rebuilt"

    outcomes, errors = race(rebuild)

    assert errors == []
    assert sorted(outcomes) == ["rebuilt"] + ["refused"] * (THREADS - 1)
    with SessionLocal() as session:
        versions = session.scalars(
            select(CityRateReport.method_version).where(
                CityRateReport.quarter == built_report["quarter"]
            )
        ).all()
    assert sorted(versions) == [1, 2]


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


def test_a_rebuild_that_waited_is_refused_before_it_builds_anything(
    built_report, slow_writes, monkeypatch
):
    """D-201 review: after the lock, the loser looks again and builds no body."""
    with SessionLocal() as session:
        first = session.get_one(Account, built_report["admins"][0])
        admin_service.publish(session, first, built_report["quarter"], CONCURRENCY_NOW)
        admin_service.withdraw(
            session, first, built_report["quarter"], "Wrong city.", CONCURRENCY_NOW
        )
    monkeypatch.setattr(rules, "METHOD_VERSION", 2)
    real = service.build_body
    calls: list[int] = []

    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "build_body", counted)

    def rebuild(index: int) -> str:
        with SessionLocal() as session:
            admin = session.get_one(Account, built_report["admins"][index])
            try:
                admin_service.rebuild(
                    session, admin, built_report["quarter"], CONCURRENCY_NOW
                )
            except RateReportNotWithdrawn:
                return "refused"
            return "rebuilt"

    outcomes, errors = race(rebuild)

    assert errors == []
    assert sorted(outcomes) == ["rebuilt"] + ["refused"] * (THREADS - 1)
    assert len(calls) == 1


def test_two_first_builds_of_a_new_quarter_under_two_versions_leave_one(moment):
    """D-201 review: FOR UPDATE locks nothing on a quarter with no row, so the
    trigger takes an advisory lock on the quarter; only one version stands."""
    quarter = f"{random.randint(1000, 9999)}-Q2"
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def insert(version: int) -> None:
        body = {"v": version}
        with SessionLocal() as session:
            barrier.wait()
            try:
                session.add(
                    CityRateReport(
                        quarter=quarter,
                        method_version=version,
                        body=body,
                        body_sha256=service.fingerprint(body),
                        built_at=moment,
                        created_at=moment,
                        updated_at=moment,
                    )
                )
                session.flush()
                time.sleep(0.4)  # the other insert arrives while this one is open
                session.commit()
                outcomes.append("stands")
            except IntegrityError:
                session.rollback()
                outcomes.append("refused")

    threads = [threading.Thread(target=insert, args=(v,)) for v in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    try:
        assert sorted(outcomes) == ["refused", "stands"]
        with SessionLocal() as session:
            assert (
                session.scalar(
                    select(func.count()).where(CityRateReport.quarter == quarter)
                )
                == 1
            )
    finally:
        remove([quarter], [])


def test_a_rebuild_waiting_behind_an_older_version_s_correction_is_refused(
    built_report, monkeypatch
):
    """D-201, D-205: the look again after the lock finds a correction by
    what it supersedes, whatever its version.

    A rolling deploy: an instance still on method version 2 corrects the
    quarter while one already on version 3 waits on the lock. The waiter
    holds the version-1 row it read before the commit; the correction
    supersedes that row though it is below the waiter's version, and the
    look again (a row superseding the newest) sees it. Driven, not raced:
    the correcting instance takes the lock first, the waiter is seen blocked
    by exactly that session (`pg_blocking_pids`), and only then is the
    correction committed (testing.md section 4, the driven race)."""
    quarter = built_report["quarter"]
    with SessionLocal() as session:
        first = session.get_one(Account, built_report["admins"][0])
        admin_service.publish(session, first, quarter, CONCURRENCY_NOW)
        admin_service.withdraw(session, first, quarter, "Wrong city.", CONCURRENCY_NOW)
    monkeypatch.setattr(rules, "METHOD_VERSION", 3)
    real = service.build_body
    calls: list[int] = []

    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(service, "build_body", counted)
    pids: list[int] = []
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def waiter() -> None:
        with SessionLocal() as session:
            pids.append(session.scalar(text("SELECT pg_backend_pid()")))
            try:
                service.rebuild(session, quarter, CONCURRENCY_NOW, agreed_fees=False)
                outcomes.append("rebuilt")
            except RateReportNotWithdrawn:
                outcomes.append("refused")
            except BaseException as error:  # pragma: no cover - reported below
                errors.append(error)

    corrector = SessionLocal()
    thread = threading.Thread(target=waiter, daemon=True)  # never holds pytest open
    try:
        withdrawn = service._locked(corrector, quarter)
        withdrawn_id = withdrawn.id  # read now: the commit below expires it
        corrector_pid = corrector.scalar(text("SELECT pg_backend_pid()"))
        thread.start()
        deadline = time.monotonic() + 10
        with SessionLocal() as watcher:
            while not (
                pids
                and corrector_pid
                in watcher.scalar(text("SELECT pg_blocking_pids(:p)"), {"p": pids[0]})
            ):
                assert time.monotonic() < deadline, "the waiter never waited"
                time.sleep(0.01)
                watcher.rollback()  # a fresh snapshot each look
        body = {"v": 2}
        corrector.add(
            CityRateReport(
                quarter=quarter,
                method_version=2,
                body=body,
                body_sha256=service.fingerprint(body),
                built_at=CONCURRENCY_NOW,
                supersedes_id=withdrawn.id,
                created_at=CONCURRENCY_NOW,
                updated_at=CONCURRENCY_NOW,
            )
        )
        corrector.commit()
    finally:
        corrector.close()
        if thread.ident is not None:  # started
            thread.join(timeout=30)

    assert not thread.is_alive(), "the waiter never finished"
    assert errors == []
    assert outcomes == ["refused"]
    assert calls == []
    with SessionLocal() as session:
        rows = session.execute(
            select(CityRateReport.method_version, CityRateReport.supersedes_id)
            .where(CityRateReport.quarter == quarter)
            .order_by(CityRateReport.method_version)
        ).all()
    assert [tuple(row) for row in rows] == [(1, None), (2, withdrawn_id)]
