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
from app.modules.auth import device_service, sessions
from app.modules.auth import service as login
from app.modules.auth.exceptions import InvalidToken, SessionNotFound
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.device_token import DeviceToken
from app.modules.me import session_service
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


def _family_of(account_id: uuid.UUID) -> uuid.UUID:
    with SessionLocal() as session:
        return session.scalars(
            select(AuthSession.family_id).where(AuthSession.account_id == account_id)
        ).first()


def test_a_refresh_at_the_moment_one_session_is_ended_does_not_outlive_it(
    signed_in, slow_refresh
):
    account_id, refresh_token = signed_in
    family_id = _family_of(account_id)

    def end() -> None:
        with SessionLocal() as session:
            sessions.end_one(session, account_id, family_id, LATER)
            session.commit()

    assert _race(refresh_token, end) == []
    assert _live_sessions(account_id) == 0


def test_two_requests_ending_one_session_at_once_end_it_once(signed_in, monkeypatch):
    """Exactly one ends it; the other is told it is not found, never a raw error."""
    account_id, _ = signed_in
    family_id = _family_of(account_id)
    end_sessions = login.end_sessions

    def held(db, account_id, now, **kwargs):
        time.sleep(0.3)
        return end_sessions(db, account_id, now, **kwargs)

    monkeypatch.setattr(login, "end_sessions", held)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def end() -> None:
        barrier.wait()
        with SessionLocal() as session:
            account = session.get_one(Account, account_id)
            try:
                session_service.end_one(
                    session, account, family_id, family_id, None, LATER
                )
                outcomes.append("ended")
            except SessionNotFound:
                outcomes.append("not_found")

    threads = [threading.Thread(target=end) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["ended", "not_found"]
    assert _live_sessions(account_id) == 0


def _tokens_of(account_id: uuid.UUID) -> int:
    with SessionLocal() as session:
        return session.scalar(
            select(func.count())
            .select_from(DeviceToken)
            .where(DeviceToken.account_id == account_id)
        )


@pytest.mark.parametrize("first", ["register", "end"])
def test_a_phone_registering_as_its_session_ends_is_never_left_behind(
    signed_in, monkeypatch, first
):
    """Either order, the ended session ends up with no phone (D-116)."""
    account_id, _ = signed_in
    family_id = _family_of(account_id)
    keep = device_service._keep_most_recent
    end_sessions = login.end_sessions

    def held_register(db, account_id):
        time.sleep(0.3)
        keep(db, account_id)

    def held_end(db, account_id, now, **kwargs):
        login.lock_sessions_of(db, account_id)
        time.sleep(0.3)
        return end_sessions(db, account_id, now, **kwargs)

    if first == "register":
        monkeypatch.setattr(device_service, "_keep_most_recent", held_register)
    else:
        monkeypatch.setattr(login, "end_sessions", held_end)
    outcomes: list[str] = []

    def register() -> None:
        if first == "end":
            time.sleep(0.1)
        with SessionLocal() as session:
            try:
                device_service.register(
                    session,
                    account_id,
                    token=uuid.uuid4().hex * 2,
                    platform="android",
                    app_version=None,
                    now=LATER,
                    session_id=family_id,
                )
                outcomes.append("registered")
            except InvalidToken:
                outcomes.append("refused")

    def end() -> None:
        if first == "register":
            time.sleep(0.1)
        with SessionLocal() as session:
            sessions.end_one(session, account_id, family_id, LATER)
            session.commit()

    threads = [threading.Thread(target=register), threading.Thread(target=end)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes == (["registered"] if first == "register" else ["refused"])
    assert _tokens_of(account_id) == 0
    assert _live_sessions(account_id) == 0


def test_an_acknowledgement_at_the_moment_of_a_refresh_is_carried_on(
    signed_in, slow_refresh
):
    """D-120: the refresh's new row must not lose the owner's "it was me"."""
    account_id, refresh_token = signed_in
    later_family = _family_of(account_id)
    with SessionLocal() as session:
        earlier_family = uuid.uuid4()
        account = session.get_one(Account, account_id)
        login.issue_session(
            session, account, earlier_family, CONCURRENCY_NOW - timedelta(hours=1)
        )
        session.commit()

    def end() -> None:
        with SessionLocal() as session:
            sessions.acknowledge(session, account_id, later_family, earlier_family, LATER)
            session.commit()

    assert _race(refresh_token, end) == []
    with SessionLocal() as session:
        live = session.scalars(
            select(AuthSession).where(
                AuthSession.family_id == later_family,
                AuthSession.used_at.is_(None),
                AuthSession.revoked_at.is_(None),
            )
        ).one()
        assert live.sign_in_acknowledged_at is not None
