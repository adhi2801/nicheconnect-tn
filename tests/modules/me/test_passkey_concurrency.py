"""Passkeys against everything that could run beside them (D-113).

Real committed connections, threads started together on a barrier
(testing.md section 4):

- one login answer sent four times at once logs in once;
- a reset falling due as the owner signs in with a passkey: the sign-in
  lands first and cancels it, never the reset first and the keys gone;
- two passkeys added at once to an account one short of the cap: one is
  kept, the other refused.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, select, text

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.auth import passkeys
from app.modules.auth import service as login
from app.modules.auth.exceptions import PasskeyInvalid, TooManyPasskeys
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.passkey import (
    MAX_PASSKEYS,
    PASSKEY_RESET_WAIT,
    Passkey,
    PasskeyChallenge,
    PasskeyReset,
)
from app.modules.me import passkey_service as service
from app.modules.notifications.models import Notification
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW
from tests.passkeys import ORIGIN, RP_ID, SoftAuthenticator

THREADS = 4


@pytest.fixture
def account_id(monkeypatch) -> Iterator[uuid.UUID]:
    """A committed creator account, with passkeys switched on."""
    monkeypatch.setattr(settings, "passkey_rp_id", RP_ID)
    monkeypatch.setattr(settings, "passkey_origins", ORIGIN)
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=unique_test_phone())
        session.commit()
        created = account.id
    try:
        yield created
    finally:
        with SessionLocal() as session:
            for table in (Notification, AuthSession, Passkey, PasskeyReset):
                session.execute(delete(table).where(table.account_id == created))
            session.execute(
                delete(PasskeyChallenge).where(
                    (PasskeyChallenge.account_id == created)
                    | PasskeyChallenge.account_id.is_(None)
                    & (PasskeyChallenge.created_at >= CONCURRENCY_NOW - timedelta(days=8))
                )
            )
            session.execute(delete(Account).where(Account.id == created))
            session.commit()


def added(account_id: uuid.UUID, key: SoftAuthenticator) -> None:
    """A real passkey on the account, through the real checks."""
    with SessionLocal() as session:
        account = session.get_one(Account, account_id)
        options = passkeys.registration_options(session, account, CONCURRENCY_NOW)
        passkeys.add(session, account, key.create(options), "My phone", CONCURRENCY_NOW)
        session.commit()


def at_once(*work: Callable[[], object]) -> tuple[list[object], list[BaseException]]:
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


def test_one_login_answer_sent_four_times_at_once_logs_in_once(account_id, slow_writes):
    key = SoftAuthenticator()
    added(account_id, key)
    with SessionLocal() as session:
        answer = key.get(passkeys.login_options(session, CONCURRENCY_NOW))

    def log_in() -> str:
        with SessionLocal() as session:
            try:
                passkeys.log_in(session, answer, CONCURRENCY_NOW)
            except PasskeyInvalid as refused:
                return refused.code
        return "in"

    outcomes, errors = at_once(*([log_in] * THREADS))

    assert errors == []
    assert sorted(outcomes) == ["in"] + ["passkey_invalid"] * (THREADS - 1)


def test_a_sign_in_as_a_reset_falls_due_cancels_it_and_keeps_the_keys(
    account_id, monkeypatch
):
    key = SoftAuthenticator()
    added(account_id, key)
    requested = CONCURRENCY_NOW - PASSKEY_RESET_WAIT
    with SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO passkey_reset (account_id, requested_at, takes_effect_at) "
                "VALUES (:a, :r, :t)"
            ),
            {"a": account_id, "r": requested, "t": CONCURRENCY_NOW},
        )
        session.commit()
        answer = key.get(passkeys.login_options(session, CONCURRENCY_NOW))

    # Hold the sign-in open while it holds its key's lock, and start the job
    # inside that window: without the job's lock on the keys, it would find
    # no sign-in yet, and remove them.
    issue_session = login.issue_session

    def slow_issue_session(*args, **kwargs):
        time.sleep(0.3)
        return issue_session(*args, **kwargs)

    monkeypatch.setattr(login, "issue_session", slow_issue_session)

    def sign_in() -> str:
        with SessionLocal() as session:
            passkeys.log_in(session, answer, CONCURRENCY_NOW)
        return "in"

    def settle() -> service.ResetRun:
        time.sleep(0.1)
        return service.run_resets(SessionLocal, CONCURRENCY_NOW)

    outcomes, errors = at_once(sign_in, settle)

    assert errors == []
    [run] = [outcome for outcome in outcomes if isinstance(outcome, service.ResetRun)]
    assert (run.cancelled, run.reset) == (1, 0)
    with SessionLocal() as session:
        kept = session.scalars(
            select(Passkey).where(Passkey.account_id == account_id)
        ).all()
    assert len(kept) == 1


def test_two_added_at_once_at_the_cap_keep_one(account_id, slow_writes):
    added(account_id, SoftAuthenticator())
    with SessionLocal() as session:
        for n in range(MAX_PASSKEYS - 2):
            session.add(
                Passkey(
                    account_id=account_id,
                    credential_id=uuid.uuid4().bytes,
                    public_key=bytes.fromhex("a10102"),
                    sign_count=0,
                    aaguid=uuid.UUID(int=0),
                    backup_eligible=False,
                    backup_state=False,
                    name=f"spare {n}",
                    created_at=CONCURRENCY_NOW,
                    updated_at=CONCURRENCY_NOW,
                )
            )
        session.commit()
        account = session.get_one(Account, account_id)
        answers = [
            SoftAuthenticator().create(
                passkeys.registration_options(session, account, CONCURRENCY_NOW)
            )
            for _ in range(2)
        ]

    def add(answer: dict) -> Callable[[], str]:
        def work() -> str:
            with SessionLocal() as session:
                account = session.get_one(Account, account_id)
                try:
                    passkeys.add(session, account, answer, "New", CONCURRENCY_NOW)
                    session.commit()
                except TooManyPasskeys as refused:
                    return refused.code
            return "added"

        return work

    outcomes, errors = at_once(add(answers[0]), add(answers[1]))

    assert errors == []
    assert sorted(outcomes) == ["added", "too_many_passkeys"]
    with SessionLocal() as session:
        held = session.scalars(
            select(Passkey).where(Passkey.account_id == account_id)
        ).all()
    assert len(held) == MAX_PASSKEYS
