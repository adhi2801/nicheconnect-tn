"""FastAPI dependencies for profiles: the brand a request acts for (D-148)."""

from typing import Annotated

from fastapi import Depends

from app.modules.auth.brand_dependencies import MaybeBrandAccess
from app.modules.auth.exceptions import ProfileNotFound
from app.modules.auth.models.brand import Brand


def get_acting_brand_profile(access: MaybeBrandAccess) -> Brand:
    """The brand the signed-in account acts for: its own, or one it is on the
    team of, in a role allowed this route (`auth.brand_acts`).

    404 until there is one, as the brand's own profile always answered.
    """
    if access is None:
        raise ProfileNotFound()
    return access.brand


ActingBrandProfile = Annotated[Brand, Depends(get_acting_brand_profile)]
