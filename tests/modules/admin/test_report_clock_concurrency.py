"""Warning runs at once never warn twice about one report (item 51).

Two app instances, or a run that overlaps the next, take reports with SKIP
LOCKED and mark them warned in the same transaction. Real committed
connections, started together, with every write held open a moment, so the
bad ordering happens on every run (testing.md section 4).
"""

import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.admin import report_clock_service as service
from app.modules.admin.models.report import Report
from app.modules.auth.models.account import Account
from app.modules.notifications.models import Notification
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

THREADS = 4
REPORTS = 3


@pytest.fixture
def due_soon() -> Iterator[uuid.UUID]:
    """A committed admin, and three committed reports due in 10 minutes."""
    with SessionLocal() as session:
        admin = create_account(session, "admin", phone=unique_test_phone())
        reporters = [
            create_account(session, "brand", phone=unique_test_phone())
            for _ in range(REPORTS)
        ]
        for reporter in reporters:
            session.add(
                Report(
                    reporter_account_id=reporter.id,
                    subject_kind="creator",
                    subject_id=uuid.uuid4(),
                    category="impersonation",
                    status="open",
                    created_at=CONCURRENCY_NOW - timedelta(hours=1, minutes=50),
                    due_at=CONCURRENCY_NOW + timedelta(minutes=10),
                    updated_at=CONCURRENCY_NOW,
                )
            )
        session.commit()
        accounts = [admin.id, *(r.id for r in reporters)]
    try:
        yield admin.id
    finally:
        with SessionLocal() as session:
            # Reports and notifications go with their accounts (CASCADE).
            session.execute(delete(Account).where(Account.id.in_(accounts)))
            session.commit()


def test_four_runs_at_once_warn_once_about_each_report(due_soon, slow_writes):
    barrier = threading.Barrier(THREADS)
    runs: list[service.WarningRun] = []
    errors: list[BaseException] = []

    def run() -> None:
        barrier.wait()
        try:
            with SessionLocal() as session:
                runs.append(service.warn_admins(session, CONCURRENCY_NOW))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with SessionLocal() as session:
        warned = session.scalars(
            select(Notification.details["report_id"].astext).where(
                Notification.account_id == due_soon,
                Notification.notification_type == "report_due_soon",
            )
        ).all()
    assert errors == []
    assert sum(r.due_soon for r in runs) == REPORTS
    assert len(warned) == len(set(warned)) == REPORTS
