"""The device_token table holds its own rules (item 9, D-095).

Each forbidden row is written past the code, and the database refuses it.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from tests.factories import FIXED_NOW, create_account

INSERT = (
    "INSERT INTO device_token (account_id, platform, token, app_version, last_seen_at)"
    " VALUES (:account_id, :platform, :token, :app_version, :seen)"
)


def row(account_id, **overrides) -> dict:
    values = {
        "account_id": account_id,
        "platform": "android",
        "token": uuid.uuid4().hex * 2,
        "app_version": None,
        "seen": FIXED_NOW,
    }
    values.update(overrides)
    return values


def refused(db, values: dict, constraint: str) -> None:
    with pytest.raises(IntegrityError) as exc_info, db.begin_nested():
        db.execute(text(INSERT), values)
    assert constraint in str(exc_info.value)


@pytest.fixture
def account_id(db):
    return create_account(db, "creator").id


def test_a_well_formed_row_is_kept(db, account_id):
    db.execute(text(INSERT), row(account_id, app_version="1.4.0"))


@pytest.mark.parametrize("platform", ["web", "windows", ""])
def test_an_unknown_platform_is_refused(db, account_id, platform):
    refused(db, row(account_id, platform=platform), "platform_allowed")


@pytest.mark.parametrize("token", ["x" * 31, "has a space" + "x" * 40, "é" * 40])
def test_a_token_of_the_wrong_shape_is_refused(db, account_id, token):
    refused(db, row(account_id, token=token), "token_shape")


def test_a_token_past_the_column_is_refused(db, account_id):
    with pytest.raises(DataError), db.begin_nested():
        db.execute(text(INSERT), row(account_id, token="x" * 1025))


def test_an_empty_app_version_is_refused(db, account_id):
    refused(db, row(account_id, app_version=""), "app_version_length")


def test_one_token_has_one_owner(db, account_id):
    token = uuid.uuid4().hex * 2
    db.execute(text(INSERT), row(account_id, token=token))
    other = create_account(db, "brand").id

    refused(db, row(other, token=token), "uq_device_token_token")


def test_a_device_needs_a_real_account(db):
    refused(db, row(uuid.uuid4()), "fk_device_token_account_id_account")


def test_a_deleted_account_takes_its_phones_with_it(db, account_id):
    db.execute(text(INSERT), row(account_id))

    db.execute(text("DELETE FROM account WHERE id = :id"), {"id": account_id})

    left = db.execute(
        text("SELECT count(*) FROM device_token WHERE account_id = :id"),
        {"id": account_id},
    ).scalar_one()
    assert left == 0
