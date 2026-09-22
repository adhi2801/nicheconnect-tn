"""How app/main.py puts the layers together (D-044, D-045).

The settings are read once, when app/main.py is first imported, just as in a
deployment. So the checks that need other settings start the real app in a
fresh interpreter with those environment variables, instead of reaching into
the app this test run already built.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.core.body_limit import BodyLimitMiddleware
from app.core.request_id import RequestIdMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.unexpected_error import UnexpectedErrorMiddleware
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = "https://app.example.in"


def run_real_app(script: str, **settings: str) -> Any:
    """Run `script` in a fresh interpreter with these settings added to the
    environment, and return the JSON it prints last."""
    result = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, **settings},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_layers_wrap_in_the_intended_order():
    """Outermost first. Each position is explained in app/main.py."""
    assert [middleware.cls for middleware in app.user_middleware] == [
        SecurityHeadersMiddleware,
        RequestIdMiddleware,
        CORSMiddleware,
        UnexpectedErrorMiddleware,
        SlowAPIMiddleware,
        BodyLimitMiddleware,
    ]


def test_the_api_docs_are_served_outside_production():
    client = TestClient(app)

    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200, path


def test_the_api_docs_are_gone_in_production():
    statuses = run_real_app(
        """
        import json
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        paths = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/healthz")
        print(json.dumps({path: client.get(path).status_code for path in paths}))
        """,
        ENVIRONMENT="production",
        CORS_ALLOWED_ORIGINS="",
    )

    assert statuses == {
        "/docs": 404,
        "/redoc": 404,
        "/openapi.json": 404,
        "/docs/oauth2-redirect": 404,
        # The app itself still answers.
        "/healthz": 200,
    }


def test_every_kind_of_answer_reaches_the_dashboard_readably():
    """A refusal or a crash must reach the dashboard's page like any other
    answer: with the CORS permission, the security headers and the request
    ID. Otherwise the page sees only a bare "network error"."""
    seen = run_real_app(
        """
        import json
        import os
        from fastapi.testclient import TestClient
        from app.core.body_limit import MAX_BODY_BYTES
        from app.main import app

        @app.get("/test-only/crash")
        def crash() -> None:
            raise RuntimeError("boom")

        client = TestClient(app, raise_server_exceptions=False)
        origin = {"Origin": os.environ["CORS_ALLOWED_ORIGINS"]}

        def seen(response):
            return {
                "status": response.status_code,
                "allowed": response.headers.get("access-control-allow-origin"),
                "security_headers": "content-security-policy" in response.headers,
                "request_id": "x-request-id" in response.headers,
            }

        results = {
            "preflight": seen(client.options(
                "/healthz", headers={**origin, "Access-Control-Request-Method": "GET"}
            )),
            "too_large": seen(client.post(
                "/healthz", content=b"x" * (MAX_BODY_BYTES + 1), headers=origin
            )),
            "crash": seen(client.get("/test-only/crash", headers=origin)),
        }
        for _ in range(60):
            client.get("/healthz", headers=origin)
        results["rate_limited"] = seen(client.get("/healthz", headers=origin))
        print(json.dumps(results))
        """,
        ENVIRONMENT="test",
        CORS_ALLOWED_ORIGINS=DASHBOARD,
    )

    expected_status = {
        "preflight": 200,
        "too_large": 413,
        "crash": 500,
        "rate_limited": 429,
    }
    for kind, status in expected_status.items():
        assert seen[kind] == {
            "status": status,
            "allowed": DASHBOARD,
            "security_headers": True,
            "request_id": True,
        }, kind
