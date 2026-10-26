"""The database's own rules for assistants' tokens (item 11, D-138), broken with raw SQL."""

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.agent_token import AgentToken
from tests.factories import FIXED_NOW, create_account

HASH = "a" * 64


def _insert(db, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "account_id": account_id,
        "name": "Claude",
        "token_hash": HASH,
        "scopes": ["deals:read"],
        "expires_at": FIXED_NOW + timedelta(days=90),
        "revoked_at": None,
        "created_at": FIXED_NOW,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO agent_token (account_id, name, token_hash, scopes, expires_at, "
            "revoked_at, created_at, updated_at) VALUES (:account_id, :name, "
            ":token_hash, CAST(:scopes AS varchar[]), :expires_at, :revoked_at, "
            ":created_at, :created_at)"
        ),
        values,
    )


def test_a_good_row_is_kept(db):
    account = create_account(db, "creator")

    _insert(db, account.id)

    assert db.scalars(
        select(AgentToken.scopes).where(AgentToken.account_id == account.id)
    ).all() == [["deals:read"]]


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"token_hash": "A" * 64}, "token_hash_format"),
        ({"token_hash": "nct_" + "a" * 60}, "token_hash_format"),
        ({"name": ""}, "name_shape"),
        ({"name": " Claude"}, "name_shape"),
        ({"name": "Claude\nGPT"}, "name_shape"),
        ({"scopes": []}, "scopes_allowed"),
        ({"scopes": ["deals:read", "payments:write"]}, "scopes_allowed"),
        ({"scopes": ["admin"]}, "scopes_allowed"),
        (
            {"expires_at": FIXED_NOW + timedelta(days=90, seconds=1)},
            "lifetime_within_limit",
        ),
        ({"expires_at": FIXED_NOW}, "lifetime_within_limit"),
        ({"revoked_at": FIXED_NOW - timedelta(seconds=1)}, "revoked_after_made"),
    ],
)
def test_a_bad_row_is_refused(db, overrides, constraint):
    account = create_account(db, "creator")

    with (
        pytest.raises(IntegrityError, match=f"ck_agent_token_{constraint}"),
        db.begin_nested(),
    ):
        _insert(db, account.id, **overrides)


def test_one_hash_is_one_token(db):
    account = create_account(db, "creator")
    _insert(db, account.id)

    with (
        pytest.raises(IntegrityError, match="uq_agent_token_token_hash"),
        db.begin_nested(),
    ):
        _insert(db, account.id)


def test_a_token_goes_with_its_account(db):
    account = create_account(db, "creator")
    _insert(db, account.id)

    db.execute(text("DELETE FROM account WHERE id = :id"), {"id": account.id})

    assert (
        db.scalars(select(AgentToken.id).where(AgentToken.account_id == account.id)).all()
        == []
    )
