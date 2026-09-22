"""Security headers on every response (security.md section 7).

These are cheap instructions to the browser about what it may do with our
response. They matter even for a JSON API: a response a browser can be
tricked into interpreting as HTML, or framing inside another page, is the
starting point for several attacks.

Two policies, because we serve two very different things:

- **Everything the API returns is JSON**, and JSON needs to load nothing at
  all. So the policy is `default-src 'none'` — no scripts, no styles, no
  images, nothing. This is as strict as a policy gets.
- **`/docs` and `/redoc` are HTML**, and they pull Swagger UI and ReDoc from
  a CDN and run an inline bootstrap script. A policy that blocked them would
  break the API documentation, which `backend.md` section 2 calls the
  contract the frontend builds against. So those two pages get a wider
  policy, written out origin by origin, and a test asserts the policy still
  covers every URL the pages actually reference.

A route that sets one of these headers itself is left alone, so a future
endpoint can opt out deliberately rather than by accident.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

# Environments where the app is reached over plain HTTP, so HSTS must stay
# off. Matches the naming used for the OTP sender.
LOCAL_ENVIRONMENTS = frozenset({"local", "test"})

# The HTML the docs pages load. Read from FastAPI's own defaults; if a future
# upgrade changes them, test_docs_csp_covers_what_the_page_loads fails.
DOCS_PATHS = frozenset({"/docs", "/redoc"})

# A JSON API needs to load nothing whatsoever.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# Swagger UI and ReDoc, spelled out. 'unsafe-inline' is here because FastAPI
# generates an inline <script> to start the viewer and both libraries inject
# inline styles; we do not control that markup. It is confined to these two
# developer-facing pages, which production does not serve at all (D-044).
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com 'unsafe-inline'; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' https://fastapi.tiangolo.com data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'none'"
)

# One year, and every subdomain. Deliberately no `preload`: that submits the
# domain to a list baked into browsers, which is slow and awkward to undo,
# so it is a founder decision rather than a default.
HSTS = "max-age=31536000; includeSubDomains"

BASE_HEADERS = {
    # Don't guess a content type. Stops a JSON response being treated as HTML.
    "X-Content-Type-Options": "nosniff",
    # Never leak the path a user came from to another site.
    "Referrer-Policy": "no-referrer",
    # Nobody frames us; defends against clickjacking on any HTML we serve.
    "X-Frame-Options": "DENY",
}


def is_https_environment() -> bool:
    """Whether this deployment is reached over HTTPS.

    HSTS must never be sent locally. A browser that receives it for
    `localhost` will force HTTPS on *every* local project on that machine,
    not just this one, and the only cure is clearing it by hand in the
    browser's settings.
    """
    return settings.environment not in LOCAL_ENVIRONMENTS


def policy_for(path: str) -> str:
    """The Content-Security-Policy for a given request path."""
    return DOCS_CSP if path in DOCS_PATHS else API_CSP


class SecurityHeadersMiddleware:
    """Pure ASGI middleware. Add it last, so it wraps every other middleware
    and reaches responses they generate themselves, such as 429 and 413."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        to_add = dict(BASE_HEADERS)
        to_add["Content-Security-Policy"] = policy_for(scope.get("path", ""))
        if is_https_environment():
            to_add["Strict-Transport-Security"] = HSTS

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in to_add.items():
                    # A route that set it already meant to; leave it be.
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
