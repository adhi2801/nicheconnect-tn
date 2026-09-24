from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware

from app.core import cors, openapi
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import settings
from app.core.errors import problem_doc, problem_response, register_error_handlers
from app.core.health import HealthRead, ReadinessRead, run_readiness_checks
from app.core.idempotent_route import set_identity_resolver
from app.core.rate_limit import limiter
from app.core.request_id import RequestIdMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.unexpected_error import UnexpectedErrorMiddleware
from app.modules.auth.attention_router import router as attention_router
from app.modules.auth.dependencies import idempotency_identity
from app.modules.auth.export_router import router as export_router
from app.modules.auth.profile_router import brand_router, creator_router
from app.modules.auth.public_router import router as public_router
from app.modules.auth.router import router as auth_router
from app.modules.campaigns.application_router import router as applications_router
from app.modules.campaigns.router import router as campaigns_router
from app.modules.deal_memo.delivery_router import router as delivery_router
from app.modules.deal_memo.proof_router import router as proof_router
from app.modules.deal_memo.router import router as deal_memos_router
from app.modules.disputes.router import router as disputes_router
from app.modules.matching.router import router as matching_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payment_status.brand_router import router as reliability_router
from app.modules.payment_status.bulk_router import router as bulk_payments_router
from app.modules.payment_status.router import router as payment_router

# The API describes itself at /docs, /redoc and /openapi.json everywhere but
# production (D-044). The frontend builds from the committed copy in
# docs/api/openapi.json and from staging; in production the pages would only
# hand strangers a map of every endpoint.
API_DOCS_PUBLIC = settings.environment != "production"

app = FastAPI(
    title="NicheConnect TN API",
    openapi_url="/openapi.json" if API_DOCS_PUBLIC else None,
    docs_url="/docs" if API_DOCS_PUBLIC else None,
    redoc_url="/redoc" if API_DOCS_PUBLIC else None,
)
# Every error in the API document in our one format, validation included.
openapi.install(app)

app.state.limiter = limiter
# Retries are grouped by the account that sent them, so a refreshed token
# does not turn a retry into a second request.
set_identity_resolver(idempotency_identity)
# Every error, including 429 from the rate limiter, uses Problem Details.
register_error_handlers(app)
# Middleware wraps in reverse order of adding: the last one added sees each
# request first and each response last. tests/test_main.py pins the order.
#
# Added before the rate limiter, which puts it *inside* it: an oversized
# request is still counted against the sender's limit, so a flood of them
# earns a 429 rather than an endless stream of cheap 413s.
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(SlowAPIMiddleware)
# Outside the rate limiter and the body limit, so a crash in either (Redis
# down, say) still becomes our usual 500, not a bare one (D-045).
app.add_middleware(UnexpectedErrorMiddleware)
# Which websites may call us from a browser (D-044). Outside everything that
# can refuse or fail, so a 413, 429 or 500 still reaches the dashboard in a
# form it can read. A browser's preflight is answered here, before the rate
# limiter; slowapi already let every OPTIONS request through unlimited.
cors.install(app)
# Every response gets X-Request-ID.
app.add_middleware(RequestIdMiddleware)
# Added last so it wraps everything, including the 413, 429 and 500 that the
# middlewares above generate on their own.
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(brand_router)
app.include_router(creator_router)
# Privacy: download everything we hold about you.
app.include_router(export_router)
app.include_router(attention_router)
# Public: the Creator Passport, readable without logging in.
app.include_router(public_router)
app.include_router(campaigns_router)
app.include_router(applications_router)
app.include_router(notifications_router)
app.include_router(deal_memos_router)
app.include_router(proof_router)
app.include_router(payment_router)
app.include_router(bulk_payments_router)
app.include_router(reliability_router)
app.include_router(delivery_router)
app.include_router(disputes_router)
app.include_router(matching_router)


@app.get(
    "/healthz",
    response_model=HealthRead,
    summary="Liveness check",
    description=(
        "Answers as long as the process is running, without touching the "
        "database or Redis. For a deployment platform deciding whether to "
        "restart it."
    ),
    responses={429: problem_doc("Too many requests; see the Retry-After header")},
)
def healthz() -> HealthRead:
    """Liveness check — is the process up at all."""
    return HealthRead(status="ok")


@app.get(
    "/readyz",
    summary="Readiness check",
    description=(
        "Reports whether the database and Redis are reachable. Returns 503 "
        "while either is down, so a deployment platform stops sending traffic."
    ),
    # Explicit, because the 503 is returned as a response object rather than
    # this model, and FastAPI would otherwise read the union as the model.
    response_model=ReadinessRead,
    responses={
        429: problem_doc("Too many requests; see the Retry-After header"),
        503: problem_doc("The database or Redis cannot be reached"),
    },
)
def readyz(request: Request) -> JSONResponse | ReadinessRead:
    """Readiness check — can this process actually serve requests?"""
    checks = run_readiness_checks()
    results = {check.name: "ok" if check.ok else "unavailable" for check in checks}
    failed = [check.name for check in checks if not check.ok]
    if failed:
        return problem_response(
            request,
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            code="not_ready",
            title="The service is not ready to take requests",
            detail=f"Unavailable: {', '.join(sorted(failed))}.",
        )
    return ReadinessRead(status="ready", checks=results)
