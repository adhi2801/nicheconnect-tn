"""A refresh at the moment a session ends never outlives it (item 81, D-114).

A refresh locks its token's row, then adds the next row of the session. A
logout arriving meanwhile used to wait for that row, then end it, but never
saw the new row: under PostgreSQL's read committed isolation a statement
sees only rows committed before it began. The logged-out phone kept a
working session for up to 30 days. Shown on 24 October 2026, before the fix.

Real committed connections, with the moment between a refresh's lock and its
new row held open, so the bad ordering happens on every run (testing.md
section 4).
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.modules.auth import service as login
from app.modules.auth.exceptions import InvalidToken
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

LATER = CONCURRENCY_NOW + timedelta(minutes=1)


@pytest.fixture
def signed_in() -> Iterator[tuple[uuid.UUID, str]]:
    """A committed account with one session, and that session's refresh token."""
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=unique_test_phone())
        result = login.issue_session(session, account, uuid.uuid4(), CONCURRENCY_NOW)
        session.commit()
        account_id = account.id
    try:
        yield account_id, result.refresh_token
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(AuthSession).where(AuthSession.account_id == account_id)
            )
            session.execute(delete(Account).where(Account.id == account_id))
            session.commit()


@pytest.fixture
def slow_refresh(monkeypatch) -> None:
    """Hold a refresh between locking its token and adding the next one."""
    issue = login.issue_session

    def held(*args, **kwargs):
        time.sleep(0.3)
        return issue(*args, **kwargs)

    monkeypatch.setattr(login, "issue_session", held)


def _live_sessions(account_id: uuid.UUID) -> int:
    with SessionLocal() as session:
        return session.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.account_id == account_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.used_at.is_(None),
            )
        )


def _race(refresh_token: str, end: Callable[[], None]) -> list[BaseException]:
    """Start a refresh, and end the session while the refresh is held."""
    errors: list[BaseException] = []

    def refresh() -> None:
        try:
            with SessionLocal() as session:
                login.refresh_session(session, refresh_token, LATER)
        except InvalidToken:
            pass  # refused: the session ended first, which is also right
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    def end_it() -> None:
        time.sleep(0.1)  # the refresh holds its lock by now
        try:
            end()
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=refresh), threading.Thread(target=end_it)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def test_a_refresh_at_the_moment_of_logout_does_not_outlive_it(signed_in, slow_refresh):
    account_id, refresh_token = signed_in

    def end() -> None:
        with SessionLocal() as session:
            login.logout(session, refresh_token, LATER)

    assert _race(refresh_token, end) == []
    assert _live_sessions(account_id) == 0


def test_a_refresh_at_the_moment_of_logging_out_everywhere_does_not_outlive_it(
    signed_in, slow_refresh
):
    account_id, refresh_token = signed_in

    def end() -> None:
        with SessionLocal() as session:
            login.logout_all_sessions(session, account_id, LATER)
            session.commit()

    assert _race(refresh_token, end) == []
    assert _live_sessions(account_id) == 0


def test_a_refresh_waiting_behind_a_logout_is_refused(signed_in, monkeypatch):
    """The other order: the logout holds the lock, and the refresh must wait for it."""
    account_id, refresh_token = signed_in
    end_sessions = login.end_sessions

    def held(db, account_id, now, **kwargs):
        login.lock_sessions_of(db, account_id)
        time.sleep(0.3)
        return end_sessions(db, account_id, now, **kwargs)

    monkeypatch.setattr(login, "end_sessions", held)
    refused: list[bool] = []

    def logout() -> None:
        with SessionLocal() as session:
            login.logout(session, refresh_token, LATER)

    def refresh() -> None:
        time.sleep(0.1)  # the logout holds the lock by now
        with SessionLocal() as session:
            try:
                login.refresh_session(session, refresh_token, LATER)
            except InvalidToken:
                refused.append(True)

    threads = [threading.Thread(target=logout), threading.Thread(target=refresh)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert refused == [True]
    assert _live_sessions(account_id) == 0
