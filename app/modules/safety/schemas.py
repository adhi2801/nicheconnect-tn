"""Request and response shapes for blocking (item 59) and takedowns (item 52; D-099)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
from app.modules.safety.takedown_models import TAKEDOWN_BASES, TAKEDOWN_SUBJECTS


class BlockCreate(BaseModel):
    """Whom to block. A creator names a brand; a brand names a creator."""

    model_config = ConfigDict(extra="forbid")

    brand_id: uuid.UUID | None = Field(
        default=None, description="For a creator: the brand to block, from a campaign"
    )
    creator_id: uuid.UUID | None = Field(
        default=None, description="For a brand: the creator to block, from search"
    )

    @model_validator(mode="after")
    def exactly_one(self) -> BlockCreate:
        if (self.brand_id is None) == (self.creator_id is None):
            raise PydanticCustomError(
                "block_names_one", "Give brand_id or creator_id, exactly one"
            )
        return self


class BlockRead(BaseModel):
    """A block you placed. The other side is never told."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None
    creator_id: uuid.UUID | None
    name: str = Field(description="The brand's name, or the creator's handle")
    created_at: datetime


class TakedownRead(BaseModel):
    """One of your items withheld for legal reasons (item 52), as you see it.

    Who issued the order, its number and the law it cites are shown unless the
    order is sealed. The admins' names and notes are never shown.
    """

    id: uuid.UUID
    subject_kind: Literal["creator", "brand", "campaign"] = Field(
        description=(
            "What is withheld: your creator profile, your brand (and so every "
            "campaign it posts), or one campaign"
        )
    )
    subject_id: uuid.UUID
    basis: Literal["court_order", "government_notice", "report"] = Field(
        description=(
            "`court_order` or `government_notice`: an order under the IT Rules, "
            "rule 3(1)(d). `report`: a report the IT Rules make us act on while "
            "an admin looks into it. Clients tolerate values they do not know"
        )
    )
    issued_by: str | None = Field(
        description="The court or authority; null for a report, or a sealed order"
    )
    order_reference: str | None = Field(
        description="The order's number; null for a report, or a sealed order"
    )
    legal_provision: str | None = Field(
        description="The law it cites; null when it cites none, or it is sealed"
    )
    reference_sealed: bool = Field(
        description="The order may not be shown to you, so its details are null"
    )
    withheld_at: datetime
    lifted_at: datetime | None = Field(
        description="When it became visible again; null while it is withheld"
    )


# The API's lists must be exactly the database's, or startup fails.
ensure_same_values(
    "TakedownSubject",
    TakedownRead.model_fields["subject_kind"].annotation,
    TAKEDOWN_SUBJECTS,
)
ensure_same_values(
    "TakedownBasis", TakedownRead.model_fields["basis"].annotation, TAKEDOWN_BASES
)
