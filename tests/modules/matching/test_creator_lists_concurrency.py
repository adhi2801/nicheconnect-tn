"""Lists started and creators saved at the same moment (item 66, D-129).

Real, committed connections released together, every write held open
(`slow_writes`). Each cap is counted under a row lock, so however many
requests arrive at once, a brand never passes 50 lists, nor a list 200
creators, and saving one creator twice at once keeps one line.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.matching import creator_list_service
from app.modules.matching.creator_list_models import (
    MAX_LISTS_PER_BRAND,
    CreatorList,
    CreatorListEntry,
)
from app.modules.matching.exceptions import CreatorListFull, CreatorListsFull
from tests.factories import (
    FIXED_NOW,
    build_brand,
    build_creator,
    create_account,
    unique_test_phone,
)
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
    """A committed brand with one list, and AT_ONCE findable creators."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"list-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        creators = []
        for _ in range(AT_ONCE):
            account = create_account(session, "creator", phone=unique_test_phone())
            creator = build_creator(
                session,
                handle=f"lc{uuid.uuid4().hex[:12]}",
                account_id=account.id,
                passport_published_at=FIXED_NOW,
            )
            session.add(creator)
            creators.append(creator)
        session.flush()
        saved = CreatorList(brand_id=brand.id, name="At once")
        session.add(saved)
        session.commit()
        ids = {
            "brand": brand.id,
            "list": saved.id,
            "creators": [c.id for c in creators],
            "accounts": [brand_account.id, *(c.account_id for c in creators)],
        }

    try:
        yield ids
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(CreatorList).where(CreatorList.brand_id == ids["brand"])
            )
            session.execute(delete(Creator).where(Creator.id.in_(ids["creators"])))
            session.execute(delete(Brand).where(Brand.id == ids["brand"]))
            session.execute(delete(Account).where(Account.id.in_(ids["accounts"])))
            session.commit()


def test_lists_started_at_once_never_pass_the_cap(committed, slow_writes):
    with SessionLocal() as session:
        session.add_all(
            CreatorList(brand_id=committed["brand"], name=f"Before {n}")
            for n in range(MAX_LISTS_PER_BRAND - 2)  # one more fits beside "At once"
        )
        session.commit()

    def start(n: int) -> Callable[[Any], Any]:
        def work(session):
            brand = session.get_one(Brand, committed["brand"])
            return creator_list_service.create(session, brand, f"At once {n}", NOW)

        return work

    results = run_together([start(n) for n in range(AT_ONCE)])

    assert sum(isinstance(r, CreatorList) for r in results) == 1, results
    assert all(isinstance(r, CreatorList | CreatorListsFull) for r in results), results
    with SessionLocal() as session:
        held = session.scalar(
            select(func.count()).where(CreatorList.brand_id == committed["brand"])
        )
    assert held == MAX_LISTS_PER_BRAND


def test_creators_saved_at_once_never_pass_the_cap(committed, slow_writes, monkeypatch):
    monkeypatch.setattr(creator_list_service, "MAX_CREATORS_PER_LIST", 1)

    def save(creator_id: uuid.UUID) -> Callable[[Any], Any]:
        def work(session):
            brand = session.get_one(Brand, committed["brand"])
            found = session.get_one(CreatorList, committed["list"])
            creator_list_service.add(session, brand, found, creator_id, NOW)
            return "saved"

        return work

    results = run_together([save(c) for c in committed["creators"]])

    assert results.count("saved") == 1, results
    assert all(r == "saved" or isinstance(r, CreatorListFull) for r in results), results
    with SessionLocal() as session:
        held = session.scalar(
            select(func.count()).where(CreatorListEntry.list_id == committed["list"])
        )
    assert held == 1


def test_one_creator_saved_at_once_keeps_one_line(committed, slow_writes):
    creator_id = committed["creators"][0]

    def save(session):
        brand = session.get_one(Brand, committed["brand"])
        found = session.get_one(CreatorList, committed["list"])
        creator_list_service.add(session, brand, found, creator_id, NOW)
        return "saved"

    results = run_together([save] * AT_ONCE)

    assert results == ["saved"] * AT_ONCE
    with SessionLocal() as session:
        held = session.scalar(
            select(func.count()).where(CreatorListEntry.list_id == committed["list"])
        )
    assert held == 1


def test_the_fixture_creators_are_findable(committed):
    """Guards the tests above: an unfindable creator would be refused, not raced."""
    with SessionLocal() as session:
        found = session.scalar(
            select(func.count()).where(
                Creator.id.in_(committed["creators"]),
                *creator_list_service.search_service.visible(None),
            )
        )
    assert found == AT_ONCE
