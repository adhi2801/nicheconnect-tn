"""What is switched on for the signed-in account (item 92, D-160).

`GET /api/v1/features` says what is on for everyone; while a feature is
being rolled out to a share of accounts, only this answer says whether it is
on for you. A team member is answered as their brand, which is how the
feature's own routes decide (D-148), so a whole team sees the same.
"""

from fastapi import APIRouter, Request, Response

from app.core import features
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.modules.auth.brand_dependencies import AnyBrandAccess
from app.modules.auth.dependencies import CurrentAccount

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/me", tags=["features"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/features",
    response_model=features.FeaturesRead,
    summary="What is switched on for me",
    description=(
        "As `GET /api/v1/features`, but `on` is for the signed-in account: a "
        "feature being rolled out to a share of accounts is on for some and "
        "not others. An account stays in as the share grows. A team member "
        "is answered as their brand. Cached privately for 5 minutes."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def my_features(
    request: Request, response: Response, account: CurrentAccount, access: AnyBrandAccess
) -> features.FeaturesRead:
    response.headers["Cache-Control"] = f"private, max-age={features.CACHE_SECONDS}"
    return features.current(account.id if access is None else access.brand.account_id)
