"""Tracing says which endpoint and which query took the time, and nothing more (D-094).

Spans are read exactly as they would be sent, from an in-memory exporter, the
way the error-tracking tests read exactly what Sentry would get (D-074).
"""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import ValidationError
from sqlalchemy import text

from app.core import tracing
from app.core.tracing import TracingMiddleware, init_tracing, instrument_engine
from app.db.session import engine, get_db
from app.main import app
from tests.core.test_config import load
from tests.test_main import run_real_app

SECRET_HANDLE = "priya.secret9876543210"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN_ID = "00f067aa0ba902b7"


def provider(ratio: float = 1.0) -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    found = TracerProvider(sampler=ParentBased(TraceIdRatioBased(ratio)))
    found.add_span_processor(SimpleSpanProcessor(exporter))
    return found, exporter


@pytest.fixture
def traced(db) -> Iterator[tuple[TestClient, InMemorySpanExporter]]:
    """The real app, traced into memory, on the rolled-back test session."""
    found, exporter = provider()
    remove = instrument_engine(engine, found)
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(TracingMiddleware(app, tracer_provider=found)), exporter
    finally:
        app.dependency_overrides.clear()
        remove()


def everything_said(exporter: InMemorySpanExporter) -> str:
    """Every name and attribute of every span, as one string to search."""
    return json.dumps(
        [
            {"name": s.name, **dict(s.attributes or {})}
            for s in exporter.get_finished_spans()
        ]
    )


def server_span(exporter: InMemorySpanExporter):
    (span,) = [s for s in exporter.get_finished_spans() if s.kind == SpanKind.SERVER]
    return span


def test_a_request_is_one_span_named_by_its_route_template(traced):
    client, exporter = traced

    response = client.get(f"/api/v1/creators/by-handle/{SECRET_HANDLE}")

    span = server_span(exporter)
    assert span.name == "GET /api/v1/creators/by-handle/{handle}"
    assert span.attributes["http.route"] == "/api/v1/creators/by-handle/{handle}"
    assert span.attributes["http.request.method"] == "GET"
    assert span.attributes["http.response.status_code"] == response.status_code
    assert span.attributes["app.request_id"] == response.headers["x-request-id"]


def test_each_query_is_a_child_span_with_placeholders_never_values(traced):
    client, exporter = traced

    client.get(f"/api/v1/creators/by-handle/{SECRET_HANDLE}?ref=9876543210")

    parent = server_span(exporter)
    queries = [s for s in exporter.get_finished_spans() if s.kind == SpanKind.CLIENT]
    assert queries, "the lookup ran no traced query"
    assert {q.parent.span_id for q in queries} == {parent.context.span_id}
    assert all(q.attributes["db.system.name"] == "postgresql" for q in queries)
    assert any(q.attributes["db.operation.name"] == "SELECT" for q in queries)
    # Neither the handle in the path nor the number in the query string
    # reaches any span, whether as a name, a route or a query.
    said = everything_said(exporter)
    assert SECRET_HANDLE not in said
    assert "9876543210" not in said


def test_a_trace_started_by_the_app_is_continued(traced):
    client, exporter = traced

    client.get(
        "/api/v1/cities",
        headers={"traceparent": f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"},
    )

    span = server_span(exporter)
    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert format(span.parent.span_id, "016x") == PARENT_SPAN_ID


def test_a_failure_is_marked_by_its_type_never_its_message(traced, db):
    client, exporter = traced

    def broken():
        raise RuntimeError(f"row for {SECRET_HANDLE} refused")

    app.dependency_overrides[get_db] = broken
    response = client.get("/api/v1/campaigns/discover")

    span = server_span(exporter)
    assert response.status_code == 500
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "500"
    assert SECRET_HANDLE not in everything_said(exporter)


def test_an_unknown_path_leaves_the_span_unnamed(traced):
    client, exporter = traced

    client.get(f"/no/such/{SECRET_HANDLE}")

    span = server_span(exporter)
    assert span.name == "GET"
    assert "http.route" not in span.attributes
    assert SECRET_HANDLE not in everything_said(exporter)


def test_a_query_outside_any_request_is_not_traced(db):
    found, exporter = provider()
    remove = instrument_engine(engine, found)
    try:
        db.execute(text("SELECT 1"))
    finally:
        remove()

    assert exporter.get_finished_spans() == ()


def test_at_a_ratio_of_nothing_no_request_is_traced_unless_the_app_asked(db):
    found, exporter = provider(ratio=0.0)
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(TracingMiddleware(app, tracer_provider=found))
        client.get("/api/v1/cities")
        assert exporter.get_finished_spans() == ()

        client.get(
            "/api/v1/cities",
            headers={"traceparent": f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"},
        )
    finally:
        app.dependency_overrides.clear()

    assert len(exporter.get_finished_spans()) == 1


def test_removing_the_hooks_stops_query_spans(traced):
    client, _ = traced
    found, other = provider()
    remove = instrument_engine(engine, found)
    remove()

    client.get("/api/v1/cities")

    assert other.get_finished_spans() == ()


# --- switching it on ---------------------------------------------------------------------


def test_with_no_endpoint_nothing_is_started(monkeypatch):
    started = []
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", started.append)

    assert init_tracing(load()) is None
    assert started == []


def test_with_an_endpoint_spans_are_sent_there_in_batches(monkeypatch):
    started = []
    monkeypatch.setattr(tracing.trace, "set_tracer_provider", started.append)

    found = init_tracing(
        load(
            traces_endpoint="https://traces.example.in/v1/traces",
            traces_sample_ratio=0.25,
        )
    )

    assert found is not None and started == [found]
    assert found.resource.attributes["service.name"] == "nicheconnect-api"
    assert "0.25" in found.sampler.get_description()
    found.shutdown()


def test_an_empty_endpoint_means_off():
    assert load(traces_endpoint="").traces_endpoint is None


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_spans_leave_encrypted_outside_a_laptop(environment):
    with pytest.raises(ValidationError, match="https"):
        load(environment=environment, traces_endpoint="http://collector:4318/v1/traces")


def test_on_a_laptop_plain_http_to_a_local_collector_is_allowed():
    found = load(environment="local", traces_endpoint="http://localhost:4318/v1/traces")

    assert found.traces_endpoint == "http://localhost:4318/v1/traces"


def test_switched_on_it_wraps_everything_else():
    """Outermost, so a 503 or a 500 from any layer is inside a span."""
    layers = run_real_app(
        """
        import json
        from app.main import app
        print(json.dumps([m.cls.__name__ for m in app.user_middleware]))
        """,
        TRACES_ENDPOINT="http://localhost:4318/v1/traces",
        ENVIRONMENT="local",
    )

    assert layers[0] == "TracingMiddleware"


def test_an_exception_that_escapes_is_recorded_by_type_with_no_message():
    """If anything fails outside our own error layer, the span still keeps
    only the error's type: the default would copy its message, and with it
    whatever the message quotes."""
    found, exporter = provider()

    async def failing(scope, receive, send):
        raise RuntimeError(f"could not save {SECRET_HANDLE}")

    middleware = TracingMiddleware(failing, tracer_provider=found)
    with pytest.raises(RuntimeError):
        TestClient(middleware).get("/anything")

    (span,) = exporter.get_finished_spans()
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"
    assert span.events == ()  # no recorded exception, so no message
    assert SECRET_HANDLE not in everything_said(exporter)


@pytest.mark.parametrize("path", ["/healthz", "/readyz"])
def test_health_probes_are_not_traced(traced, path):
    client, exporter = traced

    client.get(path)

    assert exporter.get_finished_spans() == ()
