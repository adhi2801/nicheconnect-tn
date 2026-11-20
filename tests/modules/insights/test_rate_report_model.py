"""The quarterly rate report's rules, held by the database itself (item 84, D-200).

Each check is broken with raw SQL and refused by name; the seal is shown
refusing every change to a published report but its one withdrawal.
"""

import random
from collections.abc import Callable

import pytest
from psycopg.errors import Diagnostic
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import FIXED_NOW, create_account

SHA = "b" * 64


def refused(db: Session, action: Callable[[], object]) -> Diagnostic:
    with pytest.raises(IntegrityError) as exc_info, db.begin_nested():
        action()
    return exc_info.value.orig.diag


def a_quarter() -> str:
    """A quarter of this test's own: rows other tests leave cannot collide."""
    return f"{random.randint(1000, 9999)}-Q{random.randint(1, 4)}"


def insert(db: Session, **overrides) -> str:
    fields = {
        "quarter": a_quarter(),
        "method_version": 1,
        "body": "{}",
        "body_sha256": SHA,
        "built_at": FIXED_NOW,
        "published_at": None,
        "published_by_account_id": None,
        "withdrawn_at": None,
        "withdrawn_reason": None,
    }
    fields.update(overrides)
    db.execute(
        text(
            "INSERT INTO city_rate_report (quarter, method_version, body, body_sha256,"
            " built_at, published_at, published_by_account_id, withdrawn_at,"
            " withdrawn_reason) VALUES (:quarter, :method_version, CAST(:body AS jsonb),"
            " :body_sha256, :built_at, :published_at, :published_by_account_id,"
            " :withdrawn_at, :withdrawn_reason)"
        ),
        fields,
    )
    return str(fields["quarter"])


def published(db: Session) -> str:
    admin = create_account(db, "admin")
    return insert(db, published_at=FIXED_NOW, published_by_account_id=admin.id)


def test_a_built_report_is_stored(db):
    quarter = insert(db)

    assert (
        db.scalar(
            text("SELECT count(*) FROM city_rate_report WHERE quarter = :q"),
            {"q": quarter},
        )
        == 1
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"quarter": "2026-Q5"}, "ck_city_rate_report_quarter_shape"),
        ({"quarter": "26-Q1"}, "ck_city_rate_report_quarter_shape"),
        ({"method_version": 0}, "ck_city_rate_report_method_version_positive"),
        ({"body": "[]"}, "ck_city_rate_report_body_is_object"),
        ({"body_sha256": "A" * 64}, "ck_city_rate_report_body_sha256_shape"),
        ({"body_sha256": "a" * 63}, "ck_city_rate_report_body_sha256_shape"),
        ({"published_at": FIXED_NOW}, "ck_city_rate_report_published_with_its_admin"),
        (
            {"withdrawn_reason": "A good long reason."},
            "ck_city_rate_report_withdrawn_with_its_reason",
        ),
        (
            {"withdrawn_at": FIXED_NOW, "withdrawn_reason": "A good long reason."},
            "ck_city_rate_report_withdrawn_only_once_published",
        ),
    ],
)
def test_each_rule_is_refused_by_name(db, overrides, constraint):
    said = refused(db, lambda: insert(db, **overrides))

    assert said.constraint_name == constraint


def test_an_admin_is_named_by_a_real_account(db):
    import uuid

    said = refused(
        db,
        lambda: insert(db, published_at=FIXED_NOW, published_by_account_id=uuid.uuid4()),
    )

    assert said.constraint_name == "fk_city_rate_report_published_by_account_id_account"


@pytest.mark.parametrize("reason", ["too short", " " * 12 + "short", "x" * 501])
def test_a_withdrawal_s_reason_has_a_real_length(db, reason):
    admin = create_account(db, "admin")

    said = refused(
        db,
        lambda: insert(
            db,
            published_at=FIXED_NOW,
            published_by_account_id=admin.id,
            withdrawn_at=FIXED_NOW,
            withdrawn_reason=reason,
        ),
    )

    assert said.constraint_name == "ck_city_rate_report_withdrawn_reason_length"


def test_one_report_a_quarter(db):
    quarter = insert(db)

    said = refused(db, lambda: insert(db, quarter=quarter))

    assert said.constraint_name == "uq_city_rate_report_quarter"


def test_the_admin_who_published_cannot_be_deleted(db):
    admin = create_account(db, "admin")
    insert(db, published_at=FIXED_NOW, published_by_account_id=admin.id)

    said = refused(
        db, lambda: db.execute(text("DELETE FROM account WHERE id = :a"), {"a": admin.id})
    )

    assert said.constraint_name == "fk_city_rate_report_published_by_account_id_account"


# --- the seal -------------------------------------------------------------------------


def change(db: Session, quarter: str, assignment: str, **params) -> Callable[[], object]:
    return lambda: db.execute(
        text(f"UPDATE city_rate_report SET {assignment} WHERE quarter = :q"),  # noqa: S608
        {"q": quarter, **params},
    )


def test_an_unpublished_report_can_be_changed_or_removed(db):
    quarter = insert(db)

    change(db, quarter, "body = '{\"a\": 1}'::jsonb")()
    db.execute(text("DELETE FROM city_rate_report WHERE quarter = :q"), {"q": quarter})

    assert (
        db.scalar(
            text("SELECT count(*) FROM city_rate_report WHERE quarter = :q"),
            {"q": quarter},
        )
        == 0
    )


@pytest.mark.parametrize(
    "assignment",
    [
        "body = '{\"a\": 1}'::jsonb",
        "body_sha256 = repeat('c', 64)",
        "method_version = 2",
        "built_at = built_at - interval '1 day'",
        "published_at = published_at + interval '1 day'",
        "quarter = '1999-Q1'",
        "created_at = created_at - interval '1 day'",
    ],
)
def test_a_published_report_never_changes_what_it_says(db, assignment):
    quarter = published(db)

    said = refused(db, change(db, quarter, assignment))

    assert said.message_primary == (
        f"city_rate_report_sealed: {quarter} is published, its figures cannot change"
    )


def test_the_publishing_admin_cannot_be_rewritten(db):
    quarter = published(db)
    other = create_account(db, "admin")

    said = refused(db, change(db, quarter, "published_by_account_id = :a", a=other.id))

    assert "its figures cannot change" in said.message_primary


def test_a_published_report_cannot_be_deleted(db):
    quarter = published(db)

    said = refused(
        db,
        lambda: db.execute(
            text("DELETE FROM city_rate_report WHERE quarter = :q"), {"q": quarter}
        ),
    )

    assert said.message_primary == (
        f"city_rate_report_sealed: {quarter} is published, DELETE refused"
    )


def test_a_published_report_is_withdrawn_once_and_stays_withdrawn(db):
    quarter = published(db)
    withdraw = "withdrawn_at = now(), withdrawn_reason = :r"

    change(db, quarter, withdraw, r="A figure was built from a wrong city.")()
    again = refused(db, change(db, quarter, withdraw, r="Another reason, written later."))
    undone = refused(
        db, change(db, quarter, "withdrawn_at = NULL, withdrawn_reason = NULL")
    )

    assert (
        again.message_primary
        == undone.message_primary
        == (f"city_rate_report_sealed: {quarter} was withdrawn, and stays withdrawn")
    )


def test_updated_at_alone_may_move_on_a_published_report(db):
    quarter = published(db)

    change(db, quarter, "updated_at = now()")()


# The owner: the app's own login has no TRUNCATE right at all (item 97), so
# only the owner reaches the trigger this shows.
@pytest.mark.owner
def test_the_table_cannot_be_emptied(db):
    published(db)

    said = refused(db, lambda: db.execute(text("TRUNCATE city_rate_report")))

    assert said.message_primary == "city_rate_report_sealed: TRUNCATE refused"


def test_the_seal_and_its_triggers_are_in_place(db):
    triggers = set(
        db.scalars(
            text(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = 'city_rate_report'::regclass"
                " AND NOT tgisinternal"
            )
        )
    )

    assert triggers == {"city_rate_report_sealed", "city_rate_report_no_truncate"}


def test_nothing_deleted_by_the_orm_bypasses_the_seal(db):
    from app.modules.insights.rate_report_models import CityRateReport

    quarter = published(db)

    said = refused(
        db,
        lambda: db.execute(
            delete(CityRateReport).where(CityRateReport.quarter == quarter)
        ),
    )

    assert "DELETE refused" in said.message_primary
