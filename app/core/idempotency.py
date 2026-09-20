"""Make a retried POST safe to send twice.

A creator on patchy mobile data taps "apply", the connection drops before the
reply arrives, and they tap again. Today the second tap either creates a
second thing or returns a confusing error about the first. With an
`Idempotency-Key` header, the second tap gets the answer the first one
earned.

This follows draft-ietf-httpapi-idempotency-key-header-07:

| Situation                                   | Answer |
|---------------------------------------------|--------|
| First time we've seen the key                | run it |
| Same key, same body, original finished       | replay the original response |
| Same key, same body, original still running  | 409 |
| Same key, *different* body                   | 422 |

Two deliberate departures, both written down rather than assumed:

1. **A malformed key is 422, not the draft's 400.** Our own error standard
   (backend.md section 2) sends every invalid input to 422, and one
   consistent rule matters more to the frontend than matching a draft.
2. **Responses that came from a raised error are not stored.** The draft
   allows replaying errors. Ours are deterministic — the same request raises
   the same domain error — so re-running costs nothing, and never storing a
   failure means a server fault can never be replayed back at someone.

Correctness does not rest on this. The database still refuses a genuine
duplicate (one application per creator per campaign). This turns a confusing
error into the right answer; it is not the thing keeping the data honest.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from typing import Any

import redis

from app.core.errors import DomainError
from app.core.redis_client import get_redis

HEADER = "Idempotency-Key"

# A key has to be long enough that two clients don't pick the same one by
# accident. A UUID v4 is the recommended shape; this also allows the prefixed
# keys some clients like ("apply-<uuid>").
KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

# How long a claim may stay "running" before we assume the process died and
# let someone else try. Longer than any request we allow.
IN_FLIGHT_TTL_SECONDS = 60
# How long a finished answer stays replayable. The draft says to pick a
# policy and publish it, so this number appears in the endpoint description.
COMPLETED_TTL_SECONDS = 24 * 60 * 60

KEY_PREFIX = "idem:v1:"

# Response headers worth replaying. An allow-list, so nothing else — a
# cookie, say — can be handed back with a stored response.
REPLAYABLE_HEADERS = ("location", "content-type")
# Tells a client the answer came from the store, not from running the work
# again. Not in the draft; useful when debugging a mobile client.
REPLAYED_HEADER = "Idempotency-Replayed"


class InvalidIdempotencyKey(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "idempotency_key_invalid"
    title = "That Idempotency-Key is not a usable key"


class IdempotentRequestInFlight(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "idempotency_key_in_flight"
    title = "A request is outstanding for this Idempotency-Key"


class IdempotencyKeyReused(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "idempotency_key_reused"
    title = "That Idempotency-Key has already been used for a different request"


class IdempotencyStoreUnavailable(DomainError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "idempotency_unavailable"
    title = "Can't guarantee this request runs only once. Please try again"


class Outcome(str, Enum):
    PROCEED = "proceed"
    REPLAY = "replay"
    IN_FLIGHT = "in_flight"
    BODY_CHANGED = "body_changed"


@dataclass(frozen=True)
class StoredResponse:
    """A finished answer, kept so a retry can be given the same one."""

    status: int
    body: str
    headers: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "body": self.body, "headers": self.headers}


@dataclass(frozen=True)
class Claim:
    outcome: Outcome
    response: StoredResponse | None = None


def check_key(key: str) -> str:
    """Reject a key that is too short or has odd characters."""
    if not KEY_PATTERN.fullmatch(key):
        raise InvalidIdempotencyKey(
            "Use 8 to 128 characters: letters, digits, dot, dash, colon or "
            "underscore. A random UUID is a good choice."
        )
    return key


def fingerprint(body: bytes) -> str:
    """What "the same request" means: the same bytes."""
    return hashlib.sha256(body).hexdigest()


def storage_key(*, credential: str, method: str, path: str, key: str) -> str:
    """Scope a key so it cannot collide with anyone else's.

    The credential is part of the scope, so two people using the same key
    never meet. It is the presented token rather than the account id because
    this runs before the token is decoded; the effect is narrower scoping,
    not wider. A retry after signing in again therefore runs afresh, which
    the database still protects against.
    """
    scope = "\n".join([credential, method.upper(), path, key])
    return KEY_PREFIX + hashlib.sha256(scope.encode()).hexdigest()


class RedisIdempotencyStore:
    """Claims and answers, kept in Redis.

    Redis losing its contents means a retry runs again rather than replaying
    — never a wrong answer, because the database holds the real constraints.
    """

    def __init__(self, client: redis.Redis | None = None) -> None:
        self._client = client

    @property
    def client(self) -> redis.Redis:
        return self._client if self._client is not None else get_redis()

    def claim(self, key: str, request_fingerprint: str) -> Claim:
        """Take the key if it is free; otherwise say what is already there."""
        marker = json.dumps({"state": "in_flight", "fingerprint": request_fingerprint})
        try:
            if self.client.set(key, marker, nx=True, ex=IN_FLIGHT_TTL_SECONDS):
                return Claim(Outcome.PROCEED)
            raw = self.client.get(key)
        except redis.RedisError as error:
            raise IdempotencyStoreUnavailable() from error

        if raw is None:
            # It expired between the set and the get. Nobody holds it now.
            return Claim(Outcome.PROCEED)

        existing = json.loads(raw)
        if existing.get("fingerprint") != request_fingerprint:
            return Claim(Outcome.BODY_CHANGED)
        if existing.get("state") == "in_flight":
            return Claim(Outcome.IN_FLIGHT)
        return Claim(Outcome.REPLAY, StoredResponse(**existing["response"]))

    def complete(
        self, key: str, request_fingerprint: str, response: StoredResponse
    ) -> None:
        """Record the answer, so a retry gets this one."""
        record = json.dumps(
            {
                "state": "done",
                "fingerprint": request_fingerprint,
                "response": response.as_dict(),
            }
        )
        try:
            self.client.set(key, record, ex=COMPLETED_TTL_SECONDS)
        except redis.RedisError as error:
            raise IdempotencyStoreUnavailable() from error

    def release(self, key: str) -> None:
        """Give the key back, so the caller may try again.

        Used when the work failed. Never raises: the request already has an
        answer, and losing the claim only costs a stale key for a minute.
        """
        try:
            self.client.delete(key)
        except redis.RedisError:
            pass


_store: RedisIdempotencyStore | None = None


def get_store() -> RedisIdempotencyStore:
    global _store
    if _store is None:
        _store = RedisIdempotencyStore()
    return _store


def set_store(store: RedisIdempotencyStore | None) -> None:
    """Swap the store. For tests."""
    global _store
    _store = store
