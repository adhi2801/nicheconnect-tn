"""What is switched on: GET /api/v1/features (R6 of docs/PROPOSAL_FRONTEND_API_REQUESTS.md).

Several built features stay off until something outside the code arrives:
the domain (passkeys), Meta's and Google's approval (connected accounts),
the validation pack's notice wording (UPI IDs, Passport indexing, results
read from proof). A screen cannot hide what is off unless the API says, and
a store release just to turn one on would be a week's wait, so the apps
read this instead (frontend.md section 14: feature flags).

Read from the settings each feature is already switched by, so this can
never say "on" while the feature's own routes say "off". For each, the
problem code those routes answer while it is off, so a client that calls
one anyway knows what it met. `tests/core/test_features.py` holds every
code to the exception its module really raises.

Public and the same for everyone: it says what the product can do, nothing
about anyone.
"""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit

PUBLIC_READ_LIMIT = "60 per minute"
# Five minutes: a switch turned on reaches every client within that.
CACHE_SECONDS = 300


class FeatureRead(BaseModel):
    """One feature: whether it is on, and what its routes answer while it is off."""

    model_config = ConfigDict(extra="forbid")

    on: bool
    off_code: str | None = Field(
        description=(
            "The problem `code` this feature's routes answer while it is off; "
            "null when it has no route of its own to call"
        ),
        examples=["connections_unavailable"],
    )


class FeaturesRead(BaseModel):
    """Every feature that can be switched off. Unknown keys may appear: ignore them."""

    passkeys: FeatureRead = Field(
        description="Signing in and proving changes with a passkey (item 79): on once the domain exists"
    )
    connected_accounts: FeatureRead = Field(
        description=(
            "Connecting Instagram and YouTube (item 29): on once Meta and Google "
            "approve the apps and the connect notice exists"
        )
    )
    upi_ids: FeatureRead = Field(
        description=(
            "A creator adding a UPI ID, and the pay link brands open from it "
            "(D-085): on once its notice exists. Until then brands pay by bank transfer"
        )
    )
    passport_indexing: FeatureRead = Field(
        description="Published Passports offered to search engines (item 85): on once the publish notice says so"
    )
    results_from_proof: FeatureRead = Field(
        description="Reach and views read from proof screenshots (D-070), behind its validation pack question"
    )


def current() -> FeaturesRead:
    """The features as the settings switch them now."""
    return FeaturesRead(
        passkeys=FeatureRead(
            on=settings.passkey_rp_id is not None, off_code="passkeys_unavailable"
        ),
        connected_accounts=FeatureRead(
            on=settings.platform_connections_enabled, off_code="connections_unavailable"
        ),
        upi_ids=FeatureRead(
            on=settings.upi_notice_version is not None, off_code="upi_not_open_yet"
        ),
        # Its feed answers as if nothing is published while off, never an error.
        passport_indexing=FeatureRead(on=settings.passport_indexing, off_code=None),
        # A job reads the screenshots; no route waits on it.
        results_from_proof=FeatureRead(
            on=settings.proof_reading_enabled and settings.anthropic_api_key is not None,
            off_code=None,
        ),
    )


router = APIRouter(tags=["public"])


@router.get(
    "/api/v1/features",
    response_model=FeaturesRead,
    summary="What is switched on",
    description=(
        "Which built features are on now, and for each the problem `code` its "
        "routes answer while it is off, so a screen can hide what is off and "
        "show it the moment it is switched on, with no app release. The same "
        "for everyone; no login. Cached for 5 minutes. Limit: 60 a minute."
    ),
    responses={429: problem_doc("Too many requests; see the Retry-After header")},
)
@rate_limit(PUBLIC_READ_LIMIT)
def features(request: Request, response: Response) -> FeaturesRead:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return current()
