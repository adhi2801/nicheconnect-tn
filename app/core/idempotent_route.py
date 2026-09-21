"""Wire idempotency into a router without touching any endpoint.

A router built with `route_class=IdempotentRoute` accepts an
`Idempotency-Key` header on its POSTs. Endpoints stay exactly as they were:
no extra parameter, no extra dependency, nothing to remember. That matters,
because the failure mode of an opt-in safety feature is somebody forgetting
to opt in.

A route class is used rather than middleware because middleware cannot tell
which routes opted in, and rather than a dependency because a dependency
never sees the response it would need to store.

Requests without the header behave exactly as before.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.core.idempotency import (
    COMPLETED_TTL_SECONDS,
    HEADER,
    REPLAYABLE_HEADERS,
    REPLAYED_HEADER,
    Claim,
    IdempotencyKeyReused,
    IdempotentRequestInFlight,
    Outcome,
    StoredResponse,
    check_key,
    fingerprint,
    get_store,
    storage_key,
)

# Only methods that are not already idempotent by definition. GET, PUT and
# DELETE either change nothing or land on the same state however many times
# they arrive.
GUARDED_METHODS = frozenset({"POST", "PATCH"})

# A server fault must never be stored: the retry is exactly when we want the
# work attempted again.
MAX_STORABLE_STATUS = 500


# Who a request belongs to. The app sets this at start-up (see app/main.py)
# to something that reads the verified account out of the access token. It is
# a hook rather than a direct import because `app/core` must not depend on a
# module; the composition root wires the two together.
_identity_resolver: Callable[[Request], str | None] | None = None


def set_identity_resolver(resolver: Callable[[Request], str | None] | None) -> None:
    """Tell the route how to work out whose request this is."""
    global _identity_resolver
    _identity_resolver = resolver


def _credential(request: Request) -> str:
    """What identifies the caller for scoping purposes.

    The resolver gives a stable answer — the account — so a retry still
    replays after the client has refreshed its token. Without one, the raw
    credential is used, and failing that the client address, so an
    unauthenticated caller still cannot reach another caller's keys.
    """
    if _identity_resolver is not None:
        identity = _identity_resolver(request)
        if identity:
            return identity
    authorization = request.headers.get("authorization")
    if authorization:
        return authorization
    return request.client.host if request.client else "anonymous"


def _to_stored(response: Response) -> StoredResponse:
    headers = {
        name: response.headers[name]
        for name in REPLAYABLE_HEADERS
        if name in response.headers
    }
    return StoredResponse(
        status=response.status_code,
        body=bytes(response.body).decode("utf-8"),
        headers=headers,
    )


def _replay(stored: StoredResponse) -> Response:
    headers = dict(stored.headers)
    media_type = headers.pop("content-type", None)
    headers[REPLAYED_HEADER] = "true"
    return Response(
        content=stored.body,
        status_code=stored.status,
        headers=headers,
        media_type=media_type,
    )


def _answer_for(claim: Claim) -> Response:
    """Turn a claim that isn't "proceed" into the right answer."""
    if claim.outcome is Outcome.REPLAY:
        if claim.response is None:
            raise RuntimeError("A replay claim always carries the stored response")
        return _replay(claim.response)
    if claim.outcome is Outcome.IN_FLIGHT:
        raise IdempotentRequestInFlight(
            "A request with the same Idempotency-Key is still being processed. "
            "Wait a moment and try again."
        )
    raise IdempotencyKeyReused(
        "This Idempotency-Key was used for a request with a different body. "
        "Use a new key for a new request."
    )


HEADER_DOC = {
    "name": HEADER,
    "in": "header",
    "required": False,
    "schema": {"type": "string", "minLength": 8, "maxLength": 128},
    "description": (
        "Send the same key when retrying this request and you get the "
        "original response back instead of doing the work twice, with "
        f"`{REPLAYED_HEADER}: true` on the reply. Retrying while the first "
        "attempt is still running gives 409; reusing a key with a different "
        "body gives 422. Use a new random value (a UUID is ideal) for each "
        f"distinct request. Keys are remembered for "
        f"{COMPLETED_TTL_SECONDS // 3600} hours."
    ),
}

# Documented by the route class rather than per endpoint, so no POST can be
# added later that honours the header without saying what it may answer.
UNAVAILABLE_RESPONSE = {
    "503": {
        "description": (
            "Can't guarantee this request runs only once right now. Safe to retry."
        )
    }
}


class IdempotentRoute(APIRoute):
    """Honours an Idempotency-Key header on the routes of its router."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Put the header in the API documentation for exactly the routes that
        # honour it. FastAPI concatenates list values here, so a route's own
        # path parameters are kept.
        if set(self.methods or ()) & GUARDED_METHODS:
            extra = dict(self.openapi_extra or {})
            extra["parameters"] = [*extra.get("parameters", []), HEADER_DOC]
            extra["responses"] = {**UNAVAILABLE_RESPONSE, **extra.get("responses", {})}
            self.openapi_extra = extra

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        run_endpoint = super().get_route_handler()

        async def handler(request: Request) -> Response:
            key = request.headers.get(HEADER)
            if key is None or request.method not in GUARDED_METHODS:
                return await run_endpoint(request)

            check_key(key)
            # Reading the body here is safe: Starlette caches it, so the
            # endpoint still gets to read it afterwards.
            body = await request.body()
            request_fingerprint = fingerprint(body)
            stored_key = storage_key(
                credential=_credential(request),
                method=request.method,
                path=request.url.path,
                key=key,
            )

            store = get_store()
            claim = store.claim(stored_key, request_fingerprint)
            if claim.outcome is not Outcome.PROCEED:
                return _answer_for(claim)

            try:
                response = await run_endpoint(request)
            except Exception:
                # Includes every domain error. Give the key back so the same
                # request can be sent again; the error will be the same one.
                store.release(stored_key)
                raise

            if hasattr(response, "body") and response.status_code < MAX_STORABLE_STATUS:
                store.complete(stored_key, request_fingerprint, _to_stored(response))
            else:
                store.release(stored_key)
            return response

        return handler
