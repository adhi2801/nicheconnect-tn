import logging
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.errors import DomainError, register_error_handlers
from app.core.request_id import RequestIdMiddleware

PROBLEM_KEYS = {"type", "title", "status", "code", "request_id"}


class CampaignNotOpen(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "campaign_not_open"
    title = "Campaign is not open for applications"


class PitchIn(BaseModel):
    pitch: str = Field(min_length=20)
    phone: str = Field(pattern=r"^\+91[6-9][0-9]{9}$")


def make_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/closed")
    def closed() -> None:
        raise CampaignNotOpen("Campaign closed on 15 Sep.")

    @app.get("/plain-domain-error")
    def plain_domain_error() -> None:
        raise CampaignNotOpen()

    @app.post("/pitch")
    def pitch(body: PitchIn) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("SELECT * FROM account WHERE phone = '+919876543210'")

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return make_client()


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body.keys() >= PROBLEM_KEYS
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == "https://nicheconnect.in/errors/" + code.replace("_", "-")
    assert body["request_id"] == response.headers["x-request-id"]
    return body


def test_domain_error_uses_its_status_code_title_and_detail(client):
    body = assert_problem(client.get("/closed"), 409, "campaign_not_open")
    assert body["title"] == "Campaign is not open for applications"
    assert body["detail"] == "Campaign closed on 15 Sep."


def test_domain_error_without_detail_omits_detail(client):
    body = assert_problem(client.get("/plain-domain-error"), 409, "campaign_not_open")
    assert "detail" not in body


def test_validation_error_lists_each_field(client):
    response = client.post("/pitch", json={"pitch": "short", "phone": "12345"})

    body = assert_problem(response, 422, "validation_failed")
    fields = {error["field"] for error in body["errors"]}
    assert fields == {"pitch", "phone"}
    assert all(error["message"] for error in body["errors"])


def test_validation_error_does_not_echo_submitted_values(client):
    submitted_phone = "+91555555555"
    response = client.post("/pitch", json={"pitch": "short", "phone": submitted_phone})

    assert response.status_code == 422
    assert submitted_phone not in response.text
    assert "short" not in response.text


def test_missing_body_is_a_validation_error(client):
    assert_problem(client.post("/pitch"), 422, "validation_failed")


def test_unknown_route_is_not_found(client):
    body = assert_problem(client.get("/does-not-exist"), 404, "not_found")
    assert body["title"] == "Not Found"


def test_wrong_method_is_method_not_allowed(client):
    response = client.put("/closed")

    assert_problem(response, 405, "method_not_allowed")
    assert "GET" in response.headers["allow"]


def test_unexpected_error_hides_details_from_the_user(client):
    response = client.get("/crash")

    body = assert_problem(response, 500, "internal_error")
    assert "SELECT" not in response.text
    assert "+919876543210" not in response.text
    assert "detail" not in body


def test_unexpected_error_is_logged_with_request_id(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        response = client.get("/crash", headers={"X-Request-ID": "trace-500"})

    assert response.json()["request_id"] == "trace-500"
    assert any("trace-500" in record.getMessage() for record in caplog.records)
