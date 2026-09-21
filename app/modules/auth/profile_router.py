"""Brand and creator profile endpoints.

Each account has one profile, and its role decides which kind, so these
endpoints are always about "my own profile" ("/me"): there is no way to read
or change someone else's.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth import profiles
from app.modules.auth.dependencies import CurrentBrand, CurrentCreator, get_now
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.schemas import (
    BrandProfileCreate,
    BrandProfileRead,
    BrandProfileUpdate,
    CreatorProfileCreate,
    CreatorProfileRead,
    CreatorProfileUpdate,
)

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

brand_router = APIRouter(prefix="/api/v1/brands", tags=["profiles"])
creator_router = APIRouter(prefix="/api/v1/creators", tags=["profiles"])

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type does not have that kind of profile"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@brand_router.post(
    "/me",
    status_code=status.HTTP_201_CREATED,
    response_model=BrandProfileRead,
    summary="Create my brand profile",
    description="Creates the profile for the signed-in brand account. One per account.",
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This account already has a profile, or the email is taken"),
        422: problem_doc("A field is missing or invalid"),
    },
)
@limiter.limit(WRITE_LIMIT)
def create_brand_profile(
    request: Request,
    response: Response,
    body: BrandProfileCreate,
    account: CurrentBrand,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> BrandProfileRead:
    profile = profiles.create_profile(db, Brand, account.id, body.model_dump(), now)
    response.headers["Location"] = "/api/v1/brands/me"
    return BrandProfileRead.model_validate(profile)


@brand_router.get(
    "/me",
    response_model=BrandProfileRead,
    summary="Read my brand profile",
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("The profile has not been created yet"),
    },
)
@limiter.limit(READ_LIMIT)
def read_brand_profile(
    request: Request,
    account: CurrentBrand,
    db: Session = Depends(get_db),
) -> BrandProfileRead:
    return BrandProfileRead.model_validate(profiles.get_profile(db, Brand, account.id))


@brand_router.patch(
    "/me",
    response_model=BrandProfileRead,
    summary="Change my brand profile",
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("The profile has not been created yet"),
        409: problem_doc("That email belongs to another brand"),
        422: problem_doc("A field is missing or invalid"),
    },
)
@limiter.limit(WRITE_LIMIT)
def update_brand_profile(
    request: Request,
    body: BrandProfileUpdate,
    account: CurrentBrand,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> BrandProfileRead:
    profile = profiles.get_profile(db, Brand, account.id)
    changes = body.model_dump(exclude_unset=True)
    return BrandProfileRead.model_validate(
        profiles.update_profile(db, profile, changes, now)
    )


@creator_router.post(
    "/me",
    status_code=status.HTTP_201_CREATED,
    response_model=CreatorProfileRead,
    summary="Create my creator profile",
    description=(
        "Creates the profile for the signed-in creator account. One per account. "
        "The handle is stored in lowercase and must be unique."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This account already has a profile, or the handle is taken"),
        422: problem_doc("A field is missing or invalid"),
    },
)
@limiter.limit(WRITE_LIMIT)
def create_creator_profile(
    request: Request,
    response: Response,
    body: CreatorProfileCreate,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CreatorProfileRead:
    profile = profiles.create_profile(db, Creator, account.id, body.model_dump(), now)
    response.headers["Location"] = "/api/v1/creators/me"
    return CreatorProfileRead.model_validate(profile)


@creator_router.get(
    "/me",
    response_model=CreatorProfileRead,
    summary="Read my creator profile",
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("The profile has not been created yet"),
    },
)
@limiter.limit(READ_LIMIT)
def read_creator_profile(
    request: Request,
    account: CurrentCreator,
    db: Session = Depends(get_db),
) -> CreatorProfileRead:
    return CreatorProfileRead.model_validate(
        profiles.get_profile(db, Creator, account.id)
    )


@creator_router.patch(
    "/me",
    response_model=CreatorProfileRead,
    summary="Change my creator profile",
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("The profile has not been created yet"),
        409: problem_doc("That handle belongs to another creator"),
        422: problem_doc("A field is missing or invalid"),
    },
)
@limiter.limit(WRITE_LIMIT)
def update_creator_profile(
    request: Request,
    body: CreatorProfileUpdate,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CreatorProfileRead:
    profile = profiles.get_profile(db, Creator, account.id)
    changes = body.model_dump(exclude_unset=True)
    return CreatorProfileRead.model_validate(
        profiles.update_profile(db, profile, changes, now)
    )


# --- the public Creator Passport switch ----------------------------------
#
# Publishing is a decision, not a field edit, so it is its own action rather
# than a flag on the profile update (backend.md section 2). It also means the
# moment of consent is a single, auditable call.


@creator_router.post(
    "/me/passport/publish",
    response_model=CreatorProfileRead,
    summary="Publish my Creator Passport",
    description=(
        "Turns on the public page at `/api/v1/creators/by-handle/{handle}`, "
        "readable by anyone with the link and no login. It shows your "
        "display name, handle, city, niches, languages, bio and the month "
        "you joined — never your phone number or email. "
        "Publishing again keeps the date you first chose, and you can turn "
        "it off at any time."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("You have not created a creator profile yet"),
    },
)
@limiter.limit(WRITE_LIMIT)
def publish_passport(
    request: Request,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Creator:
    """Only the creator can publish their own profile."""
    creator = profiles.get_profile(db, Creator, account.id)
    return profiles.publish_passport(db, creator, now)


@creator_router.post(
    "/me/passport/unpublish",
    response_model=CreatorProfileRead,
    summary="Take my Creator Passport down",
    description=(
        "Stops the public page answering, immediately. Your profile stays "
        "exactly as it is for campaigns and applications; it simply is not "
        "findable by anyone who is not signed in."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("You have not created a creator profile yet"),
    },
)
@limiter.limit(WRITE_LIMIT)
def unpublish_passport(
    request: Request,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Creator:
    """Withdrawing is never refused."""
    creator = profiles.get_profile(db, Creator, account.id)
    return profiles.unpublish_passport(db, creator, now)
