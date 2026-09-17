"""Simultaneous requests for one phone (the per-phone advisory lock).

These tests need separate, really-committing connections, so they can't use
the rollback fixture. They use a reserved fake number and delete its rows
before and after.
"""

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.auth.exceptions import OtpInvalid, OtpSendLimitReached
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.service import request_otp, verify_otp
from tests.factories import FIXED_NOW

CONCURRENCY_PHONE = "+917777700001"
THREADS = 6


def remove_rows_for(phone: str) -> None:
    with SessionLocal() as session:
        account_ids = select(Account.id).where(Account.phone == phone)
        session.execute(delete(AuthSession).where(AuthSession.account_id.in_(account_ids)))
        session.execute(delete(Account).where(Account.phone == phone))
        session.execute(delete(OtpChallenge).where(OtpChallenge.phone == phone))
        session.commit()


@pytest.fixture
def phone() -> Iterator[str]:
    remove_rows_for(CONCURRENCY_PHONE)
    try:
        yield CONCURRENCY_PHONE
    finally:
        remove_rows_for(CONCURRENCY_PHONE)


def run_at_once(work: Callable[[Any], Any], count: int) -> list[Any]:
    """Run `work(session)` in `count` threads released together; return results or errors."""
    barrier = threading.Barrier(count)
    results: list[Any] = [None] * count

    def worker(index: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                results[index] = work(session)
            except Exception as exc:  # collected and asserted by the test
                results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_simultaneous_requests_never_exceed_the_send_limit(phone):
    results = run_at_once(lambda session: request_otp(session, phone, FIXED_NOW), THREADS)

    refused = [r for r in results if isinstance(r, OtpSendLimitReached)]
    unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, OtpSendLimitReached)]
    assert unexpected == []
    assert len(refused) == THREADS - 3
    with SessionLocal() as session:
        stored = session.scalars(select(OtpChallenge).where(OtpChallenge.phone == phone)).all()
    assert len(stored) == 3


def test_simultaneous_logins_with_one_code_succeed_once(phone):
    with SessionLocal() as session:
        code = request_otp(session, phone, FIXED_NOW).code

    results = run_at_once(
        lambda session: verify_otp(session, phone, code, "creator", FIXED_NOW), THREADS
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1
    assert all(isinstance(f, OtpInvalid) for f in failures)
    with SessionLocal() as session:
        accounts = session.scalars(select(Account).where(Account.phone == phone)).all()
        assert len(accounts) == 1
        sessions = session.scalars(
            select(AuthSession).where(AuthSession.account_id == accounts[0].id)
        ).all()
        assert len(sessions) == 1
