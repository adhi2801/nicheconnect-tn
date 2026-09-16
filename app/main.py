from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler  # NEW
from slowapi.errors import RateLimitExceeded  # NEW
from slowapi.middleware import SlowAPIMiddleware  # NEW

from app.core.rate_limit import limiter  # NEW

app = FastAPI(title="NicheConnect TN API")

app.state.limiter = limiter  # NEW
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # NEW
app.add_middleware(SlowAPIMiddleware)  # NEW


@app.get("/healthz")
def healthz():
    """Liveness check — is the process up at all."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness check — placeholder until DB/Redis connectivity is wired in."""
    return {"status": "ready"}