"""The database's own rules for step-up codes (item 82, D-107), broken with raw SQL."""

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.step_up_challenge import STEP_UP_TTL, StepUpChallenge
from tests.factories import FIXED_NOW, create_account

HASH = "a" * 64


def _insert(db, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "account_id": account_id,
        "action": "download_export",
        "value_hash": HASH,
        "code_hash": HASH,
        "attempts": 0,
        "created_at": FIXED_NOW,
        "expires_at": FIXED_NOW + STEP_UP_TTL,
        "consumed_at": None,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO step_up_challenge (account_id, action, value_hash, code_hash, "
            "attempts, created_at, expires_at, consumed_at) VALUES (:account_id, "
            ":action, :value_hash, :code_hash, :attempts, :created_at, :expires_at, "
            ":consumed_at)"
        ),
        values,
    )


def test_a_good_row_is_kept(db):
    account = create_account(db, "creator")

    _insert(db, account.id)

    assert db.scalars(
        select(StepUpChallenge.action).where(StepUpChallenge.account_id == account.id)
    ).all() == ["download_export"]


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"action": "delete_account"}, "action_allowed"),
        ({"value_hash": "A" * 64}, "value_hash_format"),
        ({"value_hash": "a" * 63}, "value_hash_format"),
        ({"code_hash": "123456"}, "code_hash_format"),
        ({"attempts": 6}, "attempts_range"),
        ({"attempts": -1}, "attempts_range"),
        (
            {"expires_at": FIXED_NOW + STEP_UP_TTL + timedelta(seconds=1)},
            "expires_five_minutes_after_created",
        ),
        (
            {"expires_at": FIXED_NOW + timedelta(days=1)},
            "expires_five_minutes_after_created",
        ),
        ({"consumed_at": FIXED_NOW - timedelta(seconds=1)}, "consumed_after_created"),
    ],
)
def test_the_database_refuses_a_bad_row(db, overrides, constraint):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match=f"ck_step_up_challenge_{constraint}"):
        _insert(db, account.id, **overrides)


def test_a_code_goes_with_its_account(db):
    account = create_account(db, "creator")
    _insert(db, account.id)

    db.delete(account)
    db.flush()

    assert (
        db.scalars(
            select(StepUpChallenge).where(StepUpChallenge.account_id == account.id)
        ).all()
        == []
    )
