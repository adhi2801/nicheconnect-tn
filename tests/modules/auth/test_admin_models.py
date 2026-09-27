"""The admin schema's rules, enforced by the database itself (D-061)."""

import uuid
from collections.abc import Callable

import pytest
from psycopg.errors import Diagnostic
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.account import Account
from app.modules.auth.models.admin_action import AdminAction
from app.modules.auth.models.report import Report
from tests.factories import FIXED_NOW, create_account


def refused(db, action: Callable[[], object]) -> Diagnostic:
    """Run `action` in a savepoint and return what the database said."""
    with pytest.raises(IntegrityError) as exc_info, db.begin_nested():
        action()
    return exc_info.value.orig.diag


def adding(db, row) -> Callable[[], None]:
    def add() -> None:
        db.add(row)
        db.flush()

    return add


def report(reporter: Account, **overrides) -> Report:
    fields = {
        "reporter_account_id": reporter.id,
        "subject_kind": "creator",
        "subject_id": uuid.uuid4(),
        "category": "fake_profile",
        "status": "open",
    }
    fields.update(overrides)
    return Report(**fields)


# --- accounts ---------------------------------------------------------------------


def test_an_admin_account_is_allowed(db):
    assert create_account(db, "admin").role == "admin"


def test_an_unknown_role_is_refused(db):
    said = refused(db, adding(db, Account(phone="+919000066601", role="superuser")))

    assert said.constraint_name == "ck_account_role_allowed"


def test_a_suspension_always_says_why(db):
    account = create_account(db, "creator")

    said = refused(
        db,
        lambda: db.execute(
            update(Account).where(Account.id == account.id).values(suspended_at=FIXED_NOW)
        ),
    )

    assert said.constraint_name == "ck_account_suspension_has_reason"


def test_a_reason_without_a_suspension_is_refused(db):
    account = create_account(db, "creator")

    said = refused(
        db,
        lambda: db.execute(
            update(Account)
            .where(Account.id == account.id)
            .values(suspension_reason="spam")
        ),
    )

    assert said.constraint_name == "ck_account_suspension_has_reason"


def test_a_suspension_reason_must_be_a_known_category(db):
    account = create_account(db, "creator")

    said = refused(
        db,
        lambda: db.execute(
            update(Account)
            .where(Account.id == account.id)
            .values(suspended_at=FIXED_NOW, suspension_reason="looked_at_me_funny")
        ),
    )

    assert said.constraint_name == "ck_account_suspension_reason_allowed"


# --- reports ---------------------------------------------------------------------------


def test_one_open_report_per_reporter_per_subject(db):
    reporter = create_account(db, "brand")
    subject = uuid.uuid4()
    db.add(report(reporter, subject_id=subject))
    db.flush()

    said = refused(db, adding(db, report(reporter, subject_id=subject)))

    assert said.constraint_name == "uq_report_open_per_reporter"


def test_a_resolved_report_does_not_block_a_new_one(db):
    reporter = create_account(db, "brand")
    subject = uuid.uuid4()
    db.add(
        report(reporter, subject_id=subject, status="dismissed", resolved_at=FIXED_NOW)
    )
    db.flush()

    db.add(report(reporter, subject_id=subject))
    db.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"subject_kind": "deal_memo"}, "subject_kind_allowed"),
        ({"category": "boring"}, "category_allowed"),
        ({"status": "ignored", "resolved_at": FIXED_NOW}, "status_allowed"),
        ({"note": "x" * 1001}, "note_length"),
        ({"resolution_note": "x" * 1001}, "resolution_note_length"),
        ({"status": "actioned"}, "resolved_when_closed"),
        ({"resolved_at": FIXED_NOW}, "resolved_when_closed"),
    ],
)
def test_report_rules_are_enforced_by_the_database(db, overrides, constraint):
    reporter = create_account(db, "creator")

    said = refused(db, adding(db, report(reporter, **overrides)))

    assert said.constraint_name == f"ck_report_{constraint}"


# --- the admin log ---------------------------------------------------------------------


def logged(db) -> AdminAction:
    admin = create_account(db, "admin")
    row = AdminAction(
        admin_account_id=admin.id, action="view_account", note="caller asked"
    )
    db.add(row)
    db.flush()
    return row


def test_the_log_cannot_be_changed_or_emptied(db):
    row = logged(db)

    changed = refused(
        db,
        lambda: db.execute(
            update(AdminAction).where(AdminAction.id == row.id).values(note="x")
        ),
    )
    removed = refused(
        db, lambda: db.execute(delete(AdminAction).where(AdminAction.id == row.id))
    )
    emptied = refused(db, lambda: db.execute(text("TRUNCATE admin_action")))

    assert changed.message_primary == "admin_action is append-only: UPDATE refused"
    assert removed.message_primary == "admin_action is append-only: DELETE refused"
    assert emptied.message_primary == "admin_action is append-only: TRUNCATE refused"


def test_an_admin_who_acted_cannot_be_deleted(db):
    row = logged(db)

    said = refused(
        db, lambda: db.execute(delete(Account).where(Account.id == row.admin_account_id))
    )

    assert said.constraint_name == "fk_admin_action_admin_account_id_account"


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"action": "delete_user"}, "action_allowed"),
        ({"note": "x" * 1001}, "note_length"),
    ],
)
def test_log_rules_are_enforced_by_the_database(db, overrides, constraint):
    admin = create_account(db, "admin")
    fields = {"admin_account_id": admin.id, "action": "suspend"}
    fields.update(overrides)

    said = refused(db, adding(db, AdminAction(**fields)))

    assert said.constraint_name == f"ck_admin_action_{constraint}"
