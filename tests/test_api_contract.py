"""The API contract, checked as a whole rather than one endpoint at a time.

Per-endpoint tests prove what each endpoint does. These prove that nothing
was left out anywhere: an endpoint reachable without a login by accident,
an error the documentation never mentions, a change to the contract nobody
noticed. Each walks the whole OpenAPI document, so a new endpoint is
checked the moment it exists, without anyone remembering to add a test.
"""

import re
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.main import app
from tests import openapi_snapshot

# Every operation needs a login except these, each for a stated reason.
PUBLIC = {
    ("GET", "/healthz"): "a deployment platform's liveness probe",
    ("GET", "/readyz"): "a deployment platform's readiness probe",
    ("POST", "/api/v1/auth/otp/request"): "how a login starts",
    ("POST", "/api/v1/auth/otp/verify"): "how a login finishes",
    (
        "POST",
        "/api/v1/auth/refresh",
    ): "the access token has expired; the refresh token in the body is the credential",
    (
        "POST",
        "/api/v1/auth/logout",
    ): "the refresh token in the body is the credential; always 204",
    ("GET", "/api/v1/creators/by-handle/{handle}"): "the public Creator Passport (D-036)",
}

PROBLEM_TYPE = "application/problem+json"
WRITE_METHODS = {"post", "patch", "put", "delete"}


def operations() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (method.upper(), path, operation)
        for path, item in openapi_snapshot.current()["paths"].items()
        for method, operation in item.items()
    ]


def label(method: str, path: str) -> str:
    return f"{method} {path}"


# --- who can call what --------------------------------------------------------------


def test_the_public_list_names_only_real_operations():
    real = {(method, path) for method, path, _ in operations()}

    assert set(PUBLIC) <= real, set(PUBLIC) - real


def test_every_other_operation_refuses_a_request_without_a_token():
    """Called for real, without a token: the answer must be 401 before anything
    else happens. A placeholder id stands in for every path parameter."""
    client = TestClient(app)
    limiter.enabled = False
    try:
        reachable = []
        for method, path, _ in operations():
            if (method, path) in PUBLIC:
                continue
            url = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)
            body = {} if method.lower() in WRITE_METHODS else None
            response = client.request(method, url, json=body)
            if response.status_code != 401:
                reachable.append(f"{label(method, path)} -> {response.status_code}")
    finally:
        limiter.enabled = True

    assert reachable == [], "Reachable without a login: " + "; ".join(reachable)


# --- what the documentation promises ------------------------------------------------


def test_every_operation_is_described_with_a_summary_and_a_description():
    missing = [
        label(method, path)
        for method, path, op in operations()
        if not op.get("summary") or not op.get("description")
    ]

    assert missing == [], missing


def test_every_successful_answer_has_a_documented_shape():
    missing = []
    for method, path, op in operations():
        success = {code: r for code, r in op["responses"].items() if code.startswith("2")}
        described = all(
            code == "204"
            or r.get("content", {}).get("application/json", {}).get("schema")
            for code, r in success.items()
        )
        if not success or not described:
            missing.append(label(method, path))

    assert missing == [], missing


def test_every_operation_documents_its_rate_limit():
    missing = [
        label(method, path)
        for method, path, op in operations()
        if "429" not in op["responses"]
    ]

    assert missing == [], missing


def test_every_operation_behind_a_login_documents_401():
    missing = [
        label(method, path)
        for method, path, op in operations()
        if (method, path) not in PUBLIC and "401" not in op["responses"]
    ]

    assert missing == [], missing


def test_every_operation_that_takes_input_documents_422():
    missing = [
        label(method, path)
        for method, path, op in operations()
        if (op.get("parameters") or op.get("requestBody"))
        and "422" not in op["responses"]
    ]

    assert missing == [], missing


def test_every_operation_that_takes_a_body_documents_400():
    """A body that is not valid UTF-8 is refused before any field is read."""
    missing = [
        label(method, path)
        for method, path, op in operations()
        if op.get("requestBody") and "400" not in op["responses"]
    ]

    assert missing == [], missing


def test_an_unreadable_body_really_answers_400():
    """The document above is only worth anything if this is what happens."""
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/otp/request",
            content=b'\x1c\x8f\x9dd\xc2"\x9ais9',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith(PROBLEM_TYPE)
    assert response.json()["code"] == "bad_request"


def test_a_readable_body_that_is_not_json_still_answers_422():
    """400 is for bytes we cannot read, not for a body we can read and reject."""
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/otp/request",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def test_every_documented_error_uses_the_one_error_format():
    """backend.md section 3: one error shape everywhere, RFC 9457 Problem Details."""
    wrong = [
        f"{label(method, path)} {code}"
        for method, path, op in operations()
        for code, response in op["responses"].items()
        if int(code) >= 400 and PROBLEM_TYPE not in response.get("content", {})
    ]

    assert wrong == [], wrong


# --- the contract itself ------------------------------------------------------------------


def test_the_contract_matches_the_committed_copy():
    committed, current = openapi_snapshot.committed(), openapi_snapshot.current()
    if committed == current:
        return

    changed = sorted(
        path
        for path in set(committed["paths"]) | set(current["paths"])
        if committed["paths"].get(path) != current["paths"].get(path)
    )
    schemas = sorted(
        name
        for name in set(committed["components"]["schemas"])
        | set(current["components"]["schemas"])
        if committed["components"]["schemas"].get(name)
        != current["components"]["schemas"].get(name)
    )
    pytest.fail(
        "The API contract changed. If that is intended, refresh the committed copy "
        "and commit it with the change: venv\\Scripts\\python.exe -m "
        f"tests.openapi_snapshot\nPaths: {changed}\nSchemas: {schemas}"
    )
