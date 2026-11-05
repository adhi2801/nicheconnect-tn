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

Public and the same for everyone: it says what the product can do for all,
nothing about anyone. While a feature is being rolled out to a share of
accounts (item 92, D-160), it says "off" here and gives the share;
`GET /api/v1/me/features` says whether it is on for the signed-in account.
"""

import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core import rollout
from app.core.config import settings
from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit

PUBLIC_READ_LIMIT = "60 per minute"
# Five minutes: a switch turned on reaches every client within that.
CACHE_SECONDS = 300


class FeatureRead(BaseModel):
    """One feature: whether it is on, and what its routes answer while it is off."""

    model_config = ConfigDict(extra="forbid")

    on: bool = Field(
        description=(
            "On `GET /api/v1/features`: on for everyone. On `GET /api/v1/me/features`: "
            "on for the signed-in account"
        )
    )
    share_percent: int = Field(
        ge=0,
        le=100,
        description=(
            "The share of accounts it reaches when switched on (item 92): 100 for "
            "everyone, less while it is being rolled out"
        ),
        examples=[100],
    )
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
    brief_drafting: FeatureRead = Field(
        description=(
            "A campaign brief drafted from a brand's own words (item 40), behind its "
            "validation pack question"
        )
    )


def _feature(
    name: str, switched: bool, off_code: str | None, account_id: uuid.UUID | None
) -> FeatureRead:
    """On for everyone (no account), or for this account, within its rollout share."""
    percent = rollout.share(name)
    if account_id is None:
        on = switched and percent == rollout.BUCKETS
    else:
        on = switched and rollout.includes(name, account_id)
    return FeatureRead(on=on, share_percent=percent, off_code=off_code)


def current(account_id: uuid.UUID | None = None) -> FeaturesRead:
    """The features as the settings switch them now: for everyone, or for one account."""
    return FeaturesRead(
        passkeys=_feature(
            "passkeys",
            settings.passkey_rp_id is not None,
            "passkeys_unavailable",
            account_id,
        ),
        connected_accounts=_feature(
            "connected_accounts",
            settings.platform_connections_enabled,
            "connections_unavailable",
            account_id,
        ),
        upi_ids=_feature(
            "upi_ids",
            settings.upi_notice_version is not None,
            "upi_not_open_yet",
            account_id,
        ),
        # Its feed answers as if nothing is published while off, never an error.
        passport_indexing=_feature(
            "passport_indexing", settings.passport_indexing, None, account_id
        ),
        # A job reads the screenshots; no route waits on it.
        results_from_proof=_feature(
            "results_from_proof",
            settings.proof_reading_enabled and settings.anthropic_api_key is not None,
            None,
            account_id,
        ),
        brief_drafting=_feature(
            "brief_drafting",
            settings.brief_drafting_enabled and settings.anthropic_api_key is not None,
            "brief_drafting_unavailable",
            account_id,
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
