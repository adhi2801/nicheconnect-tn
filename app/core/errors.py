"""One error shape for every non-2xx response: RFC 9457 Problem Details.

Services raise DomainError subclasses; the handlers here turn every error
into the same JSON body (docs/standards/backend.md section 3). Routers never
build error JSON by hand.
"""

import logging
from collections.abc import Iterable, Iterator
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

ERROR_TYPE_BASE = "https://nicheconnect.in/errors/"
PROBLEM_CONTENT_TYPE = "application/problem+json"
REQUEST_ID_HEADER = "X-Request-ID"


class DomainError(Exception):
    """Base class for business-rule errors raised by services.

    Subclasses set status_code, code (stable, machine-readable) and title
    (safe to show to users). detail adds a user-safe explanation.
    """

    status_code: int = HTTPStatus.BAD_REQUEST
    code: str = "domain_error"
    title: str = "The request could not be completed"

    def __init__(
        self, detail: str | None = None, *, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        # Extra response headers, e.g. Retry-After on a 429.
        self.headers = dict(headers or {})


class FieldError(BaseModel):
    field: str
    message: str


class ProblemDetails(BaseModel):
    """The error body every non-2xx response uses (for the API docs)."""

    type: str
    title: str
    status: int
    code: str
    request_id: str | None
    detail: str | None = None
    errors: list[FieldError] | None = None


# The shape FastAPI takes for a route's `responses=`. Written once so every
# router's shared error table has the type FastAPI expects.
ResponseDocs = dict[int | str, dict[str, Any]]


def problem_doc(description: str) -> dict[str, Any]:
    """An OpenAPI `responses` entry for an error status."""
    return {
        "model": ProblemDetails,
        "description": description,
        "content": {PROBLEM_CONTENT_TYPE: {}},
    }


def _code_for_status(status: int) -> str:
    """Stable code for plain HTTP errors, e.g. 404 -> 'not_found'."""
    return HTTPStatus(status).phrase.lower().replace(" ", "_").replace("-", "_")


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a Problem Details response carrying the request ID."""
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, Any] = {
        "type": ERROR_TYPE_BASE + code.replace("_", "-"),
        "title": title,
        "status": status,
        "code": code,
        "request_id": request_id,
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors

    response_headers = dict(headers or {})
    # Set here too: on a 500 the request-ID middleware never sees a response.
    if request_id:
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        body,
        status_code=status,
        headers=response_headers,
        media_type=PROBLEM_CONTENT_TYPE,
    )


def _field_name(location: tuple[Any, ...]) -> str:
    """'body.pitch' -> 'pitch'; keeps 'query.limit' style for non-body input."""
    parts = [str(part) for part in location]
    if parts and parts[0] == "body":
        parts = parts[1:]
    return ".".join(parts) or "request"


async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return problem_response(
        request,
        status=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        headers=exc.headers,
    )


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Messages only; submitted values are never echoed back (they may be PII).
    errors = [
        {"field": _field_name(tuple(error["loc"])), "message": error["msg"]}
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="validation_failed",
        title="Some fields are missing or invalid",
        errors=errors,
    )


def handle_rate_limit(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Must stay a plain (non-async) function: SlowAPIMiddleware silently falls
    # back to its own non-standard body when this handler is async.
    # The full window length is a safe upper bound for when to retry.
    retry_after = exc.limit.limit.get_expiry() if exc.limit else 60
    return problem_response(
        request,
        status=HTTPStatus.TOO_MANY_REQUESTS,
        code="rate_limited",
        title="Too many requests. Please wait and try again",
        headers={"Retry-After": str(retry_after)},
    )


def _leaf_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Every endpoint route, flattened out of whatever is nesting it.

    `app.routes` is not a flat list: FastAPI wraps each `include_router` in a
    router object, and Starlette nests a `Mount`'s routes inside it. Both are
    unwrapped here, so a caller sees only the routes that actually answer.
    """
    for route in routes:
        nested = getattr(route, "routes", None)
        if nested is None:
            original = getattr(route, "original_router", None)
            nested = getattr(original, "routes", None)
        if nested:
            yield from _leaf_routes(nested)
        else:
            yield route


def _methods_this_resource_supports(request: Request) -> str | None:
    """Every method allowed on this path, for the `Allow` header on a 405.

    Starlette raises the 405 from the first route whose path matched and
    fills `Allow` with that one route's methods. FastAPI registers a route
    per method, so `OPTIONS /api/v1/brands/me` answered saying only POST was
    allowed, when GET and PATCH are too. RFC 9110 wants every method the
    resource supports, and a client reading a short list concludes the
    others do not exist.

    Matched on `path_regex` rather than `route.matches(scope)`: the latter
    stops at the wrapper, which never compares the path of the routes inside.

    Only the routes sharing the FIRST matching path template count. A static
    path also matches its parameterised sibling's pattern —
    `/api/v1/campaigns/discover` matches `/api/v1/campaigns/{campaign_id}` —
    but routing takes the first match in registration order, so the static
    one answers and the sibling's PATCH is not on offer here. Taking every
    pattern that matched advertised methods this path does not serve.
    """
    routes = list(_leaf_routes(request.app.routes))
    path = request.url.path

    template: str | None = None
    for route in routes:
        pattern = getattr(route, "path_regex", None)
        if pattern is not None and pattern.match(path):
            template = getattr(route, "path", None)
            break
    if template is None:
        return None

    methods: set[str] = set()
    for route in routes:
        if getattr(route, "path", None) == template:
            methods |= getattr(route, "methods", None) or set()
    return ", ".join(sorted(methods)) if methods else None


async def handle_http_error(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # Framework errors such as unknown routes (404) or wrong method (405).
    headers = dict(exc.headers or {})
    if exc.status_code == HTTPStatus.METHOD_NOT_ALLOWED:
        allowed = _methods_this_resource_supports(request)
        if allowed:
            headers["Allow"] = allowed
    return problem_response(
        request,
        status=exc.status_code,
        code=_code_for_status(exc.status_code),
        title=HTTPStatus(exc.status_code).phrase,
        headers=headers,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Full details go to the log only; the user gets a generic message.
    logger.exception(
        "request.unhandled_error request_id=%s",
        getattr(request.state, "request_id", None),
    )
    return problem_response(
        request,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="internal_error",
        title="Something went wrong on our side. Please try again",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach every handler above to the app."""
    # Starlette types every handler as taking a bare Exception. Each of ours
    # takes the class it is registered for, which Starlette guarantees at
    # runtime by dispatching on that class; mypy cannot see the link.
    app.add_exception_handler(DomainError, handle_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        handle_validation_error,  # type: ignore[arg-type]
    )
    app.add_exception_handler(RateLimitExceeded, handle_rate_limit)  # type: ignore[arg-type]
    app.add_exception_handler(
        StarletteHTTPException,
        handle_http_error,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, handle_unexpected_error)
