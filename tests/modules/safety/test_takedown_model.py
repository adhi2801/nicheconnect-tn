"""A takedown's rules, held by the database itself (item 52, database.md section 3).

Each test starts from a valid takedown written with raw SQL, then changes one
column inside a savepoint, so exactly one rule is broken and the error must
name it. The clock is the one rule that matters most: an order is due 3
hours after it reached us, it reached us before we acted, and at most 30
days before, so no write can make a late takedown look on time.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import create_account

ORDER = (
    "INSERT INTO takedown (subject_kind, subject_id, owner_account_id, basis,"
    " issued_by, order_reference, legal_provision, received_at, due_at,"
    " withheld_at, withheld_by_account_id, preserved)"
    " VALUES ('campaign', :subject, :owner, 'court_order', 'High Court of Madras',"
    " 'WP 101 of 2026', 'IT Act 2000, section 79(3)(b)',"
    " now() - interval '1 hour', now() + interval '2 hours', now(), :admin,"
    ' \'{"title": "Pongal sweets"}\')'
    " RETURNING id"
)
FROM_REPORT = (
    "INSERT INTO takedown (subject_kind, subject_id, owner_account_id, basis,"
    " report_id, received_at, due_at, withheld_at, withheld_by_account_id, preserved)"
    " SELECT 'creator', :subject, :owner, 'report', r.id, r.created_at, r.due_at,"
    " r.created_at + interval '10 minutes', :admin, '{}' FROM report r WHERE r.id = :report"
    " RETURNING id"
)


@pytest.fixture
def people(db: Session) -> dict[str, uuid.UUID]:
    admin = create_account(db, "admin")
    owner = create_account(db, "brand")
    reporter = create_account(db, "creator")
    report_id = db.execute(
        text(
            "INSERT INTO report (reporter_account_id, subject_kind, subject_id,"
            " category, status, created_at, due_at)"
            " VALUES (:r, 'creator', :s, 'impersonation', 'open', now(),"
            " now() + interval '2 hours') RETURNING id"
        ),
        {"r": reporter.id, "s": uuid.uuid4()},
    ).scalar_one()
    return {
        "admin": admin.id,
        "owner": owner.id,
        "reporter": reporter.id,
        "report": report_id,
    }


def write(db: Session, sql: str, **values: Any) -> uuid.UUID:
    return db.execute(text(sql), values).scalar_one()


@pytest.fixture
def order(db: Session, people) -> uuid.UUID:
    return write(
        db, ORDER, subject=uuid.uuid4(), owner=people["owner"], admin=people["admin"]
    )


@pytest.fixture
def from_report(db: Session, people) -> uuid.UUID:
    return write(
        db,
        FROM_REPORT,
        subject=uuid.uuid4(),
        owner=people["owner"],
        admin=people["admin"],
        report=people["report"],
    )


def refused(db: Session, sql: str, **values: Any) -> str:
    with pytest.raises(IntegrityError) as caught, db.begin_nested():
        db.execute(text(sql), values)
    return str(caught.value.orig)


def test_the_valid_rows_are_accepted(db, order, from_report):
    """A guard: the tests below break one rule of rows that are otherwise right."""
    count = db.execute(
        text("SELECT count(*) FROM takedown WHERE id IN (:a, :b)"),
        {"a": order, "b": from_report},
    ).scalar_one()

    assert count == 2


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ("subject_kind = 'deal_memo'", "ck_takedown_subject_kind_allowed"),
        ("basis = 'rumour'", "ck_takedown_basis_allowed"),
        # An order without who issued it.
        ("issued_by = NULL", "ck_takedown_order_details_only_for_orders"),
        ("order_reference = NULL", "ck_takedown_order_details_only_for_orders"),
        # The clock: 3 hours, never more.
        (
            "due_at = received_at + interval '4 hours'",
            "ck_takedown_order_due_in_three_hours",
        ),
        # Received after it was acted on, keeping the 3-hour rule true.
        (
            "received_at = withheld_at + interval '1 minute',"
            " due_at = withheld_at + interval '3 hours 1 minute'",
            "ck_takedown_received_before_withheld",
        ),
        # A mistyped year: an order "received" long ago looks on time.
        (
            "received_at = withheld_at - interval '31 days',"
            " due_at = withheld_at - interval '31 days' + interval '3 hours'",
            "ck_takedown_received_before_withheld",
        ),
        ("lifted_at = withheld_at + interval '1 hour'", "ck_takedown_lifted_by_someone"),
        (
            "lifted_at = withheld_at - interval '1 minute',"
            " lifted_by_account_id = withheld_by_account_id",
            "ck_takedown_lifted_after_withheld",
        ),
        ("issued_by = 'HC'", "ck_takedown_issued_by_length"),
        ("order_reference = ''", "ck_takedown_order_reference_length"),
        ("legal_provision = 's1'", "ck_takedown_legal_provision_length"),
        ("preserved = '[]'", "ck_takedown_preserved_small_object"),
        (
            "preserved = jsonb_build_object('bio', repeat('x', 20000))",
            "ck_takedown_preserved_small_object",
        ),
    ],
)
def test_an_order_breaking_a_rule_is_refused(db, order, change, rule):
    message = refused(db, f"UPDATE takedown SET {change} WHERE id = :t", t=order)  # noqa: S608 - fixed SQL above

    assert rule in message


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        # A report-based takedown carries no order details, and nothing to seal.
        (
            "issued_by = 'High Court of Madras'",
            "ck_takedown_order_details_only_for_orders",
        ),
        ("legal_provision = 'IT Act 2000'", "ck_takedown_order_details_only_for_orders"),
        ("reference_sealed = true", "ck_takedown_order_details_only_for_orders"),
        # The report's own clock, at most 7 days, after it was filed.
        (
            "due_at = received_at + interval '8 days'",
            "ck_takedown_report_due_within_seven_days",
        ),
        ("due_at = received_at", "ck_takedown_report_due_within_seven_days"),
    ],
)
def test_a_takedown_on_a_report_breaking_a_rule_is_refused(db, from_report, change, rule):
    message = refused(db, f"UPDATE takedown SET {change} WHERE id = :t", t=from_report)  # noqa: S608 - fixed SQL above

    assert rule in message


def test_an_item_has_one_active_takedown(db, people):
    subject = uuid.uuid4()
    write(db, ORDER, subject=subject, owner=people["owner"], admin=people["admin"])

    message = refused(
        db, ORDER, subject=subject, owner=people["owner"], admin=people["admin"]
    )

    assert "uq_takedown_active_subject" in message


def test_a_lifted_takedown_makes_room_for_a_new_one(db, people):
    """A new order after one was lifted is a new takedown, not a conflict."""
    subject = uuid.uuid4()
    first = write(
        db, ORDER, subject=subject, owner=people["owner"], admin=people["admin"]
    )
    db.execute(
        text(
            "UPDATE takedown SET lifted_at = now(), lifted_by_account_id = :a WHERE id = :t"
        ),
        {"a": people["admin"], "t": first},
    )

    second = write(
        db, ORDER, subject=subject, owner=people["owner"], admin=people["admin"]
    )

    assert second != first


def test_an_admin_who_withheld_something_cannot_be_deleted(db, order, people):
    message = refused(db, "DELETE FROM account WHERE id = :a", a=people["admin"])

    assert "fk_takedown_withheld_by_account_id_account" in message


def test_an_admin_who_lifted_something_cannot_be_deleted(db, order, people):
    lifter = create_account(db, "admin")
    db.execute(
        text(
            "UPDATE takedown SET lifted_at = now(), lifted_by_account_id = :a WHERE id = :t"
        ),
        {"a": lifter.id, "t": order},
    )

    message = refused(db, "DELETE FROM account WHERE id = :a", a=lifter.id)

    assert "fk_takedown_lifted_by_account_id_account" in message


def test_the_takedown_outlives_the_report_it_came_from(db, from_report, people):
    """The reporter's account goes, and with it the report; the record stays."""
    db.execute(text("DELETE FROM account WHERE id = :r"), {"r": people["reporter"]})

    report_id = db.execute(
        text("SELECT report_id FROM takedown WHERE id = :t"), {"t": from_report}
    ).one()

    assert report_id == (None,)


def test_the_owner_s_account_going_leaves_the_record(db, order, people):
    """No foreign key to the owner: the law keeps the record, not the account."""
    db.execute(text("DELETE FROM account WHERE id = :o"), {"o": people["owner"]})

    kept = db.execute(
        text("SELECT count(*) FROM takedown WHERE id = :t"), {"t": order}
    ).scalar_one()

    assert kept == 1
