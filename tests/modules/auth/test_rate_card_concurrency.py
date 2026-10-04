"""Two rate-card writes at once for one creator: the limits still hold.

Review findings, PR #34: the package limit was "count, then insert", so a
creator at nine packages adding two at once ended with eleven; and saving a
channel was "look, then insert", so two first saves at once made one request
fail with a raw IntegrityError, a 500, on an endpoint promised to be a safe
replace.

Real, committed connections, like the other concurrency tests. The moment
before each write reaches the database is held open, so the race happens
every run rather than by luck.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.db.session import SessionLocal
from app.modules.auth import rate_card_service as rate_card
from app.modules.auth.exceptions import PackageLimitReached
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import (
    MAX_PACKAGES_PER_CREATOR,
    CreatorChannel,
    CreatorPackage,
)
from tests.factories import build_creator, create_account
from tests.modules.payment_status.test_payment_concurrency import (
    AT_ONCE,
    run_at_once,
    split,
    unique_phone,
)

TODAY = date(2026, 10, 4)


def package_fields(position: int) -> dict[str, object]:
    return {
        "platform": "instagram",
        "format": "reel",
        "title": f"One reel {position}",
        "price_paise": 500_000,
        "delivery_days": 7,
        "position": position,
    }


@pytest.fixture
def creator() -> Iterator[uuid.UUID]:
    """A real, committed creator, removed again afterwards."""
    with SessionLocal() as session:
        account = create_account(session, "creator", phone=unique_phone())
        row = build_creator(
            session, handle=f"rc{uuid.uuid4().hex[:12]}", account_id=account.id
        )
        session.add(row)
        session.commit()
        creator_id, account_id = row.id, account.id
    try:
        yield creator_id
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(CreatorPackage).where(CreatorPackage.creator_id == creator_id)
            )
            session.execute(
                delete(CreatorChannel).where(CreatorChannel.creator_id == creator_id)
            )
            session.execute(delete(Creator).where(Creator.id == creator_id))
            session.execute(delete(Account).where(Account.id == account_id))
            session.commit()


def test_the_package_limit_holds_against_simultaneous_adds(
    creator, slow_writes_after_setup
):
    results = run_at_once(
        lambda s: rate_card.create_package(
            s, s.get(Creator, creator), **package_fields(10)
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, PackageLimitReached)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)
    with SessionLocal() as session:
        count = session.scalar(
            select(func.count(CreatorPackage.id)).where(
                CreatorPackage.creator_id == creator
            )
        )
    assert count == MAX_PACKAGES_PER_CREATOR


@pytest.fixture
def slow_writes_after_setup(creator) -> Iterator[None]:
    """Nine packages already saved, then writes held open: one short of the limit."""
    with SessionLocal() as session:
        for position in range(MAX_PACKAGES_PER_CREATOR - 1):
            session.add(CreatorPackage(creator_id=creator, **package_fields(position)))
        session.commit()

    def hold(*args: object) -> None:
        time.sleep(0.2)

    event.listen(Session, "before_flush", hold)
    try:
        yield
    finally:
        event.remove(Session, "before_flush", hold)


def test_simultaneous_first_saves_of_a_channel_all_succeed_as_one_row(
    creator, slow_writes
):
    results = run_at_once(
        lambda s: rate_card.save_channel(
            s,
            s.get(Creator, creator),
            platform="instagram",
            profile_url="https://www.instagram.com/priya.eats/",
            followers=12_000,
            average_views=9_000,
            today=TODAY,
        ),
        AT_ONCE,
    )

    unexpected = [r for r in results if isinstance(r, Exception)]
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    with SessionLocal() as session:
        rows = session.scalar(
            select(func.count(CreatorChannel.id)).where(
                CreatorChannel.creator_id == creator
            )
        )
    assert rows == 1
