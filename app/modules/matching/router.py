"""HTTP endpoint for matching (D-052). HTTP only: rules live in service.py."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.schemas import PublicCreatorRead
from app.modules.campaigns.dependencies import OwnedCampaign
from app.modules.matching import service
from app.modules.matching.schemas import (
    CreatorMatchesRead,
    CreatorMatchRead,
    MatchReasonsRead,
)

READ_LIMIT = "60 per minute"

DEFAULT_MATCHES = 20
MAX_MATCHES = 50

router = APIRouter(prefix="/api/v1/campaigns", tags=["matching"])

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No token, or the token is not valid"),
    403: problem_doc("Only a brand may ask for matches"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/{campaign_id}/matches",
    response_model=CreatorMatchesRead,
    summary="Creators who suit this campaign",
    description=(
        "Creators worth approaching for one of the signed-in brand's own "
        "campaigns, best first, each with the reasons it was suggested.\n\n"
        "Only creators in a city the campaign named, in at least one of its "
        "niches, **and who have published their Creator Passport**. A creator "
        "who has not published is not discoverable here; that is their choice "
        "to make and it is not overridden by a brand searching (D-036).\n\n"
        "If the campaign has not been indexed yet, `ranked_by_similarity` is "
        "false and `similarity` is null on every row: the list is ordered by "
        "the facts alone and is still worth reading."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such campaign, or it is not yours"),
        409: problem_doc("The brand profile has not been created yet"),
        422: problem_doc("A query parameter is invalid"),
    },
)
@rate_limit(READ_LIMIT)
def list_matches_for_campaign(
    request: Request,
    campaign: OwnedCampaign,
    limit: Annotated[
        int, Query(ge=1, le=MAX_MATCHES, description="How many creators to suggest")
    ] = DEFAULT_MATCHES,
    db: Session = Depends(get_db),
) -> CreatorMatchesRead:
    matches = service.find_creators_for_campaign(db, campaign, limit=limit)
    return CreatorMatchesRead(
        # Every row carries the same answer, so read it off the first one;
        # with no rows there is nothing to have ranked either way.
        ranked_by_similarity=bool(matches) and matches[0].reasons.similarity is not None,
        matches=[
            CreatorMatchRead(
                creator=PublicCreatorRead(
                    id=match.creator.id,
                    handle=match.creator.handle,
                    display_name=match.creator.display_name,
                    city=match.creator.city,
                    niches=match.creator.niches,
                    languages=match.creator.languages,
                    bio=match.creator.bio,
                    member_since=match.creator.created_at.strftime("%Y-%m"),
                ),
                reasons=MatchReasonsRead.model_validate(match.reasons),
            )
            for match in matches
        ],
    )
