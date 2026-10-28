"""The same two codes sent four times at once make one admin session (item 101).

Two locks stand behind "each code works once": the phone's (every login of
one number runs one at a time) and the authenticator factor's row lock,
which re-reads the last step used. Real committed connections, started
together, with every write held open a moment, so the bad ordering happens
on every run (testing.md section 4).
"""

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.errors import DomainError
from app.db.session import SessionLocal
from app.modules.admin import admin_login_service as service
from app.modules.auth import second_factor, second_factor_secrets
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.totp_factor import TotpFactor
from app.modules.auth.tokens import hash_otp_code
from app.modules.notifications.models import Notification
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

THREADS = 4
PHONE_CODE = "246810"
SECRET = bytes(range(20))


@dataclass(frozen=True)
class Admin:
    id: uuid.UUID
    phone: str


@pytest.fixture
def admin() -> Iterator[Admin]:
    """A committed admin with an authenticator and a fresh phone code."""
    with SessionLocal() as session:
        account = create_account(session, "admin", phone=unique_test_phone())
        session.add(
            TotpFactor(
                account_id=account.id,
                secret_ciphertext=second_factor_secrets.seal(SECRET, account.id),
                enrolled_at=CONCURRENCY_NOW - timedelta(days=1),
            )
        )
        session.add(
            OtpChallenge(
                phone=account.phone,
                code_hash=hash_otp_code(PHONE_CODE),
                expires_at=CONCURRENCY_NOW + timedelta(minutes=5),
                created_at=CONCURRENCY_NOW,
                updated_at=CONCURRENCY_NOW,
            )
        )
        session.commit()
        committed = Admin(id=account.id, phone=account.phone)
    try:
        yield committed
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Notification).where(
                    Notification.details["admin_account_id"].astext == str(committed.id)
                )
            )
            session.execute(
                delete(OtpChallenge).where(OtpChallenge.phone == committed.phone)
            )
            # Its sessions and factor go with it (CASCADE).
            session.execute(delete(Account).where(Account.id == committed.id))
            session.commit()


def test_four_logins_with_the_same_codes_at_once_make_one_session(admin, slow_writes):
    code = second_factor.code_at_step(SECRET, second_factor.step_at(CONCURRENCY_NOW))
    barrier = threading.Barrier(THREADS)
    wins: list[object] = []
    refusals: list[DomainError] = []
    errors: list[BaseException] = []

    def run() -> None:
        barrier.wait()
        try:
            with SessionLocal() as session:
                wins.append(
                    service.log_in(
                        session, admin.phone, PHONE_CODE, code, CONCURRENCY_NOW
                    )
                )
        except DomainError as refused:
            refusals.append(refused)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with SessionLocal() as session:
        sessions = session.scalar(
            select(func.count()).where(AuthSession.account_id == admin.id)
        )
        factor = session.scalars(
            select(TotpFactor).where(TotpFactor.account_id == admin.id)
        ).one()
    assert errors == []
    assert len(wins) == 1
    assert [r.code for r in refusals] == ["otp_invalid"] * (THREADS - 1)
    assert sessions == 1
    assert factor.last_used_step == second_factor.step_at(CONCURRENCY_NOW)
