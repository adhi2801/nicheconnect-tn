"""Admins clearing one brand's name at once clear it once (D-119).

The clearance is decided under the brand's row lock, so a second admin sees
the first's clearance and is refused, rather than both writing and both
logging. Real committed connections, started together, with every write held
open a moment, so the bad ordering happens on every run (testing.md section 4).
"""

import threading
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, func, select, text

from app.db.session import SessionLocal
from app.modules.admin import look_alike_service as service
from app.modules.admin.exceptions import BrandNameAlreadyCleared
from app.modules.admin.models.admin_action import AdminAction
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from tests.factories import build_brand, create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW
from tests.owner import owner_engine

THREADS = 4


@pytest.fixture
def world() -> Iterator[dict[str, object]]:
    """Committed admins, and a committed brand whose name is held as a look-alike."""
    with SessionLocal() as session:
        admins = [
            create_account(session, "admin", phone=unique_test_phone())
            for _ in range(THREADS)
        ]
        owner = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=owner.id,
            name="Nykaa Collabs",
            email=f"clear-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.commit()
        ids: dict[str, object] = {
            "brand": brand.id,
            "owner": owner.id,
            "admins": [admin.id for admin in admins],
        }
    try:
        yield ids
    finally:
        # The admin log is sealed, so it goes on the owner's connection with
        # the triggers set aside.
        with owner_engine.begin() as connection:
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            connection.execute(
                delete(AdminAction).where(AdminAction.admin_account_id.in_(ids["admins"]))
            )
        with SessionLocal() as session:
            session.execute(delete(Brand).where(Brand.id == ids["brand"]))
            session.execute(
                delete(Account).where(Account.id.in_([ids["owner"], *ids["admins"]]))
            )
            session.commit()


def test_four_admins_clearing_at_once_clear_it_once(world, slow_writes):
    barrier = threading.Barrier(THREADS)
    outcomes: list[str] = []
    errors: list[BaseException] = []

    def clear(admin_id: uuid.UUID) -> None:
        barrier.wait()
        try:
            with SessionLocal() as session:
                admin = session.get_one(Account, admin_id)
                service.clear_name(
                    session, admin, world["brand"], note="Checked.", now=CONCURRENCY_NOW
                )
                outcomes.append("cleared")
        except BrandNameAlreadyCleared:
            outcomes.append("already")
        except BaseException as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=clear, args=(a,)) for a in world["admins"]]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(outcomes) == ["already"] * (THREADS - 1) + ["cleared"]
    with SessionLocal() as session:
        logged = session.scalar(
            select(func.count())
            .select_from(AdminAction)
            .where(
                AdminAction.action == "clear_brand_name",
                AdminAction.subject_account_id == world["owner"],
            )
        )
    assert logged == 1
