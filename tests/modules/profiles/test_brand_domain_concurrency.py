"""Two brands proving one domain at the same moment: exactly one holds it (item 74).

Both claims wait on the same domain, and both brands' records are published
(a shared host, or an agency that added both). Each check sees nobody holding
the domain yet; the database's partial unique index decides, and the loser
is recorded as `taken`, never a raw error. Real committed connections,
started together, with every write held open a moment (testing.md section 4).
"""

import threading
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.core.errors import DomainError
from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.profiles import brand_domain_service as service
from app.modules.profiles import brand_domains as rules
from app.modules.profiles.brand_domain_models import BrandDomain
from tests.factories import build_brand, create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW

THREADS = 2


@pytest.fixture
def claims() -> Iterator[list[service.DueCheck]]:
    """Two committed brands, each with a pending claim to the same domain."""
    domain = f"race{uuid.uuid4().hex[:10]}.in"
    with SessionLocal() as session:
        account_ids, brand_ids, due = [], [], []
        for _ in range(THREADS):
            account = create_account(session, "brand", phone=unique_test_phone())
            brand = build_brand(
                session,
                account_id=account.id,
                email=f"race-{uuid.uuid4().hex[:12]}@example.com",
            )
            session.add(brand)
            session.flush()
            claim = BrandDomain(
                brand_id=brand.id,
                domain=domain,
                token=rules.new_token(),
                claimed_at=CONCURRENCY_NOW,
                token_expires_at=CONCURRENCY_NOW + rules.TOKEN_LIFETIME,
            )
            session.add(claim)
            session.flush()
            account_ids.append(account.id)
            brand_ids.append(brand.id)
            due.append(service.DueCheck(claim.id, domain, claim.token, False))
        session.commit()
    try:
        yield due
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(BrandDomain).where(BrandDomain.brand_id.in_(brand_ids))
            )
            session.execute(delete(Brand).where(Brand.id.in_(brand_ids)))
            session.execute(delete(Account).where(Account.id.in_(account_ids)))
            session.commit()


def test_two_brands_proving_one_domain_at_once_leave_one_holder(claims, slow_writes):
    barrier = threading.Barrier(THREADS)
    errors: list[BaseException] = []
    found = rules.CheckOutcome("found", dnssec_validated=True)

    def run(due: service.DueCheck) -> None:
        barrier.wait()
        try:
            with SessionLocal() as session:
                service.apply_check(
                    session, due, found, None, CONCURRENCY_NOW + timedelta(minutes=1)
                )
        except DomainError as refused:
            errors.append(refused)
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=run, args=(due,)) for due in claims]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with SessionLocal() as session:
        rows = session.scalars(
            select(BrandDomain).where(BrandDomain.id.in_([d.claim_id for d in claims]))
        ).all()
    assert errors == []
    assert sorted((r.status, r.last_result) for r in rows) == [
        ("pending", "taken"),
        ("verified", "found"),
    ]
