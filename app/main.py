from http import HTTPStatus

from fastapi import FastAPI, Request
from slowapi.middleware import SlowAPIMiddleware

from app.core.errors import problem_response, register_error_handlers
from app.core.health import run_readiness_checks
from app.core.rate_limit import limiter
from app.core.request_id import RequestIdMiddleware
from app.modules.auth.profile_router import brand_router, creator_router
from app.modules.auth.router import router as auth_router
from app.modules.campaigns.application_router import router as applications_router
from app.modules.campaigns.router import router as campaigns_router
from app.modules.deal_memo.proof_router import router as proof_router
from app.modules.deal_memo.router import router as deal_memos_router
from app.modules.notifications.router import router as notifications_router

app = FastAPI(title="NicheConnect TN API")

app.state.limiter = limiter
# Every error, including 429 from the rate limiter, uses Problem Details.
register_error_handlers(app)
app.add_middleware(SlowAPIMiddleware)
# Added last so it wraps everything: every response gets X-Request-ID.
app.add_middleware(RequestIdMiddleware)

app.include_router(auth_router)
app.include_router(brand_router)
app.include_router(creator_router)
app.include_router(campaigns_router)
app.include_router(applications_router)
app.include_router(notifications_router)
app.include_router(deal_memos_router)
app.include_router(proof_router)


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
)
def readyz(request: Request):
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
