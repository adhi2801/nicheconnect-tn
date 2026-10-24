"""A new sign-in on the attention list (item 81, D-114), through the API.

A sign-in its owner did not make is the first sign of a SIM swap. Each
other live session that signed in during the last 7 days is listed first,
before anything due, until it is ended or its 7 days pass.
"""

import uuid
from datetime import timedelta

import pytest

from app.modules.auth import service as login
from app.modules.auth.models.account import Account
from app.modules.auth.service import ClientDevice
from tests.deal_flow import accepted_memo, brand_user, creator_user
from tests.query_counts import queries_for

ATTENTION_URL = "/api/v1/me/attention"
PIXEL = ClientDevice(platform="android", label="Pixel 8")
CHROME = ClientDevice(platform="web", label="Chrome on Windows")


def sign_in(db, account_id, clock, device=None, **kw):
    account = db.get_one(Account, account_id)
    result = login.issue_session(
        db, account, uuid.uuid4(), clock.now, device=device, **kw
    )
    db.flush()
    return result


def auth(result) -> dict[str, str]:
    return {"Authorization": f"Bearer {result.access_token}"}


def new_sign_ins(client, result) -> list[dict]:
    response = client.get(ATTENTION_URL, headers=auth(result))
    assert response.status_code == 200, response.text
    return [item for item in response.json()["items"] if item["kind"] == "new_sign_in"]


@pytest.fixture
def creator(db, clock):
    return creator_user(db, clock)


def test_another_recent_sign_in_is_listed_with_its_device(client, db, clock, creator):
    other = sign_in(db, creator.account_id, clock, PIXEL)
    # Within the other's 15-minute access token, so it can ask too.
    clock.advance(timedelta(minutes=10))
    mine = sign_in(db, creator.account_id, clock, CHROME, passkey_at=clock.now)

    [item] = new_sign_ins(client, mine)

    assert item["device_platform"] == "android"
    assert item["device_label"] == "Pixel 8"
    assert item["signed_in_with"] == "phone_code"
    assert item["due_on"] is None
    assert item["campaign_id"] is None
    assert item["signed_in_at"].startswith(
        (clock.now - timedelta(minutes=10)).isoformat()[:19]
    )
    other_body = client.get(ATTENTION_URL, headers=auth(other)).json()
    [seen_from_other] = [i for i in other_body["items"] if i["kind"] == "new_sign_in"]
    assert seen_from_other["device_label"] == "Chrome on Windows"
    assert seen_from_other["signed_in_with"] == "passkey"
    assert other_body["counts"]["new_sign_in"] == 1


def test_the_session_asking_is_never_listed(client, db, clock, creator):
    mine = sign_in(db, creator.account_id, clock, PIXEL)

    assert new_sign_ins(client, mine) == []


def test_a_sign_in_leaves_the_list_when_ended(client, db, clock, creator):
    other = sign_in(db, creator.account_id, clock, PIXEL)
    mine = sign_in(db, creator.account_id, clock, CHROME)

    login.logout(db, other.refresh_token, clock.now)

    assert new_sign_ins(client, mine) == []


def test_a_sign_in_leaves_the_list_seven_days_after_it_was_made(
    client, db, clock, creator
):
    sign_in(db, creator.account_id, clock, PIXEL)
    clock.advance(timedelta(days=7))
    mine = sign_in(db, creator.account_id, clock, CHROME)

    assert new_sign_ins(client, mine) == []
    clock.advance(timedelta(seconds=-1))
    assert len(new_sign_ins(client, mine)) == 1


def test_a_new_sign_in_comes_before_anything_due(client, db, clock):
    """A creator with work to deliver still sees the sign-in first."""
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)

    accepted_memo(client, brand, creator)
    sign_in(db, creator.account_id, clock, PIXEL)
    mine = sign_in(db, creator.account_id, clock, CHROME)

    items = client.get(ATTENTION_URL, headers=auth(mine)).json()["items"]

    assert len(items) > 1
    assert items[0]["kind"] == "new_sign_in"


def test_new_sign_ins_cost_one_query_however_many(client, db, clock, creator):
    mine = sign_in(db, creator.account_id, clock, CHROME)
    sign_in(db, creator.account_id, clock, PIXEL)
    few = queries_for(client, ATTENTION_URL, auth(mine))
    for _ in range(6):
        sign_in(db, creator.account_id, clock, PIXEL)

    assert queries_for(client, ATTENTION_URL, auth(mine)) == few


def test_a_brand_sees_its_new_sign_ins_too(client, db, clock):
    brand = brand_user(db, clock)
    sign_in(db, brand.account_id, clock, PIXEL)
    mine = sign_in(db, brand.account_id, clock, CHROME)

    assert len(new_sign_ins(client, mine)) == 1
