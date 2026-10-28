"""Two first logins on one new number at once, as different sides (item 8, D-126).

Real, committed connections released together. Each login locks the number
first, and the code works once, so exactly one side is made and the other
is a clean wrong-code answer, never a raw unique-rule error; and the same
side twice never makes two accounts.
"""

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.auth.exceptions import OtpInvalid
from app.modules.auth.models.account import Account
from app.modules.auth.service import LoginResult, request_otp, verify_otp
from tests.factories import FIXED_NOW
from tests.modules.auth.test_otp_concurrency import remove_rows_for

BOTH_SIDES_PHONE = "+917777700002"


def run_together(*works: Callable[[Any], Any]) -> list[Any]:
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
def phone() -> Iterator[str]:
    remove_rows_for(BOTH_SIDES_PHONE)
    try:
        yield BOTH_SIDES_PHONE
    finally:
        remove_rows_for(BOTH_SIDES_PHONE)


def code_for(phone: str) -> str:
    with SessionLocal() as session:
        pending = request_otp(session, phone, FIXED_NOW)
        session.commit()
        return pending.code


def roles_on(phone: str) -> list[str]:
    with SessionLocal() as session:
        return sorted(
            session.scalars(select(Account.role).where(Account.phone == phone)).all()
        )


@pytest.mark.parametrize("roles", [("brand", "creator"), ("creator", "creator")])
def test_one_code_makes_one_side_whatever_is_asked(phone, roles, slow_writes):
    code = code_for(phone)

    results = run_together(
        *(
            lambda session, role=role: verify_otp(session, phone, code, role, FIXED_NOW)
            for role in roles
        )
    )

    assert sum(isinstance(r, LoginResult) for r in results) == 1
    assert sum(isinstance(r, OtpInvalid) for r in results) == 1, results
    assert len(roles_on(phone)) == 1
