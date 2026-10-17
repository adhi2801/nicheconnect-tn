"""The database's own rules for a waiting phone number change (item 80, D-108), broken with raw SQL."""

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.account_phone_change import (
    PHONE_CHANGE_WAIT,
    AccountPhoneChange,
)
from tests.factories import FIXED_NOW, create_account, unique_test_phone


def _insert(db, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "account_id": account_id,
        "new_phone": unique_test_phone(),
        "requested_at": FIXED_NOW,
        "takes_effect_at": FIXED_NOW + PHONE_CHANGE_WAIT,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO account_phone_change "
            "(account_id, new_phone, requested_at, takes_effect_at) "
            "VALUES (:account_id, :new_phone, :requested_at, :takes_effect_at)"
        ),
        values,
    )


def test_a_good_row_is_kept(db):
    account = create_account(db, "creator")

    _insert(db, account.id, new_phone="+919812300001")

    assert db.scalars(
        select(AccountPhoneChange.new_phone).where(
            AccountPhoneChange.account_id == account.id
        )
    ).all() == ["+919812300001"]


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"new_phone": "9812300001"}, "new_phone_format"),
        ({"new_phone": "+919812300001 "}, "new_phone_format"),
        ({"new_phone": "+915812300001"}, "new_phone_format"),
        (
            {"takes_effect_at": FIXED_NOW + PHONE_CHANGE_WAIT - timedelta(seconds=1)},
            "takes_effect_three_days_after_request",
        ),
        ({"takes_effect_at": FIXED_NOW}, "takes_effect_three_days_after_request"),
        (
            {"takes_effect_at": FIXED_NOW + timedelta(days=30)},
            "takes_effect_three_days_after_request",
        ),
    ],
)
def test_the_database_refuses_a_bad_row(db, overrides, constraint):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match=f"ck_account_phone_change_{constraint}"):
        _insert(db, account.id, **overrides)


def test_an_account_waits_on_one_number_at_most(db):
    account = create_account(db, "brand")
    _insert(db, account.id)

    with pytest.raises(IntegrityError, match="uq_account_phone_change_account_id"):
        _insert(db, account.id)


def test_two_accounts_cannot_wait_on_the_same_number(db):
    phone = unique_test_phone()
    _insert(db, create_account(db, "brand").id, new_phone=phone)

    with pytest.raises(IntegrityError, match="uq_account_phone_change_new_phone"):
        _insert(db, create_account(db, "creator").id, new_phone=phone)


def test_a_waiting_change_goes_with_its_account(db):
    account = create_account(db, "creator")
    _insert(db, account.id)

    db.delete(account)
    db.flush()

    assert (
        db.scalars(
            select(AccountPhoneChange).where(AccountPhoneChange.account_id == account.id)
        ).first()
        is None
    )
