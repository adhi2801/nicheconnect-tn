from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware

from app.core.body_limit import BodyLimitMiddleware
from app.core.errors import problem_response, register_error_handlers
from app.core.health import run_readiness_checks
from app.core.idempotent_route import set_identity_resolver
from app.core.rate_limit import limiter
from app.core.request_id import RequestIdMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
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
from app.modules.notifications.router import router as notifications_router
from app.modules.payment_status.brand_router import router as reliability_router
from app.modules.payment_status.bulk_router import router as bulk_payments_router
from app.modules.payment_status.router import router as payment_router

app = FastAPI(title="NicheConnect TN API")

app.state.limiter = limiter
# Retries are grouped by the account that sent them, so a refreshed token
# does not turn a retry into a second request.
set_identity_resolver(idempotency_identity)
# Every error, including 429 from the rate limiter, uses Problem Details.
register_error_handlers(app)
# Added before the rate limiter, which puts it *inside* it: an oversized
# request is still counted against the sender's limit, so a flood of them
# earns a 429 rather than an endless stream of cheap 413s.
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(SlowAPIMiddleware)
# Every response gets X-Request-ID.
app.add_middleware(RequestIdMiddleware)
# Added last so it wraps everything, including the 413 and 429 that the
# middlewares above generate on their own.
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(brand_router)
app.include_router(creator_router)
# Privacy: download everything we hold about you.
app.include_router(export_router)
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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check — is the process up at all."""
    return {"status": "ok"}


@app.get(
    "/readyz",
    summary="Readiness check",
    description=(
        "Reports whether the database and Redis are reachable. Returns 503 "
        "while either is down, so a deployment platform stops sending traffic."
    ),
    response_model=None,
)
def readyz(request: Request) -> JSONResponse | dict[str, object]:
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
    return {"status": "ready", "checks": results}
