from fastapi import FastAPI
from slowapi.middleware import SlowAPIMiddleware

from app.core.errors import register_error_handlers
from app.core.rate_limit import limiter
from app.core.request_id import RequestIdMiddleware
from app.modules.auth.profile_router import brand_router, creator_router
from app.modules.auth.router import router as auth_router
from app.modules.campaigns.router import router as campaigns_router

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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check — is the process up at all."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    """Readiness check — placeholder until DB/Redis connectivity is wired in."""
    return {"status": "ready"}
