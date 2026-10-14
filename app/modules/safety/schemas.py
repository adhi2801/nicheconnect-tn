"""Request and response shapes for blocking (item 59, D-099)."""

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_core import PydanticCustomError


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
