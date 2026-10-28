"""A phone number change against everything that could run beside it (item 80, D-108).

Real committed connections, threads started together on a barrier
(testing.md section 4):

- two accounts claiming the same new number at once: exactly one waits on it;
- two accounts asking for each other's number at once: both are refused,
  and neither waits on the other forever, since every piece of work on two
  numbers locks them in one order;
- two runs of the job making the same change at once: it is made once;
- a login with the current number at the moment a change made without it
  falls due (D-110): the login lands first and cancels it, never after the
  move on the moved account;
- a login with the old number at the moment the change is made: the login
  either lands before the move, and its session is ended with the rest, or
  after it, on a new account. It never keeps a session on the moved account,
  which the per-phone lock the job takes on both numbers guarantees.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import delete, select, text

from app.db.session import SessionLocal
from app.modules.auth import service as login
from app.modules.auth import step_up_service
from app.modules.auth.exceptions import OtpInvalid, PhoneInUse
from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import (
    AccountPhoneChange,
    wait_for,
)
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.me import phone_change_service as service
from app.modules.notifications.models import Notification
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

THREADS = 4
# Every login here is old enough for a change (D-109).
LONG_AGO_LOGIN = CONCURRENCY_NOW - timedelta(days=60)


@dataclass
class Numbers:
    """Every number a test used, so every row on them can be removed."""

    phones: list[str]


@pytest.fixture
def numbers() -> Iterator[Numbers]:
    used = Numbers(phones=[])
    try:
        yield used
    finally:
        with SessionLocal() as session:
            accounts = select(Account.id).where(Account.phone.in_(used.phones))
            changes = select(AccountPhoneChange.account_id).where(
                AccountPhoneChange.new_phone.in_(used.phones)
            )
            for table in (Notification, AuthSession, StepUpChallenge):
                session.execute(
                    delete(table).where(
                        table.account_id.in_(accounts) | table.account_id.in_(changes)
                    )
                )
            session.execute(
                delete(AccountPhoneChange).where(
                    AccountPhoneChange.new_phone.in_(used.phones)
                )
            )
            session.execute(
                delete(OtpChallenge).where(OtpChallenge.phone.in_(used.phones))
            )
            session.execute(delete(Account).where(Account.phone.in_(used.phones)))
            session.commit()


def new_number(numbers: Numbers) -> str:
    phone = unique_test_phone()
    numbers.phones.append(phone)
    return phone


def committed_account(numbers: Numbers) -> tuple[uuid.UUID, str]:
    phone = new_number(numbers)
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=phone)
        session.commit()
        return account.id, phone


def due_change(
    numbers: Numbers, *, without_current_number: bool = False
) -> tuple[uuid.UUID, uuid.UUID, str, str]:
    """A committed account whose change to a new number is due at CONCURRENCY_NOW."""
    account_id, old_phone = committed_account(numbers)
    new_phone = new_number(numbers)
    wait = wait_for(without_current_number)
    with SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO account_phone_change (account_id, new_phone, "
                "requested_at, takes_effect_at, without_current_number) "
                "VALUES (:a, :p, :at, :due, :lost)"
            ),
            {
                "a": account_id,
                "p": new_phone,
                "at": CONCURRENCY_NOW - wait,
                "due": CONCURRENCY_NOW,
                "lost": without_current_number,
            },
        )
        session.commit()
        change_id = session.scalars(
            select(AccountPhoneChange.id).where(
                AccountPhoneChange.account_id == account_id
            )
        ).one()
    return change_id, account_id, old_phone, new_phone


def at_once(*work: Callable[[], object]) -> tuple[list[object], list[BaseException]]:
    """Run each piece of work in its own thread, all released together."""
    barrier = threading.Barrier(len(work))
    outcomes: list[object] = []
    errors: list[BaseException] = []

    def run(piece: Callable[[], object]) -> None:
        barrier.wait()
        try:
            outcomes.append(piece())
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=run, args=(piece,)) for piece in work]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes, errors


def test_two_accounts_claiming_one_number_at_once_leave_one_waiting(numbers, slow_writes):
    new_phone = new_number(numbers)
    claims: list[tuple[uuid.UUID, str]] = []
    for _ in range(THREADS):
        account_id, _phone = committed_account(numbers)
        with SessionLocal() as session:
            account = session.get_one(Account, account_id)
            asked = step_up_service.request_code(
                session, account, "change_phone", new_phone, CONCURRENCY_NOW
            )
        assert asked.pending is not None
        claims.append((account_id, asked.pending.code))
    with SessionLocal() as session:
        new_code = login.request_otp(session, new_phone, CONCURRENCY_NOW).code

    def claim(account_id: uuid.UUID, step_up_code: str) -> Callable[[], str]:
        def work() -> str:
            with SessionLocal() as session:
                account = session.get_one(Account, account_id)
                try:
                    service.request_change(
                        session,
                        account,
                        new_phone,
                        new_code,
                        step_up_code,
                        LONG_AGO_LOGIN,
                        CONCURRENCY_NOW,
                    )
                except (OtpInvalid, PhoneInUse) as refused:
                    return refused.code
            return "waiting"

        return work

    outcomes, errors = at_once(*(claim(*pair) for pair in claims))

    assert errors == []
    assert outcomes.count("waiting") == 1
    assert len(outcomes) == THREADS
    with SessionLocal() as session:
        assert (
            len(
                session.scalars(
                    select(AccountPhoneChange).where(
                        AccountPhoneChange.new_phone == new_phone
                    )
                ).all()
            )
            == 1
        )


def test_two_accounts_asking_for_each_others_number_at_once_are_both_refused(
    numbers, monkeypatch
):
    first_id, first_phone = committed_account(numbers)
    second_id, second_phone = committed_account(numbers)
    codes: dict[uuid.UUID, tuple[str, str]] = {}
    for account_id, target in ((first_id, second_phone), (second_id, first_phone)):
        with SessionLocal() as session:
            account = session.get_one(Account, account_id)
            asked = step_up_service.request_code(
                session, account, "change_phone", target, CONCURRENCY_NOW
            )
            target_code = login.request_otp(session, target, CONCURRENCY_NOW).code
        assert asked.pending is not None
        codes[account_id] = (asked.pending.code, target_code)

    # Hold each request between its new number's code and its current
    # number's: taken in that order alone, each would hold one number's lock
    # and wait for the other's.
    check_phone_code = login.check_phone_code

    def slow_check(*args, **kwargs):
        found = check_phone_code(*args, **kwargs)
        time.sleep(0.2)
        return found

    monkeypatch.setattr(login, "check_phone_code", slow_check)

    def ask(account_id: uuid.UUID, target: str) -> Callable[[], str]:
        def work() -> str:
            step_up_code, target_code = codes[account_id]
            with SessionLocal() as session:
                account = session.get_one(Account, account_id)
                try:
                    service.request_change(
                        session,
                        account,
                        target,
                        target_code,
                        step_up_code,
                        LONG_AGO_LOGIN,
                        CONCURRENCY_NOW,
                    )
                except PhoneInUse as refused:
                    return refused.code
            return "waiting"

        return work

    outcomes, errors = at_once(ask(first_id, second_phone), ask(second_id, first_phone))

    assert errors == []
    assert outcomes == ["phone_in_use", "phone_in_use"]


def test_two_runs_at_once_make_a_change_once(numbers, slow_writes):
    change_id, account_id, _old, new_phone = due_change(numbers)

    def run() -> str | None:
        with SessionLocal() as session:
            return service.make_change(session, change_id, CONCURRENCY_NOW)

    outcomes, errors = at_once(run, run)

    assert errors == []
    assert sorted(outcomes, key=str) == [None, "made"]
    with SessionLocal() as session:
        assert session.get_one(Account, account_id).phone == new_phone
        told = session.scalars(
            select(Notification).where(
                Notification.account_id == account_id,
                Notification.notification_type == "phone_changed",
            )
        ).all()
    assert len(told) == 1


def test_a_login_with_the_old_number_as_the_change_is_made_keeps_no_session_on_it(
    numbers, monkeypatch
):
    change_id, account_id, old_phone, _new = due_change(numbers)
    with SessionLocal() as session:
        code = login.request_otp(session, old_phone, CONCURRENCY_NOW).code

    # Hold the login open between finding the account and writing its
    # session, and start the job inside that window: without the job's lock
    # on the old number, the job would move the account and end its sessions
    # first, and the login's session would then outlive the move.
    issue_session = login.issue_session

    def slow_issue_session(*args, **kwargs):
        time.sleep(0.3)
        return issue_session(*args, **kwargs)

    monkeypatch.setattr(login, "issue_session", slow_issue_session)

    def log_in() -> uuid.UUID:
        with SessionLocal() as session:
            return login.verify_otp(
                session, old_phone, code, "creator", CONCURRENCY_NOW
            ).account_id

    def make() -> str | None:
        time.sleep(0.1)
        with SessionLocal() as session:
            return service.make_change(session, change_id, CONCURRENCY_NOW)

    outcomes, errors = at_once(log_in, make)

    assert errors == []
    assert "made" in outcomes
    with SessionLocal() as session:
        live = session.scalars(
            select(AuthSession).where(
                AuthSession.account_id == account_id, AuthSession.revoked_at.is_(None)
            )
        ).all()
    assert live == []


def test_a_login_with_the_current_number_as_a_lost_number_change_falls_due_cancels_it(
    numbers, monkeypatch
):
    change_id, account_id, old_phone, _new = due_change(
        numbers, without_current_number=True
    )
    with SessionLocal() as session:
        code = login.request_otp(session, old_phone, CONCURRENCY_NOW).code

    # As above: the login holds its number's lock while it writes its session,
    # and the job starts inside that window. Without the job's lock on the
    # current number, it would move the account before the login's session
    # was written, and that session would land on the moved account.
    issue_session = login.issue_session

    def slow_issue_session(*args, **kwargs):
        time.sleep(0.3)
        return issue_session(*args, **kwargs)

    monkeypatch.setattr(login, "issue_session", slow_issue_session)

    def log_in() -> uuid.UUID:
        with SessionLocal() as session:
            return login.verify_otp(
                session, old_phone, code, "creator", CONCURRENCY_NOW
            ).account_id

    def make() -> str | None:
        time.sleep(0.1)
        with SessionLocal() as session:
            return service.make_change(session, change_id, CONCURRENCY_NOW)

    outcomes, errors = at_once(log_in, make)

    assert errors == []
    assert "voided" in outcomes
    assert account_id in outcomes
    with SessionLocal() as session:
        assert session.get_one(Account, account_id).phone == old_phone
