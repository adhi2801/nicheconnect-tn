"""The connection tables' rules, each broken with raw SQL (item 29, D-134)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import build_creator, create_account

CONNECTION_COLUMNS = (
    "creator_id, platform, platform_user_id, handle, access_token_sealed, status,"
    " notice_version, connected_at, verified_followers, verified_as_of"
)


@pytest.fixture
def ids(db) -> dict[str, uuid.UUID]:
    first = build_creator(db, handle=f"c{uuid.uuid4().hex[:12]}")
    second = build_creator(db, handle=f"c{uuid.uuid4().hex[:12]}")
    db.add_all([first, second])
    db.flush()
    return {"first": first.id, "second": second.id, "account": first.account_id}


def connection(db, creator_id, **change) -> None:
    v = {
        "platform": "'instagram'",
        "user": "'1784'",
        "handle": "'priya.eats'",
        "status": "'active'",
        "followers": "NULL",
        "as_of": "NULL",
    } | change
    values = f"(:c, {v['platform']}, {v['user']}, {v['handle']}, '\\x00', {v['status']}, 'v1', now(), {v['followers']}, {v['as_of']})"
    sql = f"INSERT INTO connected_account ({CONNECTION_COLUMNS}) VALUES {values}"  # noqa: S608 - fixed SQL from the parameters above
    db.execute(text(sql), {"c": creator_id})


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ({"platform": "'tiktok'"}, "ck_connected_account_platform_allowed"),
        ({"status": "'gone'"}, "ck_connected_account_status_allowed"),
        (
            {"followers": "-1", "as_of": "now()"},
            "ck_connected_account_followers_not_negative",
        ),
        ({"followers": "10"}, "ck_connected_account_followers_with_their_date"),
        ({"handle": "'  '"}, "ck_connected_account_handle_not_blank"),
    ],
)
def test_the_database_refuses_a_bad_connection(db, ids, change, rule):
    with pytest.raises(IntegrityError, match=rule):
        connection(db, ids["first"], **change)


def test_one_connection_a_platform_per_creator(db, ids):
    connection(db, ids["first"], user="'1'")

    with pytest.raises(IntegrityError, match="uq_connected_account_creator"):
        connection(db, ids["first"], user="'2'")


def test_one_channel_for_one_creator(db, ids):
    connection(db, ids["first"], user="'1784'")

    with pytest.raises(IntegrityError, match="uq_connected_account_platform_user"):
        connection(db, ids["second"], user="'1784'")


def attempt(db, account_id, platform="'instagram'", state="'a'", expires=None) -> None:
    expires = expires or "now() + interval '10 minutes'"
    values = f"(:a, {platform}, {state}, now(), {expires})"
    sql = f"INSERT INTO connection_attempt (account_id, platform, state_sha256, created_at, expires_at) VALUES {values}"  # noqa: S608 - fixed SQL from the parameters above
    db.execute(text(sql), {"a": account_id})


def test_the_database_refuses_a_bad_attempt(db, ids):
    with pytest.raises(IntegrityError, match="ck_connection_attempt_platform_allowed"):
        attempt(db, ids["account"], platform="'tiktok'")


def test_an_attempt_expires_after_it_began(db, ids):
    with pytest.raises(
        IntegrityError, match="ck_connection_attempt_expires_after_created"
    ):
        attempt(db, ids["account"], expires="now()")


def test_a_state_is_held_once(db, ids):
    attempt(db, ids["account"], state="'same'")

    with pytest.raises(IntegrityError, match="uq_connection_attempt_state_sha256"):
        attempt(db, create_account(db, "creator").id, state="'same'")


def deletion(db, code="'abc'", removed="0", platform="'instagram'") -> None:
    values = f"({platform}, {code}, {removed}, now())"
    sql = f"INSERT INTO platform_deletion_request (platform, confirmation_code, removed, received_at) VALUES {values}"  # noqa: S608 - fixed SQL from the parameters above
    db.execute(text(sql))


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ({"platform": "'tiktok'"}, "ck_platform_deletion_request_platform_allowed"),
        ({"removed": "-1"}, "ck_platform_deletion_request_removed_counted"),
    ],
)
def test_the_database_refuses_a_bad_deletion_request(db, change, rule):
    with pytest.raises(IntegrityError, match=rule):
        deletion(db, **change)


def test_a_confirmation_code_is_held_once(db):
    deletion(db, code="'same'")

    with pytest.raises(
        IntegrityError, match="uq_platform_deletion_request_confirmation_code"
    ):
        deletion(db, code="'same'")
