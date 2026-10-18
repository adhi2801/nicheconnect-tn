"""Exports against everything that could run beside them (D-111).

Real committed connections, threads started together on a barrier, every
write held open a moment (testing.md section 4). The code each request
carries is set aside here, so the guard under test is the database's alone:

- four requests asking at once leave one export being prepared;
- four downloads at once give the file once, and destroy it once.
"""

import threading
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import delete, select

from app.core.storage import memory_store
from app.db.session import SessionLocal
from app.modules.auth import step_up_service
from app.modules.auth.models.account import Account
from app.modules.me import data_export_service as service
from app.modules.me.exceptions import ExportAlreadyDownloaded, ExportAlreadyPreparing
from app.modules.me.export_models import DataExport, object_key
from app.modules.notifications.models import Notification
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

THREADS = 4


@pytest.fixture
def account_id(monkeypatch) -> Iterator[uuid.UUID]:
    """A committed account, with the code check set aside."""
    monkeypatch.setattr(step_up_service, "consume", lambda *args, **kwargs: None)
    memory_store().clear()
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=unique_test_phone())
        session.commit()
        created = account.id
    try:
        yield created
    finally:
        memory_store().clear()
        with SessionLocal() as session:
            session.execute(
                delete(Notification).where(Notification.account_id == created)
            )
            session.execute(delete(DataExport).where(DataExport.account_id == created))
            session.execute(delete(Account).where(Account.id == created))
            session.commit()


def at_once(work: Callable[[], object]) -> tuple[list[object], list[BaseException]]:
    barrier = threading.Barrier(THREADS)
    outcomes: list[object] = []
    errors: list[BaseException] = []

    def run() -> None:
        barrier.wait()
        try:
            outcomes.append(work())
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes, errors


def test_four_asks_at_once_leave_one_being_prepared(account_id, slow_writes):
    def ask() -> str:
        with SessionLocal() as session:
            account = session.get_one(Account, account_id)
            try:
                service.request(session, account, "123456", CONCURRENCY_NOW)
            except ExportAlreadyPreparing as refused:
                return refused.code
        return "asked"

    outcomes, errors = at_once(ask)

    assert errors == []
    assert sorted(outcomes) == ["asked"] + ["export_already_preparing"] * (THREADS - 1)
    with SessionLocal() as session:
        rows = session.scalars(
            select(DataExport).where(DataExport.account_id == account_id)
        ).all()
    assert len(rows) == 1


def test_four_downloads_at_once_give_the_file_once(account_id, slow_writes):
    with SessionLocal() as session:
        account = session.get_one(Account, account_id)
        export_id = service.request(session, account, "123456", CONCURRENCY_NOW).id
    service.run_exports(SessionLocal, memory_store(), CONCURRENCY_NOW)
    destroyed: list[str] = []
    destroy = memory_store().destroy

    def counting_destroy(key: str) -> None:
        destroyed.append(key)
        destroy(key)

    store = memory_store()
    store.destroy = counting_destroy  # type: ignore[method-assign]

    def download() -> str:
        with SessionLocal() as session:
            account = session.get_one(Account, account_id)
            try:
                data = service.download(
                    session, account, store, export_id, "123456", CONCURRENCY_NOW
                )
            except ExportAlreadyDownloaded as refused:
                return refused.code
        assert data
        return "file"

    try:
        outcomes, errors = at_once(download)
    finally:
        store.destroy = destroy  # type: ignore[method-assign]

    assert errors == []
    assert sorted(outcomes) == ["export_already_downloaded"] * (THREADS - 1) + ["file"]
    assert destroyed == [object_key(export_id)]
    with SessionLocal() as session:
        told = session.scalars(
            select(Notification).where(
                Notification.account_id == account_id,
                Notification.notification_type == "data_exported",
            )
        ).all()
    assert len(told) == 1


def test_the_job_run_twice_at_once_builds_it_once(account_id, slow_writes):
    with SessionLocal() as session:
        account = session.get_one(Account, account_id)
        service.request(session, account, "123456", CONCURRENCY_NOW)

    def run() -> int:
        return service.run_exports(SessionLocal, memory_store(), CONCURRENCY_NOW).built

    # Both may build the file; only one may mark it ready and tell the owner.
    _built, errors = at_once(run)

    assert errors == []
    with SessionLocal() as session:
        told = session.scalars(
            select(Notification).where(
                Notification.account_id == account_id,
                Notification.notification_type == "data_export_ready",
            )
        ).all()
    assert len(told) == 1
