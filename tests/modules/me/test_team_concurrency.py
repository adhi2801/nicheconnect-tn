"""Joining a team at the same moment (item 13, D-148).

Real, committed connections released together, every write held open
(`slow_writes`). Every team path takes the brand's row lock first, so
however many accept at once a brand never passes 20 members, one invite
makes one member, and a day's invites never pass the brand's 20.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.modules.auth.brand_access import BrandAccess
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import (
    INVITE_LIFETIME,
    MAX_INVITES_PER_DAY,
    MAX_TEAM_MEMBERS,
    BrandInvite,
    BrandMember,
)
from app.modules.auth.team_invites import hash_invited_phone
from app.modules.me import team_service
from app.modules.me.exceptions import (
    TeamFull,
    TeamInviteNotFound,
    TeamInvitesDailyLimit,
)
from tests.factories import build_brand, create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW as NOW

AT_ONCE = 4


def run_together(works: list[Callable[[Any], Any]]) -> list[Any]:
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
def committed() -> Iterator[dict[str, Any]]:
    """A committed brand, and AT_ONCE brand accounts each with an open invite."""
    with SessionLocal() as session:
        owner = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=owner.id,
            email=f"team-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.flush()
        people, invites = [], []
        for _ in range(AT_ONCE):
            phone = unique_test_phone()
            people.append(create_account(session, "brand", phone=phone))
            invite = BrandInvite(
                brand_id=brand.id,
                role="campaigns",
                first_name="Ravi",
                phone_hash=hash_invited_phone(phone),
                invited_by_account_id=owner.id,
                expires_at=NOW + INVITE_LIFETIME,
                created_at=NOW,
                updated_at=NOW,
            )
            session.add(invite)
            invites.append(invite)
        session.commit()
        ids = {
            "brand": brand.id,
            "owner": owner.id,
            "people": [p.id for p in people],
            "invites": [i.id for i in invites],
            "accounts": [owner.id, *(p.id for p in people)],
        }

    try:
        yield ids
    finally:
        with SessionLocal() as session:
            # The team goes with its brand; the members' own accounts are ours.
            session.execute(delete(Brand).where(Brand.id == ids["brand"]))
            accounts = [*ids["accounts"], *ids.get("fillers", [])]
            session.execute(delete(Account).where(Account.id.in_(accounts)))
            session.commit()


def live_members(brand_id: uuid.UUID) -> int:
    with SessionLocal() as session:
        return session.scalar(
            select(func.count()).where(
                BrandMember.brand_id == brand_id, BrandMember.removed_at.is_(None)
            )
        )


def test_accepting_at_once_never_passes_the_cap(committed, slow_writes):
    with SessionLocal() as session:
        fillers = [
            create_account(session, "brand", phone=unique_test_phone()).id
            for _ in range(MAX_TEAM_MEMBERS - 1)  # room for exactly one more
        ]
        session.add_all(
            BrandMember(
                brand_id=committed["brand"],
                account_id=account_id,
                role="finance",
                first_name="Meena",
                created_at=NOW,
                updated_at=NOW,
            )
            for account_id in fillers
        )
        session.commit()
    committed["fillers"] = fillers

    def accept(n: int) -> Callable[[Any], Any]:
        def work(session):
            person = session.get_one(Account, committed["people"][n])
            return team_service.accept(
                session, person, committed["invites"][n], None, NOW
            )

        return work

    results = run_together([accept(n) for n in range(AT_ONCE)])

    assert sum(isinstance(r, BrandMember) for r in results) == 1, results
    assert all(isinstance(r, BrandMember | TeamFull) for r in results), results
    assert live_members(committed["brand"]) == MAX_TEAM_MEMBERS


def test_one_invite_accepted_at_once_makes_one_member(committed, slow_writes):
    """Two taps, two phones: the same person, the same invite, at the same moment."""
    person_id, invite_id = committed["people"][0], committed["invites"][0]

    def accept(session):
        person = session.get_one(Account, person_id)
        return team_service.accept(session, person, invite_id, None, NOW)

    results = run_together([accept] * AT_ONCE)

    assert sum(isinstance(r, BrandMember) for r in results) == 1, results
    assert all(isinstance(r, BrandMember | TeamInviteNotFound) for r in results), results
    assert live_members(committed["brand"]) == 1


def test_invites_sent_at_once_never_pass_the_brand_s_day(committed, slow_writes):
    """The fixture's invites count; the rest of the day's room is raced for."""
    room = MAX_INVITES_PER_DAY - AT_ONCE
    with SessionLocal() as session:
        session.add_all(
            BrandInvite(
                brand_id=committed["brand"],
                role="finance",
                first_name="Meena",
                phone_hash=hash_invited_phone(unique_test_phone()),
                invited_by_account_id=committed["owner"],
                expires_at=NOW + INVITE_LIFETIME,
                created_at=NOW,
                updated_at=NOW,
            )
            for _ in range(room - 1)  # room for exactly one more
        )
        session.commit()

    def send(session):
        owner = session.get_one(Account, committed["owner"])
        access = BrandAccess(session.get_one(Brand, committed["brand"]), "owner")
        return team_service.invite(
            session, access, owner, unique_test_phone(), "finance", "Meena", None, NOW
        )

    results = run_together([send] * AT_ONCE)

    assert sum(isinstance(r, BrandInvite) for r in results) == 1, results
    assert all(isinstance(r, BrandInvite | TeamInvitesDailyLimit) for r in results)
    with SessionLocal() as session:
        sent = session.scalar(
            select(func.count()).where(BrandInvite.brand_id == committed["brand"])
        )
    assert sent == MAX_INVITES_PER_DAY
