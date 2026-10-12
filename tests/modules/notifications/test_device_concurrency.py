"""Registrations at once never leave an account past its cap (item 9, D-095).

Real committed connections, started together, with the moment between the
insert and the trim held open, so the bad ordering happens on every run
(testing.md section 4).
"""

import threading
import time
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.notifications import device_service
from app.modules.notifications.device_models import MAX_DEVICES_PER_ACCOUNT, DeviceToken
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

THREADS = 4


@pytest.fixture
def nearly_full() -> Iterator[uuid.UUID]:
    """A committed account one phone short of its cap."""
    with SessionLocal() as session:
        account_id = create_account(session, "creator", phone=unique_test_phone()).id
        for n in range(MAX_DEVICES_PER_ACCOUNT - 1):
            session.add(
                DeviceToken(
                    account_id=account_id,
                    platform="android",
                    token=uuid.uuid4().hex * 2,
                    last_seen_at=CONCURRENCY_NOW - timedelta(days=1, minutes=n),
                )
            )
        session.commit()
    try:
        yield account_id
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(DeviceToken).where(DeviceToken.account_id == account_id)
            )
            session.execute(delete(Account).where(Account.id == account_id))
            session.commit()


@pytest.fixture
def slow_trim(monkeypatch) -> None:
    """Hold the moment between a registration's insert and its trim."""
    trim = device_service._keep_most_recent

    def held(db, account_id):
        time.sleep(0.3)
        trim(db, account_id)

    monkeypatch.setattr(device_service, "_keep_most_recent", held)


def test_four_registrations_at_once_leave_exactly_the_cap(nearly_full, slow_trim):
    barrier = threading.Barrier(THREADS)
    errors: list[BaseException] = []

    def register(n: int) -> None:
        barrier.wait()
        try:
            with SessionLocal() as session:
                device_service.register(
                    session,
                    nearly_full,
                    token=uuid.uuid4().hex * 2,
                    platform="ios",
                    app_version=None,
                    now=CONCURRENCY_NOW + timedelta(seconds=n),
                )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=register, args=(n,)) for n in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with SessionLocal() as session:
        count = session.scalar(
            select(func.count()).where(DeviceToken.account_id == nearly_full)
        )
        newest = session.scalars(
            select(DeviceToken.platform).where(DeviceToken.account_id == nearly_full)
        ).all()
    assert errors == []
    assert count == MAX_DEVICES_PER_ACCOUNT
    # Every new phone kept; the oldest ones made way.
    assert sorted(newest).count("ios") == THREADS
