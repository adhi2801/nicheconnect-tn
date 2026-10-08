"""How a security researcher reaches us: /.well-known/security.txt (RFC 9116).

security.md section 9 (D-082). The file names where to report, in which
language, and the policy; `Expires` is required by the RFC and is a fixed
date, renewed by hand, so a stale contact can never look current. A test fails
30 days before it lapses, which is the reminder to renew it.

`Canonical` is left out until the API has its own domain (BACKEND_COMPLETE
item 4): the RFC asks for it only when the file is signed or served from more
than one place.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit

REPOSITORY = "https://github.com/adhi2801/nicheconnect-tn"
# GitHub's private vulnerability reporting: the report reaches the founders
# and nobody else, and the advisory is drafted in the same place.
CONTACT = f"{REPOSITORY}/security/advisories/new"
POLICY = f"{REPOSITORY}/blob/main/SECURITY.md"
# At most a year ahead (RFC 9116 section 2.5.5). Renew with the test's warning.
EXPIRES = datetime(2027, 4, 30, 18, 29, 59, tzinfo=UTC)
# A day's caching: it changes once or twice a year.
CACHE_SECONDS = 86_400
PUBLIC_READ_LIMIT = "60 per minute"

BODY = (
    f"Contact: {CONTACT}\n"
    f"Expires: {EXPIRES.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
    "Preferred-Languages: en\n"
    f"Policy: {POLICY}\n"
)

router = APIRouter(tags=["public"])


@router.get(
    "/.well-known/security.txt",
    response_class=PlainTextResponse,
    summary="How to report a security problem",
    description=(
        "RFC 9116: where to report a vulnerability, in which language, and "
        "the disclosure policy. Plain text, the same for everyone."
    ),
    responses={
        200: {
            "content": {"text/plain": {"schema": {"type": "string"}}},
            "description": "The security.txt file",
        },
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(PUBLIC_READ_LIMIT)
def security_txt(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        BODY,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": f"public, max-age={CACHE_SECONDS}"},
    )
