from fastapi import FastAPI

app = FastAPI(title="NicheConnect TN API")


@app.get("/healthz")
def healthz():
    """Liveness check — is the process up at all."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness check — placeholder until DB/Redis connectivity is wired in."""
    return {"status": "ready"}
