"""An authenticator factor's rules, held by the database itself (item 101, D-105).

Each test starts from a valid row written with raw SQL, one waiting for
setup and one enrolled, then changes one column inside a savepoint, so
exactly one rule is broken and the error must name it (database.md
section 3).
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import create_account

WAITING = (
    "INSERT INTO totp_factor (account_id, ticket_hash, ticket_expires_at)"
    " VALUES (:account, repeat('a', 64), now() + interval '15 minutes') RETURNING id"
)
ENROLLED = (
    "INSERT INTO totp_factor (account_id, secret_ciphertext, enrolled_at,"
    " last_used_step) VALUES (:account, decode(repeat('ab', 48), 'hex'), now(),"
    " 59000000) RETURNING id"
)


def write(db: Session, sql: str) -> uuid.UUID:
    account = create_account(db, "admin")
    db.flush()
    return db.execute(text(sql), {"account": account.id}).scalar_one()


@pytest.fixture
def waiting(db: Session) -> uuid.UUID:
    return write(db, WAITING)


@pytest.fixture
def enrolled(db: Session) -> uuid.UUID:
    return write(db, ENROLLED)


def refused(db: Session, sql: str, **values: Any) -> str:
    with pytest.raises(IntegrityError) as caught, db.begin_nested():
        db.execute(text(sql), values)
    return str(caught.value.orig)


def test_the_valid_rows_are_accepted(db, waiting, enrolled):
    """A guard: the tests below break one rule of rows that are otherwise right."""
    count = db.execute(
        text("SELECT count(*) FROM totp_factor WHERE id IN (:a, :b)"),
        {"a": waiting, "b": enrolled},
    ).scalar_one()

    assert count == 2


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        # Neither waiting nor enrolled.
        (
            "ticket_hash = NULL, ticket_expires_at = NULL",
            "ck_totp_factor_waiting_or_enrolled",
        ),
        ("ticket_expires_at = NULL", "ck_totp_factor_ticket_has_an_expiry"),
        ("ticket_hash = 'not-a-hash'", "ck_totp_factor_ticket_hash_format"),
        ("ticket_hash = repeat('A', 64)", "ck_totp_factor_ticket_hash_format"),
        # Ten wrong codes in a row and still open.
        ("consecutive_failures = 10", "ck_totp_factor_locked_at_the_limit"),
        # Locked without the failures that lock it.
        ("locked_at = now()", "ck_totp_factor_locked_at_the_limit"),
        ("consecutive_failures = -1", "ck_totp_factor_consecutive_failures_range"),
        ("consecutive_failures = 11", "ck_totp_factor_consecutive_failures_range"),
    ],
)
def test_a_waiting_factor_breaking_a_rule_is_refused(db, waiting, change, rule):
    sql = f"UPDATE totp_factor SET {change} WHERE id = :id"  # noqa: S608 - fixed SQL above
    error = refused(db, sql, id=waiting)

    assert rule in error


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        # Both waiting and enrolled at once.
        (
            "ticket_hash = repeat('b', 64), ticket_expires_at = now()",
            "ck_totp_factor_waiting_or_enrolled",
        ),
        ("enrolled_at = NULL", "ck_totp_factor_enrolled_when_it_has_a_secret"),
        (
            "secret_ciphertext = decode('abcd', 'hex')",
            "ck_totp_factor_secret_ciphertext_length",
        ),
        ("last_used_step = -1", "ck_totp_factor_last_used_step_not_negative"),
    ],
)
def test_an_enrolled_factor_breaking_a_rule_is_refused(db, enrolled, change, rule):
    sql = f"UPDATE totp_factor SET {change} WHERE id = :id"  # noqa: S608 - fixed SQL above
    error = refused(db, sql, id=enrolled)

    assert rule in error


def test_an_account_has_one_factor(db, waiting):
    error = refused(
        db,
        "INSERT INTO totp_factor (account_id, ticket_hash, ticket_expires_at)"
        " SELECT account_id, repeat('c', 64), now() FROM totp_factor WHERE id = :id",
        id=waiting,
    )

    assert "uq_totp_factor_account_id" in error


def test_a_factor_goes_with_its_account(db, enrolled):
    account_id = db.execute(
        text("SELECT account_id FROM totp_factor WHERE id = :id"), {"id": enrolled}
    ).scalar_one()

    db.execute(text("DELETE FROM account WHERE id = :id"), {"id": account_id})

    remaining = db.execute(
        text("SELECT count(*) FROM totp_factor WHERE id = :id"), {"id": enrolled}
    ).scalar_one()
    assert remaining == 0
