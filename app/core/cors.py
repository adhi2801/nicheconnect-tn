"""Which websites may call the API from a browser (D-044, security.md section 7).

A browser will not let a web page read our responses unless we name that
page's website as allowed. That is CORS. Only the brand dashboard needs it:
the creator app is a native app, and CORS is a browser rule. Until the
dashboard exists, CORS_ALLOWED_ORIGINS is empty and no website may call us.

Every list here is closed, never a pattern:

- **Websites:** exactly those in CORS_ALLOWED_ORIGINS, checked at startup
  (app/core/config.py). Never `*`.
- **Methods:** the ones the API uses. A test fails if an endpoint uses one
  that is missing, so a new method cannot ship unreachable from the dashboard.
- **Headers a page may send:** the ones the API reads.
- **Headers a page may read:** the ones the API sets that the dashboard needs.
  A browser hides any other header from the page, even though it arrives.
- **No cookies.** The API signs people in with a bearer token in the
  Authorization header, so cross-site cookies are never needed. Refusing
  them closes off cross-site request forgery entirely.

Where this sits among the other middleware is decided in app/main.py.
"""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.idempotency import HEADER as IDEMPOTENCY_KEY_HEADER
from app.core.idempotency import REPLAYED_HEADER
from app.core.request_id import REQUEST_ID_HEADER

# PUT and DELETE joined the list with the rate card (D-055): a creator
# replaces a channel with PUT and removes a channel or a package with DELETE.
# The test below fails if an endpoint uses a method missing here, so a new
# method cannot ship unreachable from the dashboard.
ALLOWED_METHODS = ("GET", "POST", "PATCH", "PUT", "DELETE")

ALLOWED_REQUEST_HEADERS = (
    "Authorization",
    "Content-Type",
    IDEMPOTENCY_KEY_HEADER,
    # Revalidates a cached public Passport without downloading it again.
    "If-None-Match",
    REQUEST_ID_HEADER,
)

EXPOSED_RESPONSE_HEADERS = (
    # Quoted in bug reports, so support can find the log line.
    REQUEST_ID_HEADER,
    # When a 429 may be retried.
    "Retry-After",
    # Where a newly created object lives.
    "Location",
    # The Passport's version, sent back as If-None-Match.
    "ETag",
    # This answer is a replay of an earlier request with the same key.
    REPLAYED_HEADER,
)

# How long a browser may reuse a preflight answer before asking again.
PREFLIGHT_CACHE_SECONDS = 600


def install(app: FastAPI) -> None:
    """Add the CORS middleware to `app`, with the lists above."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=list(ALLOWED_METHODS),
        allow_headers=list(ALLOWED_REQUEST_HEADERS),
        expose_headers=list(EXPOSED_RESPONSE_HEADERS),
        allow_credentials=False,
        max_age=PREFLIGHT_CACHE_SECONDS,
    )
