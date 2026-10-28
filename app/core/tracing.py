"""Tracing: which endpoint is slow in production, and where the time went (item 3, D-094).

Every request becomes a trace: one span for the request, with one child span
per database query, so a slow p95 shows whether the time went in our code or
in Postgres. OpenTelemetry is the standard (D-047); the spans go over OTLP to
`TRACES_ENDPOINT`, and nothing is traced while it is unset.

Built on OpenTelemetry's stable API and SDK only. The ready-made FastAPI and
SQLAlchemy instrumentation is still beta (0.66b1 in October 2026), which
D-047's rule refuses, and owning these few lines also decides exactly what a
span may say.

What a span says, and never more (security.md, constraint 2):

- a request: its method, the route **template** (`/api/v1/campaigns/{campaign_id}`,
  never the real path, which can carry a handle), the status code, our
  request ID, and the error's type when it failed;
- a query: the operation and the SQL with its placeholders. Our queries bind
  every value (database.md section 7), so a phone number or a payment
  reference is never in the text;
- never a query string, a header, a body, an account, an IP address or an
  exception's message, which can quote what someone typed.

A request from the apps that carries a W3C `traceparent` continues that
trace, so one tap can be followed from the phone into the database. Spans
are sent by a background thread in batches; a request never waits on it, and
an unreachable destination costs dropped spans, never a slower answer.
"""

import logging
from collections.abc import Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.load_shedding import EXEMPT_PATHS

logger = logging.getLogger(__name__)

SERVICE_NAME = "nicheconnect-api"
# Long enough for any query we write; a cap so a span stays small.
MAX_QUERY_TEXT = 2000
# Seconds the exporter may spend on one batch before it gives up on it.
EXPORT_TIMEOUT_SECONDS = 3
# Health probes arrive every few seconds from the load balancer and the
# container runtime; traced, they would bury real requests and cost money.
UNTRACED_PATHS = EXEMPT_PATHS
_PROPAGATOR = TraceContextTextMapPropagator()
_SPAN_KEY = "_tracing_span"


def init_tracing(settings: Settings) -> TracerProvider | None:
    """Start sending spans, or do nothing while TRACES_ENDPOINT is unset.

    Returns the provider so the caller can wire the middleware and the
    database to it. Its batches are flushed when the process exits.
    """
    if not settings.traces_endpoint:
        return None
    # Imported here: the exporter pulls in protobuf, which a process with
    # tracing off has no reason to load.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": SERVICE_NAME,
                "service.version": settings.app_release or "unknown",
                "deployment.environment.name": settings.environment,
            }
        ),
        sampler=ParentBased(TraceIdRatioBased(settings.traces_sample_ratio)),
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.traces_endpoint, timeout=EXPORT_TIMEOUT_SECONDS
            )
        )
    )
    trace.set_tracer_provider(provider)
    logger.info("tracing.started sample_ratio=%s", settings.traces_sample_ratio)
    return provider


class TracingMiddleware:
    """Pure ASGI middleware: one SERVER span per request. Outermost in app/main.py."""

    def __init__(
        self, app: ASGIApp, *, tracer_provider: TracerProvider | None = None
    ) -> None:
        self.app = app
        self.tracer = trace.get_tracer(__name__, tracer_provider=tracer_provider)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in UNTRACED_PATHS:
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        parent = _PROPAGATOR.extract(
            {
                name.decode("latin-1"): value.decode("latin-1")
                for name, value in scope["headers"]
            }
        )
        # Exceptions are recorded by hand, by type only: the default would
        # copy the exception's message into the span.
        with self.tracer.start_as_current_span(
            method,
            context=parent,
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": method,
                "url.scheme": scope.get("scheme", "http"),
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            status: int | None = None

            async def send_noting_status(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                    span.set_attribute("http.response.status_code", status)
                await send(message)

            try:
                await self.app(scope, receive, send_noting_status)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR))
                span.set_attribute("error.type", type(exc).__qualname__)
                raise
            finally:
                _name_after_route(span, scope, method)
                if status is not None and status >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                    span.set_attribute("error.type", str(status))


def _name_after_route(span: Any, scope: Scope, method: str) -> None:
    """The route's template names the span; an unmatched path stays nameless,
    so a stranger probing random paths cannot flood us with span names."""
    template = getattr(scope.get("route"), "path", None)
    if template:
        span.update_name(f"{method} {template}")
        span.set_attribute("http.route", template)
    request_id = scope.get("state", {}).get("request_id")
    if request_id:
        span.set_attribute("app.request_id", request_id)


def instrument_engine(
    engine: Engine, tracer_provider: TracerProvider | None = None
) -> Callable[[], None]:
    """A CLIENT span for every query run inside a traced request.

    Queries outside one (a background job, a script) are left alone: a span
    with no request around it would be a trace of one query, which says
    nothing and costs a trace. Returns a function that removes the hooks.
    """
    tracer = trace.get_tracer(__name__, tracer_provider=tracer_provider)

    @event.listens_for(engine, "before_cursor_execute")
    def _start(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        if context is None or not trace.get_current_span().is_recording():
            return
        operation = (
            statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "SQL"
        )
        context.__dict__[_SPAN_KEY] = tracer.start_span(
            operation,
            kind=SpanKind.CLIENT,
            attributes={
                "db.system.name": "postgresql",
                "db.operation.name": operation,
                "db.query.text": statement[:MAX_QUERY_TEXT],
            },
        )

    @event.listens_for(engine, "after_cursor_execute")
    def _end(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        span = context.__dict__.pop(_SPAN_KEY, None) if context is not None else None
        if span is not None:
            span.end()

    @event.listens_for(engine, "handle_error")
    def _failed(exception_context: Any) -> None:
        context = exception_context.execution_context
        span = context.__dict__.pop(_SPAN_KEY, None) if context is not None else None
        if span is not None:
            span.set_status(Status(StatusCode.ERROR))
            # The type only: a database error's message can quote the row.
            span.set_attribute(
                "error.type", type(exception_context.original_exception).__qualname__
            )
            span.end()

    hooks = (
        ("before_cursor_execute", _start),
        ("after_cursor_execute", _end),
        ("handle_error", _failed),
    )

    def remove() -> None:
        for name, hook in hooks:
            event.remove(engine, name, hook)

    return remove
