"""Response shapes for deleting your account (item 6, D-122)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.literals import ensure_same_values
from app.modules.me.account_deletion_registry import KEPT

KeptKindName = Literal[
    "deal_record",
    "payment_record",
    "dispute",
    "proof_file",
    "report",
    "takedown",
    "admin_log",
]

ensure_same_values("KeptKindName", KeptKindName, tuple(kind.kind for kind in KEPT))

# The deals shown as holding a deletion: enough to find and finish them,
# with the full count beside; GET /api/v1/deal-memos lists them all.
MAX_UNFINISHED_SHOWN = 20


class KeptKindRead(BaseModel):
    """One kind of record kept after the account is deleted."""

    kind: KeptKindName = Field(
        description="Clients tolerate kinds they do not know (backend.md section 2)"
    )
    what: str = Field(description="What it holds, in plain words, safe to show")
    kept_for_days: int | None = Field(
        description=(
            "How many days it is kept after the account is deleted. Null: "
            "kept, as the law may require, until a period is set; we do not "
            "guess one"
        )
    )


class AccountDeletionRead(BaseModel):
    """Where deleting your account stands, and what would hold or survive it."""

    status: Literal["none", "waiting", "held"] = Field(
        description=(
            "`none`: not asked for, or cancelled. `waiting`: it takes effect at "
            "`takes_effect_at`. `held`: its 30 days are over, but a deal "
            "begun meanwhile is not finished; it takes effect once it is, "
            "within 15 minutes. Cancel either with `DELETE /api/v1/me/deletion`"
        )
    )
    requested_at: datetime | None
    takes_effect_at: datetime | None = Field(
        description=(
            "30 days after it was asked for. Until then everything works as "
            "before, and you can cancel with no code"
        )
    )
    unfinished_deals: int = Field(
        description=(
            "Your deals not yet finished, declined or cancelled, or with a "
            "payment dispute open. Asking is refused while any is, and an "
            "erasure is held by one begun meanwhile"
        )
    )
    unfinished_deal_ids: list[uuid.UUID] = Field(
        description=f"The memos of the first {MAX_UNFINISHED_SHOWN} of them, by id"
    )
    kept: list[KeptKindRead] = Field(
        description=(
            "What is kept after deletion, because a law may require it. "
            "Everything else about you is erased, and your name, handle and "
            "number go from the deals the other side keeps"
        )
    )
