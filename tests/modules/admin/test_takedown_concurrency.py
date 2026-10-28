"""Two admins acting on the same order at once make one takedown (item 52).

Withholding is refused a second time by the database's one-active-takedown
index; lifting reads the takedown under its row's lock. Real committed
connections, started together, with every write held open a moment, so the
bad ordering happens on every run (testing.md section 4).
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select, text

from app.core.errors import DomainError
from app.db.session import SessionLocal
from app.modules.admin import takedown_service as service
from app.modules.admin.models.admin_action import AdminAction
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.campaigns.models import Campaign
from app.modules.notifications.models import Notification
from app.modules.safety.takedown_models import Takedown
from tests.factories import build_brand, build_campaign, create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW
from tests.owner import owner_engine

THREADS = 4


@pytest.fixture
def world() -> Iterator[dict[str, uuid.UUID]]:
    """Committed admins and one open campaign of a committed brand."""
    with SessionLocal() as session:
        admins = [
            create_account(session, "admin", phone=unique_test_phone())
            for _ in range(THREADS)
        ]
        owner = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=owner.id,
            email=f"takedown-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        session.commit()
        ids = {
            "campaign": campaign.id,
            "brand": brand.id,
            "owner": owner.id,
            **{f"admin{n}": admin.id for n, admin in enumerate(admins)},
        }
    admin_ids = [ids[f"admin{n}"] for n in range(THREADS)]
    try:
        yield ids
    finally:
        # The admin log is sealed and takedowns are never deleted by the app,
        # so they go on the owner's connection with the triggers set aside.
        with owner_engine.begin() as connection:
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            connection.execute(
                delete(AdminAction).where(AdminAction.admin_account_id.in_(admin_ids))
            )
            connection.execute(
                delete(Takedown).where(Takedown.subject_id == ids["campaign"])
            )
        with SessionLocal() as session:
            session.execute(
                delete(Notification).where(Notification.account_id == ids["owner"])
            )
            session.execute(delete(Campaign).where(Campaign.id == ids["campaign"]))
            session.execute(delete(Brand).where(Brand.id == ids["brand"]))
            session.execute(
                delete(Account).where(Account.id.in_([ids["owner"], *admin_ids]))
            )
            session.commit()


def at_once(world, act: Callable[[object, Account], object]) -> tuple[list, list]:
    """Run `act` as each admin, all released together; return wins and refusals."""
    barrier = threading.Barrier(THREADS)
    wins: list[object] = []
    refusals: list[DomainError] = []
    errors: list[BaseException] = []

    def run(admin_id: uuid.UUID) -> None:
        barrier.wait()
        try:
            with SessionLocal() as session:
                admin = session.get_one(Account, admin_id)
                wins.append(act(session, admin))
        except DomainError as refused:
            refusals.append(refused)
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=run, args=(world[f"admin{n}"],)) for n in range(THREADS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    return wins, refusals


def order() -> service.Order:
    return service.Order(
        basis="court_order",
        issued_by="High Court of Madras",
        order_reference="WP 1012 of 2026",
        legal_provision=None,
        reference_sealed=False,
        received_at=CONCURRENCY_NOW - timedelta(hours=1),
    )


def withhold(session, admin: Account, campaign_id: uuid.UUID) -> Takedown:
    return service.withhold(
        session,
        admin,
        subject_kind="campaign",
        subject_id=campaign_id,
        order=order(),
        report_id=None,
        note="The order names this campaign.",
        now=CONCURRENCY_NOW,
    )


def test_four_admins_withholding_at_once_make_one_takedown(world, slow_writes):
    wins, refusals = at_once(world, lambda s, a: withhold(s, a, world["campaign"]))

    with SessionLocal() as session:
        made = session.scalar(
            select(func.count()).where(Takedown.subject_id == world["campaign"])
        )
        told = session.scalar(
            select(func.count()).where(
                Notification.account_id == world["owner"],
                Notification.notification_type == "content_withheld",
            )
        )
    assert len(wins) == 1
    assert [r.code for r in refusals] == ["already_withheld"] * (THREADS - 1)
    assert (made, told) == (1, 1)


def test_four_admins_lifting_at_once_lift_it_once(world, slow_writes):
    with SessionLocal() as session:
        first = session.get_one(Account, world["admin0"])
        takedown_id = withhold(session, first, world["campaign"]).id

    wins, refusals = at_once(
        world,
        lambda s, a: service.lift(
            s, a, takedown_id, note="Set aside.", now=CONCURRENCY_NOW + timedelta(hours=1)
        ),
    )

    with SessionLocal() as session:
        restored = session.scalar(
            select(func.count()).where(
                Notification.account_id == world["owner"],
                Notification.notification_type == "content_restored",
            )
        )
        logged = session.scalar(
            select(func.count()).where(
                AdminAction.action == "lift_withhold",
                AdminAction.subject_account_id == world["owner"],
            )
        )
    assert len(wins) == 1
    assert [r.code for r in refusals] == ["takedown_already_lifted"] * (THREADS - 1)
    assert (restored, logged) == (1, 1)
