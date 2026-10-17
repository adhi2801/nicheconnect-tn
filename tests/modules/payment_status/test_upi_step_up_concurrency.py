"""One code sent four times at once sets one UPI ID once (item 82, D-107).

A code works once. Four requests carrying the same code, started together
with every write held open a moment, must leave exactly one change and
three clean refusals: the phone's lock, taken before the code is read,
makes them go one at a time (testing.md section 4). Real committed
connections.
"""

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.auth import step_up_service
from app.modules.auth.exceptions import StepUpCodeInvalid
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.notifications.models import Notification
from app.modules.payment_status import upi_service
from app.modules.payment_status.upi_change_models import CreatorUpiChange
from tests.factories import build_creator, create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

THREADS = 4
NOTICE = "upi-2026-10"
UPI_ID = "race.meena@okaxis"


@dataclass(frozen=True)
class Asked:
    account_id: uuid.UUID
    creator_id: uuid.UUID
    code: str


@pytest.fixture
def asked(monkeypatch) -> Iterator[Asked]:
    """A committed creator who has asked for a code to set UPI_ID."""
    monkeypatch.setattr(settings, "upi_notice_version", NOTICE)
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=unique_test_phone())
        creator = build_creator(
            session, handle=f"su{uuid.uuid4().hex[:12]}", account_id=account.id
        )
        session.add(creator)
        session.commit()
        account_id, creator_id = account.id, creator.id
        code = step_up_service.request_code(
            session, account, "set_upi_id", UPI_ID, CONCURRENCY_NOW
        )
    assert code.pending is not None
    try:
        yield Asked(account_id, creator_id, code.pending.code)
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(CreatorUpiChange).where(CreatorUpiChange.creator_id == creator_id)
            )
            session.execute(
                delete(Notification).where(Notification.account_id == account_id)
            )
            session.execute(
                delete(StepUpChallenge).where(StepUpChallenge.account_id == account_id)
            )
            session.execute(delete(Creator).where(Creator.id == creator_id))
            session.execute(delete(Account).where(Account.id == account_id))
            session.commit()


def test_one_code_sent_four_times_at_once_sets_it_once(asked, slow_writes):
    barrier = threading.Barrier(THREADS)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def run() -> None:
        barrier.wait()
        try:
            with SessionLocal() as session:
                account = session.get_one(Account, asked.account_id)
                creator = session.get_one(Creator, asked.creator_id)
                upi_service.set_for_creator(
                    session,
                    account,
                    creator,
                    UPI_ID,
                    NOTICE,
                    asked.code,
                    None,  # a first ID: no login age is asked (D-109)
                    CONCURRENCY_NOW,
                )
            outcomes.append("set")
        except StepUpCodeInvalid:
            outcomes.append("refused")
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(outcomes) == ["refused"] * (THREADS - 1) + ["set"]
    with SessionLocal() as session:
        pending = session.scalars(
            select(Notification).where(
                Notification.account_id == asked.account_id,
                Notification.notification_type == "upi_change_pending",
            )
        ).all()
        consumed = session.scalars(
            select(StepUpChallenge.consumed_at).where(
                StepUpChallenge.account_id == asked.account_id
            )
        ).all()
    assert len(pending) == 1
    assert consumed == [CONCURRENCY_NOW]
