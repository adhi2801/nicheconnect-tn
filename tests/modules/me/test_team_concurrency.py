"""Joining a team at the same moment (item 13, D-148).

Real, committed connections released together, every write held open
(`slow_writes`). Every team path takes the brand's row lock first, so
however many accept at once a brand never passes 20 members, one invite
makes one member, and a day's invites never pass the brand's 20.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, or_, select

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
    CannotTakeBrand,
    OwnsABrand,
    TeamChangeNotAllowed,
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


# --- handing a brand over at the same moment (piece 2) -----------------------------
#
# The code is the route's to check, and its own tests prove it; here it is
# taken as given, so each race is between the hand-overs' locks alone.

LONG_AGO = NOW - timedelta(days=30)


@pytest.fixture
def no_codes(monkeypatch):
    monkeypatch.setattr(team_service.step_ups, "consume", lambda *args, **kwargs: None)


@pytest.fixture
def two_brands() -> Iterator[dict[str, Any]]:
    """Two committed brands, each with the same campaign manager, and one more each."""
    with SessionLocal() as session:
        owners, brands, members = [], [], []
        shared = create_account(session, "brand", phone=unique_test_phone())
        extra = []
        for n in range(2):
            owner = create_account(session, "brand", phone=unique_test_phone())
            brand = build_brand(
                session,
                account_id=owner.id,
                email=f"hand-over-{uuid.uuid4().hex[:12]}@example.com",
            )
            session.add(brand)
            session.flush()
            other = create_account(session, "brand", phone=unique_test_phone())
            ids = []
            for account in (shared, other):
                member = BrandMember(
                    brand_id=brand.id,
                    account_id=account.id,
                    role="campaigns",
                    first_name=f"Ravi{n}",
                    created_at=NOW,
                    updated_at=NOW,
                )
                session.add(member)
                session.flush()
                ids.append(member.id)
            owners.append(owner.id)
            brands.append(brand.id)
            members.append(ids)
            extra.append(other.id)
        session.commit()
        found = {
            "owners": owners,
            "brands": brands,
            "members": members,
            "shared": shared.id,
            "accounts": [*owners, shared.id, *extra],
        }
    try:
        yield found
    finally:
        with SessionLocal() as session:
            session.execute(delete(Brand).where(Brand.id.in_(found["brands"])))
            session.execute(delete(Account).where(Account.id.in_(found["accounts"])))
            session.commit()


def hand(n: int, member_id_of: Callable[[dict[str, Any]], uuid.UUID], world):
    def work(session):
        owner = session.get_one(Account, world["owners"][n])
        brand = session.get_one(Brand, world["brands"][n])
        return team_service.hand_over(
            session,
            BrandAccess(brand, "owner"),
            owner,
            member_id_of(world),
            "Adhi",
            None,
            LONG_AGO,
            NOW,
        )

    return work


def test_one_brand_handed_to_two_at_once_goes_to_one(two_brands, slow_writes, no_codes):
    results = run_together(
        [
            hand(0, lambda w: w["members"][0][0], two_brands),
            hand(0, lambda w: w["members"][0][1], two_brands),
        ]
    )

    assert sum(isinstance(r, BrandAccess) for r in results) == 1, results
    assert all(isinstance(r, BrandAccess | TeamChangeNotAllowed) for r in results)
    with SessionLocal() as session:
        former = session.scalars(
            select(BrandMember).where(
                BrandMember.brand_id == two_brands["brands"][0],
                BrandMember.account_id == two_brands["owners"][0],
            )
        ).all()
    assert len(former) == 1


def test_two_brands_handed_to_one_person_at_once_give_them_one(
    two_brands, slow_writes, no_codes
):
    """Both see that they own none; the unique index decides, as 409, never a 500."""
    results = run_together(
        [hand(n, lambda w, n=n: w["members"][n][0], two_brands) for n in range(2)]
    )

    assert sum(isinstance(r, BrandAccess) for r in results) == 1, results
    assert all(isinstance(r, BrandAccess | OwnsABrand) for r in results), results
    with SessionLocal() as session:
        owned = session.scalar(
            select(func.count()).where(Brand.account_id == two_brands["shared"])
        )
    assert owned == 1


def test_a_hand_over_waits_for_a_deletion_asked_at_that_moment(two_brands, no_codes):
    """The taker's account is read under a lock: a deletion committing meanwhile is seen."""
    taker = two_brands["shared"]
    holding = threading.Event()
    release = threading.Event()

    def ask_to_delete() -> None:
        with SessionLocal() as session:
            # As request_deletion locks it (`account_deletion_service._lock`).
            account = session.scalars(
                select(Account)
                .where(Account.id == taker)
                .with_for_update(key_share=False)
            ).one()
            holding.set()
            release.wait(10)
            account.deletion_requested_at = NOW
            account.deletion_takes_effect_at = NOW + timedelta(days=30)
            session.commit()

    deleter = threading.Thread(target=ask_to_delete)
    deleter.start()
    holding.wait(10)
    outcome: list[Any] = []

    def hand_it() -> None:
        with SessionLocal() as session:
            try:
                outcome.append(hand(0, lambda w: w["members"][0][0], two_brands)(session))
            except Exception as exc:  # asserted below
                session.rollback()
                outcome.append(exc)

    hander = threading.Thread(target=hand_it)
    hander.start()
    hander.join(1)
    still_waiting = hander.is_alive()
    release.set()
    deleter.join(10)
    hander.join(10)

    assert still_waiting
    assert len(outcome) == 1 and isinstance(outcome[0], CannotTakeBrand), outcome
    with SessionLocal() as session:
        assert (
            session.get_one(Brand, two_brands["brands"][0]).account_id
            == (two_brands["owners"][0])
        )


@pytest.mark.parametrize(
    "side", ["a creator blocks the brand", "its team blocks a creator"]
)
def test_a_block_placed_as_the_brand_changes_hands_lands_on_the_new_owner(
    two_brands, side
):
    """Every block check of a brand reads its owner: one read before the move would be lost."""
    from app.modules.auth.models.creator import Creator
    from app.modules.safety import block_service
    from app.modules.safety.models import AccountBlock
    from tests.factories import build_creator

    brand_id, old_owner, new_owner = (
        two_brands["brands"][0],
        two_brands["owners"][0],
        two_brands["shared"],
    )
    with SessionLocal() as session:
        creator = build_creator(session, handle=f"race{uuid.uuid4().hex[:12]}")
        session.add(creator)
        session.commit()
        creator_ids = (creator.id, creator.account_id)
    two_brands["accounts"].append(creator_ids[1])
    holding, release = threading.Event(), threading.Event()

    def hand_over_slowly() -> None:
        # As hand_over does: the brand's row lock, then its owner moves.
        with SessionLocal() as session:
            brand = session.scalars(
                select(Brand).where(Brand.id == brand_id).with_for_update()
            ).one()
            holding.set()
            release.wait(10)
            brand.account_id = new_owner
            session.commit()

    def place() -> None:
        with SessionLocal() as session:
            if side == "a creator blocks the brand":
                account = session.get_one(Account, creator_ids[1])
                block_service.block(session, account, None, brand_id, NOW)
            else:
                account = session.get_one(Account, two_brands["accounts"][-2])
                block_service.block(session, account, brand_id, creator_ids[0], NOW)

    mover = threading.Thread(target=hand_over_slowly)
    mover.start()
    holding.wait(10)
    placer = threading.Thread(target=place)
    placer.start()
    placer.join(1)
    waited = placer.is_alive()
    release.set()
    mover.join(10)
    placer.join(10)

    with SessionLocal() as session:
        rows = session.scalars(
            select(AccountBlock).where(
                or_(
                    AccountBlock.blocker_account_id == creator_ids[1],
                    AccountBlock.blocked_account_id == creator_ids[1],
                )
            )
        ).all()
        pairs = {(r.blocker_account_id, r.blocked_account_id) for r in rows}
        session.execute(
            delete(AccountBlock).where(AccountBlock.id.in_([r.id for r in rows]))
        )
        session.execute(delete(Creator).where(Creator.id == creator_ids[0]))
        session.commit()
    assert waited
    assert old_owner not in {a for pair in pairs for a in pair}, pairs
    assert len(pairs) == 1
