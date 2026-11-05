"""A brand's plain words read as creator-search filters, over HTTP (item 64, D-158)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.brand_dependencies import MaybeBrandAccess
from app.modules.auth.dependencies import CurrentBrand, get_now
from app.modules.matching import words_service as service
from app.modules.matching.search_router import SEARCH_LIMIT
from app.modules.matching.words_reader import MAX_WORDS_LENGTH
from app.modules.matching.words_schemas import SearchReadingRead, to_read

router = APIRouter(prefix="/api/v1/creators", tags=["creator search"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brands search for creators"),
    422: problem_doc("No words, or more than 200 characters"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/search-reading",
    response_model=SearchReadingRead,
    summary="Read a creator search written in plain words",
    description=(
        'Turns a sentence such as "café creators in Coimbatore, 5k to 20k '
        'followers, free on 14 November" into the filters of `GET '
        "/api/v1/creators`, and says which words became which filter. Read by "
        "fixed rules, never a model: the words stay on our servers and always "
        "read the same way. What the rules cannot read comes back as `unread`, "
        "never guessed, with a note where there is a reason. Places are the "
        "ones creators you could find wrote, and Tamil Nadu's districts. "
        "Nothing is searched: pass `filters` to `GET /api/v1/creators`, which "
        "has the same rate limit. Brands only."
    ),
    responses=_ERRORS,
)
@rate_limit(SEARCH_LIMIT)
def read_search_words(
    request: Request,
    account: CurrentBrand,
    access: MaybeBrandAccess,
    db: Annotated[Session, Depends(get_db)],
    words: Annotated[
        str,
        Query(
            min_length=2,
            max_length=MAX_WORDS_LENGTH,
            description="What the brand is looking for, in its own words",
            examples=["Café creators in Coimbatore, 5k to 20k followers"],
        ),
    ],
    now: datetime = Depends(get_now),
) -> SearchReadingRead:
    # A team member reads places as the brand, as search does (D-148).
    viewer = account.id if access is None else access.brand.account_id
    return to_read(service.read_words(db, words, viewer, india_date(now)))
