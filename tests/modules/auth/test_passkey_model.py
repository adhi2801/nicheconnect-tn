"""The database's own rules for passkeys (D-113), broken with raw SQL."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import FIXED_NOW, create_account

HASH = "a" * 64


def insert_passkey(db, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "account_id": account_id,
        "credential_id": uuid.uuid4().bytes,
        "public_key": b"\xa1\x01\x02",
        "sign_count": 0,
        "aaguid": uuid.UUID(int=0),
        "backup_eligible": True,
        "backup_state": True,
        "name": "My phone",
        "last_used_at": None,
        "created_at": FIXED_NOW,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO passkey (account_id, credential_id, public_key, sign_count, "
            "aaguid, backup_eligible, backup_state, name, last_used_at, created_at) "
            "VALUES (:account_id, :credential_id, :public_key, :sign_count, :aaguid, "
            ":backup_eligible, :backup_state, :name, :last_used_at, :created_at)"
        ),
        values,
    )


def insert_challenge(db, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "account_id": account_id,
        "purpose": "register",
        "challenge": uuid.uuid4().bytes * 2,
        "action": None,
        "value_hash": None,
        "created_at": FIXED_NOW,
        "expires_at": FIXED_NOW + timedelta(minutes=5),
        "consumed_at": None,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO passkey_challenge (account_id, purpose, challenge, action, "
            "value_hash, created_at, expires_at, consumed_at) VALUES (:account_id, "
            ":purpose, :challenge, :action, :value_hash, :created_at, :expires_at, "
            ":consumed_at)"
        ),
        values,
    )


def test_good_rows_are_kept(db):
    account = create_account(db, "creator")

    insert_passkey(db, account.id)
    insert_challenge(db, account.id)
    insert_challenge(db, None, purpose="login")
    insert_challenge(
        db, account.id, purpose="step_up", action="add_passkey", value_hash=HASH
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"credential_id": b"short"}, "credential_id_length"),
        ({"credential_id": b"x" * 1024}, "credential_id_length"),
        ({"public_key": b""}, "public_key_length"),
        ({"public_key": b"x" * 1025}, "public_key_length"),
        ({"sign_count": -1}, "sign_count_not_negative"),
        ({"name": "   "}, "name_not_blank"),
        ({"backup_eligible": False, "backup_state": True}, "backed_up_only_if_eligible"),
        ({"last_used_at": FIXED_NOW - timedelta(seconds=1)}, "used_after_added"),
    ],
)
def test_the_database_refuses_a_bad_passkey(db, overrides, constraint):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match=f"ck_passkey_{constraint}"):
        insert_passkey(db, account.id, **overrides)


def test_a_key_belongs_to_one_account_only(db):
    shared = uuid.uuid4().bytes
    insert_passkey(db, create_account(db, "creator").id, credential_id=shared)

    with pytest.raises(IntegrityError, match="uq_passkey_credential_id"):
        insert_passkey(db, create_account(db, "brand").id, credential_id=shared)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"purpose": "recover"}, "purpose_allowed"),
        ({"challenge": b"x" * 31}, "challenge_length"),
        ({"account_id": None}, "account_unless_login"),
        ({"purpose": "step_up"}, "change_only_for_step_up"),
        ({"action": "add_passkey", "value_hash": HASH}, "change_only_for_step_up"),
        (
            {"purpose": "step_up", "action": "fly", "value_hash": HASH},
            "action_allowed",
        ),
        (
            {"purpose": "step_up", "action": "add_passkey", "value_hash": "A" * 64},
            "value_hash_format",
        ),
        (
            {"expires_at": FIXED_NOW + timedelta(minutes=6)},
            "expires_five_minutes_after_created",
        ),
        ({"consumed_at": FIXED_NOW - timedelta(seconds=1)}, "consumed_after_created"),
    ],
)
def test_the_database_refuses_a_bad_challenge(db, overrides, constraint):
    account = create_account(db, "creator")
    values = {"account_id": account.id, **overrides}
    account_id = values.pop("account_id")

    with pytest.raises(IntegrityError, match=f"ck_passkey_challenge_{constraint}"):
        insert_challenge(db, account_id, **values)


def test_a_challenge_is_never_sent_twice(db):
    account = create_account(db, "creator")
    same = b"c" * 32
    insert_challenge(db, account.id, challenge=same)

    with pytest.raises(IntegrityError, match="uq_passkey_challenge_challenge"):
        insert_challenge(db, account.id, challenge=same)


def insert_reset(db, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "account_id": account_id,
        "requested_at": FIXED_NOW,
        "takes_effect_at": FIXED_NOW + timedelta(days=7),
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO passkey_reset (account_id, requested_at, takes_effect_at) "
            "VALUES (:account_id, :requested_at, :takes_effect_at)"
        ),
        values,
    )


def test_a_reset_takes_exactly_seven_days(db):
    account = create_account(db, "creator")

    with pytest.raises(
        IntegrityError, match="ck_passkey_reset_takes_effect_seven_days_after_request"
    ):
        insert_reset(db, account.id, takes_effect_at=FIXED_NOW + timedelta(days=6))


def test_one_reset_waits_at_a_time(db):
    account = create_account(db, "creator")
    insert_reset(db, account.id)

    with pytest.raises(IntegrityError, match="uq_passkey_reset_account_id"):
        insert_reset(db, account.id)


def test_a_step_up_code_is_proven_one_of_two_ways(db):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match="ck_step_up_challenge_method_allowed"):
        db.execute(
            text(
                "INSERT INTO step_up_challenge (account_id, action, value_hash, "
                "code_hash, method, created_at, expires_at) VALUES (:a, "
                "'log_out_everywhere', :h, :h, 'pigeon', :now, :exp)"
            ),
            {
                "a": account.id,
                "h": HASH,
                "now": FIXED_NOW,
                "exp": FIXED_NOW + timedelta(minutes=5),
            },
        )
