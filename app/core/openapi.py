"""The API document, corrected where FastAPI's defaults disagree with our API.

FastAPI adds a 422 entry by itself to every operation that takes input and
does not document one, in its own validation-error shape. Ours never sends
that shape: every error, validation included, goes out as RFC 9457 Problem
Details (app/core/errors.py, backend.md section 3). Left alone, the document
would promise the frontend a body it never receives. So every such entry is
rewritten here, once, for every route present and future, instead of each
route having to remember.
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


def install(app: FastAPI) -> None:
    """Make `app.openapi()` return the corrected document."""
    generate: Callable[[], dict[str, Any]] = app.openapi

    def openapi() -> dict[str, Any]:
        return document_validation_errors_as_problems(generate())

    # FastAPI's documented way to customise the document is to replace this
    # method; mypy reads that as assigning to a method.
    app.openapi = openapi  # type: ignore[method-assign]
