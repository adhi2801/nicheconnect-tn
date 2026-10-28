"""One sign-in completed several times at once (item 29, D-134).

Real, committed connections released together, every write held open
(`slow_writes`). The attempt is locked and marked used before the platform
is asked, so however many tabs post the same `state`, one connects and the
rest are refused: the platform is asked once.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.profiles import connection_service
from app.modules.profiles.connection_models import ConnectedAccount, ConnectionAttempt
from app.modules.profiles.exceptions import ConnectionAttemptInvalid
from tests.factories import build_creator, create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW as NOW
from tests.modules.profiles.connections_world import profile

AT_ONCE = 4


def run_together(works: list[Callable[[Any], Any]]) -> list[Any]:
    barrier = threading.Barrier(len(works))
    results: list[Any] = [None] * len(works)

    def worker(index: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                results[index] = works[index](session)
            except Exception as exc:  # collected and asserted by the test
                session.rollback()
                results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(works))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.fixture
def committed_creator() -> Iterator[dict[str, uuid.UUID]]:
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=unique_test_phone())
        creator = build_creator(
            session, handle=f"cc{uuid.uuid4().hex[:12]}", account_id=account.id
        )
        session.add(creator)
        session.commit()
        ids = {"account": account.id, "creator": creator.id}
    try:
        yield ids
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(ConnectedAccount).where(
                    ConnectedAccount.creator_id == ids["creator"]
                )
            )
            session.execute(
                delete(ConnectionAttempt).where(
                    ConnectionAttempt.account_id == ids["account"]
                )
            )
            session.execute(delete(Creator).where(Creator.id == ids["creator"]))
            session.execute(delete(Account).where(Account.id == ids["account"]))
            session.commit()


def test_one_state_completed_at_once_connects_once(
    committed_creator, platforms, slow_writes
):
    platforms["instagram"].profiles["good-code"] = profile()
    with SessionLocal() as session:
        started = connection_service.start(
            session, committed_creator["account"], "instagram", NOW
        )
    state = started.authorize_url.split("state=")[1].split("&")[0]

    def finish(session):
        creator = session.get_one(Creator, committed_creator["creator"])
        return connection_service.complete(
            session,
            committed_creator["account"],
            creator,
            "instagram",
            code="good-code",
            state=state,
            now=NOW,
        )

    results = run_together([finish] * AT_ONCE)

    assert sum(isinstance(r, ConnectedAccount) for r in results) == 1, results
    assert all(
        isinstance(r, ConnectedAccount | ConnectionAttemptInvalid) for r in results
    ), results
    assert len(platforms["instagram"].exchanged) == 1  # the platform was asked once
    with SessionLocal() as session:
        held = session.scalar(
            select(func.count()).where(
                ConnectedAccount.creator_id == committed_creator["creator"]
            )
        )
    assert held == 1
