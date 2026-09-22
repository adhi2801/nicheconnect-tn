"""One error shape for every non-2xx response: RFC 9457 Problem Details.

Services raise DomainError subclasses; the handlers here turn every error
into the same JSON body (docs/standards/backend.md section 3). Routers never
build error JSON by hand.
"""

import logging
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


async def handle_http_error(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # Framework errors such as unknown routes (404) or wrong method (405).
    return problem_response(
        request,
        status=exc.status_code,
        code=_code_for_status(exc.status_code),
        title=HTTPStatus(exc.status_code).phrase,
        headers=dict(exc.headers or {}),
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
