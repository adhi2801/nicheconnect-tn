"""The account table's rules for deletion (item 6, D-122), each broken with raw SQL.

The database holds them, so no bug, script or hand-written query can make a
deletion with no date, a wait other than 30 days, a deletion nobody asked
for, or a deleted account that keeps its number (database.md section 3).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import create_account


def set_fields(db, account_id, assignments: str) -> None:
    db.execute(text(f"UPDATE account SET {assignments} WHERE id = :a"), {"a": account_id})  # noqa: S608 - fixed SQL from the parameters below


@pytest.mark.parametrize(
    ("assignments", "rule"),
    [
        (
            "deletion_requested_at = now()",
            "ck_account_deletion_requested_with_its_date",
        ),
        (
            "deletion_takes_effect_at = now()",
            "ck_account_deletion_requested_with_its_date",
        ),
        (
            "deletion_requested_at = now(),"
            " deletion_takes_effect_at = now() + interval '29 days'",
            "ck_account_deletion_takes_effect_thirty_days_after",
        ),
        (
            "deletion_requested_at = now(),"
            " deletion_takes_effect_at = now() + interval '31 days'",
            "ck_account_deletion_takes_effect_thirty_days_after",
        ),
        (
            "deleted_at = now(), phone = NULL",
            "ck_account_deleted_only_after_a_request",
        ),
        ("phone = NULL", "ck_account_phone_until_deleted"),
        (
            "deletion_requested_at = now() - interval '31 days',"
            " deletion_takes_effect_at = now() - interval '1 day', deleted_at = now()",
            "ck_account_phone_until_deleted",
        ),
    ],
)
def test_the_database_refuses_a_bad_deletion(db, assignments, rule):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match=rule):
        set_fields(db, account.id, assignments)


def test_a_deletion_asked_for_and_one_done_are_both_accepted(db):
    waiting = create_account(db, "creator")
    done = create_account(db, "brand")

    set_fields(
        db,
        waiting.id,
        "deletion_requested_at = now(), deletion_takes_effect_at = now() + interval '30 days'",
    )
    set_fields(
        db,
        done.id,
        "deletion_requested_at = now() - interval '31 days',"
        " deletion_takes_effect_at = now() - interval '1 day',"
        " deleted_at = now(), phone = NULL",
    )


def test_many_deleted_accounts_may_all_lack_a_number(db):
    # The phone stays unique; NULL is not a value, so the numbers let go
    # never collide with one another.
    for _ in range(2):
        account = create_account(db, "creator")
        set_fields(
            db,
            account.id,
            "deletion_requested_at = now() - interval '31 days',"
            " deletion_takes_effect_at = now() - interval '1 day',"
            " deleted_at = now(), phone = NULL",
        )
