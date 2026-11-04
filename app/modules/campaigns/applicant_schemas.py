"""Who applied, as the campaign's brand sees them (R2 of docs/PROPOSAL_FRONTEND_API_REQUESTS.md).

A file of its own: the delivery record's shape lives in `deal_memo.schemas`,
which already imports `campaigns.schemas`, so it cannot be imported back there.
"""

import uuid

from pydantic import BaseModel, Field

from app.modules.campaigns.schemas import ApplicationRead
from app.modules.deal_memo.schemas import CreatorDeliveryRead


class ApplicantRead(BaseModel):
    """The creator behind an application: enough to decide, without opening each one."""

    creator_id: uuid.UUID
    handle: str
    display_name: str
    city: str
    niches: list[str]
    delivery: CreatorDeliveryRead = Field(
        description=(
            "What happened on their deals with any brand, not reviews; null "
            "shares mean not enough to say, never zero"
        )
    )


class BrandApplicationRead(ApplicationRead):
    """An application to one of your campaigns, with who sent it."""

    creator: ApplicantRead
