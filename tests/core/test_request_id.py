import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.errors import register_error_handlers
from app.core.request_id import RequestIdMiddleware, request_id_var, resolve_request_id


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/echo")
    def echo(request: Request) -> dict[str, str | None]:
        return {"state": request.state.request_id, "context": request_id_var.get()}

    return TestClient(app)


def test_generated_id_is_returned_and_visible_inside_the_request(client):
    response = client.get("/echo")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    assert response.json() == {"state": request_id, "context": request_id}


def test_each_request_gets_a_different_id(client):
    first = client.get("/echo").headers["x-request-id"]
    second = client.get("/echo").headers["x-request-id"]

    assert first != second


def test_safe_incoming_id_is_reused(client):
    response = client.get("/echo", headers={"X-Request-ID": "web-2026.09_17-abc"})

    assert response.headers["x-request-id"] == "web-2026.09_17-abc"
    assert response.json()["state"] == "web-2026.09_17-abc"


@pytest.mark.parametrize(
    "incoming",
    ["has space", "semi;colon", "a" * 65, "", "line\\nbreak"],
)
def test_unsafe_incoming_id_is_replaced(incoming):
    resolved = resolve_request_id(incoming)

    assert resolved != incoming
    assert len(resolved) == 32


def test_unsafe_header_is_replaced_end_to_end(client):
    response = client.get("/echo", headers={"X-Request-ID": "bad id <script>"})

    assert response.headers["x-request-id"] != "bad id <script>"
    assert len(response.headers["x-request-id"]) == 32


def test_id_is_on_error_responses(client):
    response = client.get("/missing", headers={"X-Request-ID": "trace-404"})

    assert response.status_code == 404
    assert response.headers["x-request-id"] == "trace-404"
    assert response.json()["request_id"] == "trace-404"


def test_context_is_cleared_after_the_request(client):
    client.get("/echo")

    assert request_id_var.get() is None
