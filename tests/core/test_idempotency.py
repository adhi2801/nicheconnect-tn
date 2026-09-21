"""Retrying a POST safely: the store's rules, and the route that applies them."""

from collections.abc import Iterator

import pytest
import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers
from app.core.idempotency import (
    COMPLETED_TTL_SECONDS,
    HEADER,
    IN_FLIGHT_TTL_SECONDS,
    IdempotencyStoreUnavailable,
    InvalidIdempotencyKey,
    Outcome,
    RedisIdempotencyStore,
    StoredResponse,
    check_key,
    fingerprint,
    set_store,
    storage_key,
)
from app.core.idempotent_route import REPLAYED_HEADER, IdempotentRoute

# A database of its own, so these tests cannot disturb the rate-limit
# counters (database 1) or anything the app itself uses (database 0).
REDIS_URL = "redis://localhost:6379/2"
KEY = "3f2a9c11-7b4e-4a51-9d2e-0c1a8e5f6b70"


@pytest.fixture
def store() -> Iterator[RedisIdempotencyStore]:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    client.flushdb()
    made = RedisIdempotencyStore(client)
    set_store(made)
    try:
        yield made
    finally:
        set_store(None)
        client.flushdb()
        client.close()


@pytest.fixture
def calls() -> dict[str, int]:
    return {"count": 0}


@pytest.fixture
def client(store, calls) -> TestClient:
    """A tiny app whose POST records how many times it really ran."""
    app = FastAPI()
    register_error_handlers(app)
    app.router.route_class = IdempotentRoute

    @app.post("/things", status_code=201)
    async def make_thing(body: dict) -> JSONResponse:
        calls["count"] += 1
        return JSONResponse(
            {"id": calls["count"], "name": body.get("name")},
            status_code=201,
            headers={"Location": f"/things/{calls['count']}"},
        )

    @app.get("/things")
    async def list_things() -> dict[str, int]:
        calls["count"] += 1
        return {"count": calls["count"]}

    return TestClient(app)


def post(client, *, key: str | None = KEY, name: str = "first"):
    headers = {HEADER: key} if key else {}
    return client.post("/things", json={"name": name}, headers=headers)


# --- what counts as the same request --------------------------------------


@pytest.mark.parametrize(
    "key",
    [KEY, "apply-3f2a9c11", "a" * 8, "a" * 128, "with.dots_and-dashes:1"],
)
def test_a_sensible_key_is_accepted(key):
    assert check_key(key) == key


@pytest.mark.parametrize("key", ["", "short", "a" * 129, "has space", "emoji-✨"])
def test_an_unusable_key_is_refused(key):
    """Too short a key would collide between clients by accident."""
    with pytest.raises(InvalidIdempotencyKey):
        check_key(key)


def test_the_same_body_has_the_same_fingerprint():
    assert fingerprint(b'{"a":1}') == fingerprint(b'{"a":1}')


def test_a_changed_body_has_a_different_fingerprint():
    assert fingerprint(b'{"a":1}') != fingerprint(b'{"a":2}')


def test_two_people_using_one_key_never_meet():
    mine = storage_key(credential="Bearer aaa", method="POST", path="/x", key=KEY)
    theirs = storage_key(credential="Bearer bbb", method="POST", path="/x", key=KEY)

    assert mine != theirs


def test_the_same_key_on_a_different_endpoint_is_a_different_claim():
    one = storage_key(credential="Bearer aaa", method="POST", path="/x", key=KEY)
    two = storage_key(credential="Bearer aaa", method="POST", path="/y", key=KEY)

    assert one != two


def test_the_same_request_maps_to_the_same_claim():
    args = {"credential": "Bearer aaa", "method": "POST", "path": "/x", "key": KEY}

    assert storage_key(**args) == storage_key(**args)


# --- the store's state machine --------------------------------------------


def test_the_first_caller_gets_the_claim(store):
    assert store.claim("k", "fp").outcome is Outcome.PROCEED


def test_a_second_caller_is_told_it_is_still_running(store):
    store.claim("k", "fp")

    assert store.claim("k", "fp").outcome is Outcome.IN_FLIGHT


def test_once_finished_the_answer_is_replayed(store):
    store.claim("k", "fp")
    store.complete("k", "fp", StoredResponse(201, '{"id":1}', {"location": "/things/1"}))

    claim = store.claim("k", "fp")

    assert claim.outcome is Outcome.REPLAY
    assert claim.response.status == 201
    assert claim.response.body == '{"id":1}'
    assert claim.response.headers == {"location": "/things/1"}


def test_the_same_key_with_a_different_body_is_refused(store):
    store.claim("k", "first")

    assert store.claim("k", "second").outcome is Outcome.BODY_CHANGED


def test_releasing_a_claim_lets_the_next_caller_through(store):
    store.claim("k", "fp")
    store.release("k")

    assert store.claim("k", "fp").outcome is Outcome.PROCEED


def test_a_claim_expires_so_a_dead_process_cannot_block_forever(store):
    store.claim("k", "fp")

    ttl = store.client.ttl("k")

    assert 0 < ttl <= IN_FLIGHT_TTL_SECONDS


def test_a_finished_answer_is_kept_for_the_published_period(store):
    store.claim("k", "fp")
    store.complete("k", "fp", StoredResponse(201, "{}", {}))

    ttl = store.client.ttl("k")

    assert COMPLETED_TTL_SECONDS - 60 < ttl <= COMPLETED_TTL_SECONDS


def test_a_store_that_cannot_be_reached_says_so():
    """Fail closed: the caller asked for exactly-once and we cannot promise it."""
    unreachable = RedisIdempotencyStore(
        redis.Redis.from_url(
            "redis://localhost:6399/0", socket_connect_timeout=1, socket_timeout=1
        )
    )

    with pytest.raises(IdempotencyStoreUnavailable):
        unreachable.claim("k", "fp")


def test_releasing_never_raises_even_when_redis_is_gone():
    """The response already exists; losing the claim is not worth an error."""
    unreachable = RedisIdempotencyStore(
        redis.Redis.from_url(
            "redis://localhost:6399/0", socket_connect_timeout=1, socket_timeout=1
        )
    )

    unreachable.release("k")  # must not raise


# --- the route that uses it -----------------------------------------------


def test_without_a_key_nothing_changes(client, calls):
    assert post(client, key=None).status_code == 201
    assert post(client, key=None).status_code == 201
    assert calls["count"] == 2


def test_a_retry_gets_the_first_answer_and_does_not_run_again(client, calls):
    first = post(client)
    second = post(client)

    assert second.status_code == 201
    assert second.json() == first.json()
    assert calls["count"] == 1, "the endpoint ran twice"


def test_a_replayed_answer_says_it_was_replayed(client):
    post(client)

    second = post(client)

    assert second.headers[REPLAYED_HEADER] == "true"


def test_the_first_answer_is_not_marked_as_replayed(client):
    assert REPLAYED_HEADER.lower() not in post(client).headers


def test_a_replay_keeps_the_location_header(client):
    """A 201 promises where the new thing lives; the retry must say the same."""
    first = post(client)

    second = post(client)

    assert second.headers["location"] == first.headers["location"]
    assert second.headers["content-type"] == first.headers["content-type"]


def test_reusing_a_key_for_a_different_request_is_refused(client, calls):
    post(client, name="first")

    response = post(client, name="second")

    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_reused"
    assert calls["count"] == 1


def test_retrying_while_the_first_is_still_running_is_a_conflict(client, store, calls):
    """Simulated by leaving a claim in flight, which is what a slow first
    request looks like to the second one."""
    body = b'{"name": "first"}'
    held = storage_key(
        credential="testclient", method="POST", path="/things", key=KEY
    )
    store.claim(held, fingerprint(body))

    response = client.post("/things", content=body, headers={HEADER: KEY})

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_key_in_flight"
    assert calls["count"] == 0


def test_an_unusable_key_is_refused_before_any_work_happens(client, calls):
    response = client.post("/things", json={"name": "x"}, headers={HEADER: "short"})

    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_invalid"
    assert calls["count"] == 0


def test_a_get_ignores_the_header(client, calls):
    """Reads are already safe to repeat; nothing should be stored for them."""
    client.get("/things", headers={HEADER: KEY})
    client.get("/things", headers={HEADER: KEY})

    assert calls["count"] == 2


def test_a_different_key_is_a_different_request(client, calls):
    post(client, key=KEY)
    post(client, key="9c1e77aa-0000-4444-8888-1234567890ab")

    assert calls["count"] == 2
