"""The API document, corrected where it disagrees with what the API answers.

Each correction is applied once, for every route present and future, instead
of each route having to remember.

FastAPI adds a 422 entry by itself to every operation that takes input and
does not document one, in its own validation-error shape. Ours never sends
that shape: every error, validation included, goes out as RFC 9457 Problem
Details (app/core/errors.py, backend.md section 3). Left alone, the document
would promise the frontend a body it never receives.

Nothing documented the 400 that an unreadable body earns, though every
operation taking a body can answer it. Schemathesis found that one by
generating requests from this document and meeting a status it did not list
(docs/API_CONTRACT_FINDINGS.md).
"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from app.core.errors import PROBLEM_CONTENT_TYPE

# The body FastAPI documents for its own 422, and the schemas only it uses.
FASTAPI_VALIDATION_REF = "#/components/schemas/HTTPValidationError"
FASTAPI_ONLY_SCHEMAS = ("HTTPValidationError", "ValidationError")

VALIDATION_PROBLEM = {
    "description": "The request is not valid; `errors` names each field and why",
    "content": {
        PROBLEM_CONTENT_TYPE: {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
    },
}

# The methods an OpenAPI path item may hold. Everything else under a path
# ("parameters", "summary", "servers") describes the path, not an operation.
OPERATION_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

BAD_REQUEST_PROBLEM = {
    "description": (
        "The request itself could not be read, for example a body that is not "
        "valid UTF-8. Nothing was done"
    ),
    "content": {
        PROBLEM_CONTENT_TYPE: {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
    },
}


def _uses_fastapi_shape(response: dict[str, Any]) -> bool:
    content = response.get("content", {}).get("application/json", {})
    return bool(content.get("schema", {}).get("$ref") == FASTAPI_VALIDATION_REF)


def document_validation_errors_as_problems(spec: dict[str, Any]) -> dict[str, Any]:
    """Rewrite every 422 FastAPI documented in its own shape. Safe to repeat."""
    for item in spec.get("paths", {}).values():
        for operation in item.values():
            responses = operation.get("responses", {})
            if "422" in responses and _uses_fastapi_shape(responses["422"]):
                responses["422"] = VALIDATION_PROBLEM
    schemas = spec.get("components", {}).get("schemas", {})
    for name in FASTAPI_ONLY_SCHEMAS:
        schemas.pop(name, None)
    return spec


def document_unreadable_body(spec: dict[str, Any]) -> dict[str, Any]:
    """Document the 400 an operation with a body can always answer.

    A body that is not valid UTF-8 is refused before any field is looked at,
    so it is a 400 rather than the 422 a field error gets. Every operation
    that takes a body can answer it, and none of them documented it: a client
    generated from this document met a status it had no branch for.

    Only operations with a request body are touched, because that is where
    the answer comes from. Safe to repeat, and it never replaces a 400 a
    route documented for its own reason.
    """
    for item in spec.get("paths", {}).values():
        for method, operation in item.items():
            if method.lower() not in OPERATION_METHODS:
                continue
            if "requestBody" not in operation:
                continue
            operation.setdefault("responses", {}).setdefault("400", BAD_REQUEST_PROBLEM)
    return spec


def install(app: FastAPI) -> None:
    """Make `app.openapi()` return the corrected document."""
    generate: Callable[[], dict[str, Any]] = app.openapi

    def openapi() -> dict[str, Any]:
        return document_unreadable_body(
            document_validation_errors_as_problems(generate())
        )

    # FastAPI's documented way to customise the document is to replace this
    # method; mypy reads that as assigning to a method.
    app.openapi = openapi  # type: ignore[method-assign]
