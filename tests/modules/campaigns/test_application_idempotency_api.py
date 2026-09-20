"""Applying twice from a dropped connection must not apply twice.

The scenario this exists for: a creator on patchy mobile data taps "apply",
the reply never arrives, and the app retries. Without an idempotency key the
retry hits the database's one-application-per-campaign rule and comes back as
a confusing 409, even though their first attempt worked. With one, the retry
gets the 201 they never saw.
"""

import uuid
from collections.abc import Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.idempotency import HEADER, RedisIdempotencyStore, set_store
from app.core.idempotent_route import REPLAYED_HEADER
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.campaigns.models import Application
from tests.factories import FIXED_NOW
from tests.modules.campaigns.test_application_api import (
    CAMPAIGNS_URL,
    PITCH,
    Clock,
    brand_with_profile,
    creator_with_profile,
    open_campaign,
)

REDIS_URL = "redis://localhost:6379/2"


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def store() -> Iterator[RedisIdempotencyStore]:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    client.flushdb()
    set_store(RedisIdempotencyStore(client))
    try:
        yield
    finally:
        set_store(None)
        client.flushdb()
        client.close()


@pytest.fixture
def client(db, clock, store) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: clock.now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


@pytest.fixture
def setting(client, db, clock) -> dict:
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    return {
        "creator": creator,
        "campaign_id": open_campaign(client, brand),
    }


def new_key() -> str:
    return str(uuid.uuid4())


def apply_with(client, setting, key: str | None, **overrides):
    body = {"pitch": PITCH, "quoted_amount_paise": 800_000}
    body.update(overrides)
    headers = dict(setting["creator"].headers)
    if key is not None:
        headers[HEADER] = key
    return client.post(
        f"{CAMPAIGNS_URL}/{setting['campaign_id']}/applications",
        json=body,
        headers=headers,
    )


def applications_for(db, campaign_id: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.campaign_id == uuid.UUID(campaign_id))
    )


def test_a_retry_gets_the_original_answer_not_a_confusing_conflict(
    client, db, setting
):
    """The whole point. Without a key the retry would be a 409."""
    key = new_key()
    first = apply_with(client, setting, key)
    assert first.status_code == 201, first.text

    retry = apply_with(client, setting, key)

    assert retry.status_code == 201
    assert retry.json() == first.json()
    assert retry.headers[REPLAYED_HEADER] == "true"


def test_only_one_application_is_ever_created(client, db, setting):
    key = new_key()
    apply_with(client, setting, key)
    apply_with(client, setting, key)
    apply_with(client, setting, key)

    assert applications_for(db, setting["campaign_id"]) == 1


def test_without_a_key_the_second_attempt_is_still_a_conflict(client, db, setting):
    """Unchanged behaviour: the database rule is what keeps the data honest."""
    assert apply_with(client, setting, None).status_code == 201

    second = apply_with(client, setting, None)

    assert second.status_code == 409
    assert second.json()["code"] == "already_applied"
    assert applications_for(db, setting["campaign_id"]) == 1


def test_a_different_pitch_under_the_same_key_is_refused(client, db, setting):
    """Two different requests must not share a key, whichever arrives first."""
    key = new_key()
    apply_with(client, setting, key)

    changed = apply_with(client, setting, key, pitch="A completely different pitch here.")

    assert changed.status_code == 422
    assert changed.json()["code"] == "idempotency_key_reused"
    assert applications_for(db, setting["campaign_id"]) == 1


def test_a_failed_attempt_does_not_burn_the_key(client, db, clock):
    """A domain error is not stored, so fixing the problem and retrying with
    the same key works rather than being refused as a reuse."""
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    key = new_key()
    body = {"pitch": "too short", "quoted_amount_paise": 800_000}

    first = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json=body,
        headers={**creator.headers, HEADER: key},
    )
    assert first.status_code == 422

    fixed = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH, "quoted_amount_paise": 800_000},
        headers={**creator.headers, HEADER: key},
    )

    assert fixed.status_code == 201


def test_two_creators_may_use_the_same_key(client, db, clock):
    """Keys are the client's own; two clients picking the same one must not
    collide, or one creator's answer would land in another's app."""
    brand = brand_with_profile(db, clock)
    first_creator = creator_with_profile(db, clock, handle="priya.eats")
    second_creator = creator_with_profile(db, clock, handle="ravi.tech")
    campaign_id = open_campaign(client, brand)
    shared = new_key()
    body = {"pitch": PITCH, "quoted_amount_paise": 800_000}

    one = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json=body,
        headers={**first_creator.headers, HEADER: shared},
    )
    two = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json=body,
        headers={**second_creator.headers, HEADER: shared},
    )

    assert one.status_code == 201
    assert two.status_code == 201
    assert one.json()["id"] != two.json()["id"]
    assert applications_for(db, campaign_id) == 2


def test_a_retry_still_replays_after_the_client_refreshed_its_token(
    client, db, setting
):
    """Retries are grouped by account, not by the token presented.

    A mobile client that refreshed its access token between the dropped
    request and the retry must still get its first answer, or the refresh
    itself would cause the double submission this feature exists to stop.
    """
    key = new_key()
    first_headers = dict(setting["creator"].headers)
    first = client.post(
        f"{CAMPAIGNS_URL}/{setting['campaign_id']}/applications",
        json={"pitch": PITCH, "quoted_amount_paise": 800_000},
        headers={**first_headers, HEADER: key},
    )
    assert first.status_code == 201

    # A freshly minted token: a different string, the same person.
    retry_headers = dict(setting["creator"].headers)
    assert retry_headers["Authorization"] != first_headers["Authorization"]
    retry = client.post(
        f"{CAMPAIGNS_URL}/{setting['campaign_id']}/applications",
        json={"pitch": PITCH, "quoted_amount_paise": 800_000},
        headers={**retry_headers, HEADER: key},
    )

    assert retry.status_code == 201
    assert retry.json() == first.json()
    assert applications_for(db, setting["campaign_id"]) == 1


def test_a_forged_token_cannot_read_back_someone_elses_answer(client, db, setting):
    """Scoping trusts the signature, not the claim.

    An unsigned token naming the victim's account must not land in the
    victim's bucket, or replay would hand their response to a stranger.
    """
    import jwt

    key = new_key()
    first = apply_with(client, setting, key)
    assert first.status_code == 201

    victim_account = setting["creator"].account_id
    forged = jwt.encode(
        {
            "sub": str(victim_account),
            "role": "creator",
            "typ": "access",
            "iat": 0,
            "exp": 9999999999,
            "jti": "forged",
        },
        "not-the-signing-key-at-all-not-even-close",
        algorithm="HS256",
        headers={"kid": "k1"},
    )

    response = client.post(
        f"{CAMPAIGNS_URL}/{setting['campaign_id']}/applications",
        json={"pitch": PITCH, "quoted_amount_paise": 800_000},
        headers={"Authorization": f"Bearer {forged}", HEADER: key},
    )

    # Rejected by authentication, and crucially not given the stored answer.
    assert response.status_code == 401
    assert REPLAYED_HEADER.lower() not in response.headers
    assert first.json()["id"] not in response.text
