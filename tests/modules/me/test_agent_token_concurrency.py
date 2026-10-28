"""One code makes one token, however many requests carry it at once (item 11, D-138).

A token is made only if its code is unspent. Two requests carrying the same
code at the same moment must not both see it unspent: the code's row is
locked while it is spent (`step_up_service.consume`), so one makes the
token and the other is refused. Real committed connections, with every
write held for a moment, so the race happens on every run (testing.md
section 4).
"""

import threading
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.modules.auth import agent_tokens, step_up_service
from app.modules.auth.exceptions import StepUpCodeInvalid
from app.modules.auth.models.account import Account
from app.modules.auth.models.agent_token import AgentToken
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.me import agent_token_service
from app.modules.notifications.models import Notification
from tests.factories import create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

SCOPES = ["deals:read"]


@pytest.fixture
def account_with_code() -> Iterator[tuple[uuid.UUID, str]]:
    """A committed creator account, and a code for a token with SCOPES."""
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=unique_test_phone())
        code = step_up_service.request_code(
            session,
            account,
            "create_agent_token",
            agent_tokens.scopes_value(SCOPES),
            CONCURRENCY_NOW,
        )
        session.commit()
        account_id, phone = account.id, account.phone
        assert code.pending is not None
        sent = code.pending.code
    try:
        yield account_id, sent
    finally:
        with SessionLocal() as session:
            for model in (AgentToken, Notification, StepUpChallenge):
                session.execute(delete(model).where(model.account_id == account_id))
            session.execute(delete(OtpChallenge).where(OtpChallenge.phone == phone))
            session.execute(delete(Account).where(Account.id == account_id))
            session.commit()


def test_one_code_sent_twice_at_once_makes_one_token(account_with_code, slow_writes):
    account_id, code = account_with_code
    made: list[str] = []
    refused: list[BaseException] = []
    errors: list[BaseException] = []

    def create() -> None:
        try:
            with SessionLocal() as session:
                account = session.get_one(Account, account_id)
                _, value = agent_token_service.create(
                    session, account, "Claude", SCOPES, 30, code, CONCURRENCY_NOW
                )
                made.append(value)
        except StepUpCodeInvalid as exc:
            refused.append(exc)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert (len(made), len(refused)) == (1, 1)
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AgentToken)
                .where(AgentToken.account_id == account_id)
            )
            == 1
        )
