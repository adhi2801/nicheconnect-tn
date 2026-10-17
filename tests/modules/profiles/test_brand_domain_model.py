"""A brand domain claim's rules, held by the database itself (item 74, D-106).

Each test starts from a valid row written with raw SQL, one pending and one
verified, then changes one column inside a savepoint, so exactly one rule is
broken and the error must name it (database.md section 3).
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import build_brand

PENDING = (
    "INSERT INTO brand_domain (brand_id, domain, token, claimed_at, token_expires_at)"
    " VALUES (:brand, :domain, repeat('a', 26), now(), now() + interval '7 days')"
    " RETURNING id"
)
VERIFIED = (
    "INSERT INTO brand_domain (brand_id, domain, token, status, claimed_at,"
    " token_expires_at, verified_at, last_checked_at, last_result)"
    " VALUES (:brand, :domain, repeat('b', 26), 'verified', now(),"
    " now() + interval '7 days', now(), now(), 'found') RETURNING id"
)


def a_domain() -> str:
    return f"shop{uuid.uuid4().hex[:12]}.in"


def a_brand(db: Session) -> uuid.UUID:
    brand = build_brand(db, email=f"model-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    return brand.id


def write(db: Session, sql: str, domain: str | None = None) -> uuid.UUID:
    return db.execute(
        text(sql), {"brand": a_brand(db), "domain": domain or a_domain()}
    ).scalar_one()


@pytest.fixture
def pending(db: Session) -> uuid.UUID:
    return write(db, PENDING)


@pytest.fixture
def verified(db: Session) -> uuid.UUID:
    return write(db, VERIFIED)


def refused(db: Session, sql: str, **values: Any) -> str:
    with pytest.raises(IntegrityError) as caught, db.begin_nested():
        db.execute(text(sql), values)
    return str(caught.value.orig)


def test_the_valid_rows_are_accepted(db, pending, verified):
    """A guard: the tests below break one rule of rows that are otherwise right."""
    count = db.execute(
        text("SELECT count(*) FROM brand_domain WHERE id IN (:a, :b)"),
        {"a": pending, "b": verified},
    ).scalar_one()

    assert count == 2


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ("status = 'approved'", "ck_brand_domain_status_allowed"),
        (
            "last_result = 'maybe', last_checked_at = now()",
            "ck_brand_domain_last_result_allowed",
        ),
        ("domain = 'Shop.in'", "ck_brand_domain_domain_format"),
        ("domain = 'localhost'", "ck_brand_domain_domain_format"),
        ("domain = '-shop.in'", "ck_brand_domain_domain_format"),
        ("domain = 'shop..in'", "ck_brand_domain_domain_format"),
        ("domain = 'xn--nyka-x2a.com'", "ck_brand_domain_domain_format"),
        # One label longer than DNS allows (63); the column caps the whole.
        ("domain = repeat('a', 64) || '.in'", "ck_brand_domain_domain_format"),
        ("token = 'NOT-A-TOKEN'", "ck_brand_domain_token_format"),
        ("token = repeat('a', 25)", "ck_brand_domain_token_format"),
        (
            "token_expires_at = claimed_at + interval '30 days'",
            "ck_brand_domain_token_lasts_seven_days",
        ),
        ("last_checked_at = now()", "ck_brand_domain_checked_with_a_result"),
        ("last_result = 'absent'", "ck_brand_domain_checked_with_a_result"),
        # Pending with a verification time.
        ("verified_at = now()", "ck_brand_domain_verified_at_once_verified"),
        # Verified without one.
        ("status = 'verified'", "ck_brand_domain_verified_at_once_verified"),
        ("consecutive_absent = -1", "ck_brand_domain_consecutive_absent_range"),
        ("consecutive_absent = 4", "ck_brand_domain_consecutive_absent_range"),
    ],
)
def test_a_pending_claim_breaking_a_rule_is_refused(db, pending, change, rule):
    sql = f"UPDATE brand_domain SET {change} WHERE id = :id"  # noqa: S608 - fixed SQL above

    assert rule in refused(db, sql, id=pending)


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        # Lapsed without a time, and a time without lapsing.
        ("status = 'lapsed'", "ck_brand_domain_lapsed_at_when_lapsed"),
        ("lapsed_at = now()", "ck_brand_domain_lapsed_at_when_lapsed"),
        (
            "verified_at = claimed_at - interval '1 minute'",
            "ck_brand_domain_verified_after_claimed",
        ),
        (
            "status = 'lapsed', lapsed_at = verified_at - interval '1 minute'",
            "ck_brand_domain_lapsed_after_verified",
        ),
        # Back to pending would forget it was ever verified.
        ("status = 'pending'", "ck_brand_domain_verified_at_once_verified"),
    ],
)
def test_a_verified_claim_breaking_a_rule_is_refused(db, verified, change, rule):
    sql = f"UPDATE brand_domain SET {change} WHERE id = :id"  # noqa: S608 - fixed SQL above

    assert rule in refused(db, sql, id=verified)


def test_a_brand_has_one_claim(db, pending):
    error = refused(
        db,
        "INSERT INTO brand_domain (brand_id, domain, token, claimed_at, token_expires_at)"
        " SELECT brand_id, 'other.in', token, now(), now() + interval '7 days'"
        " FROM brand_domain WHERE id = :id",
        id=pending,
    )

    assert "uq_brand_domain_brand_id" in error


def test_one_brand_at_a_time_holds_a_verified_domain(db):
    domain = a_domain()
    write(db, VERIFIED, domain)

    error = refused(
        db,
        VERIFIED,
        brand=a_brand(db),
        domain=domain,
    )

    assert "uq_brand_domain_verified_domain" in error


def test_two_brands_may_both_be_waiting_on_one_domain(db):
    """A pending claim blocks nobody: the real owner can always prove theirs."""
    domain = a_domain()
    write(db, PENDING, domain)

    write(db, PENDING, domain)

    count = db.execute(
        text("SELECT count(*) FROM brand_domain WHERE domain = :d"), {"d": domain}
    ).scalar_one()
    assert count == 2


def test_a_claim_goes_with_its_brand(db, pending):
    brand_id = db.execute(
        text("SELECT brand_id FROM brand_domain WHERE id = :id"), {"id": pending}
    ).scalar_one()

    db.execute(text("DELETE FROM brand WHERE id = :id"), {"id": brand_id})

    assert (
        db.execute(
            text("SELECT count(*) FROM brand_domain WHERE id = :id"), {"id": pending}
        ).scalar_one()
        == 0
    )
