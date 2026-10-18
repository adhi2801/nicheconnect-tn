"""Response shapes for asking for, and downloading, the data export (D-111)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.me.data_export_service import ExportStatus


class DataExportRead(BaseModel):
    """One export asked for, and where it stands."""

    id: uuid.UUID
    status: ExportStatus = Field(
        description=(
            "`preparing`, then `ready` (download it, once, before `expires_at`), "
            "then `downloaded`; or `failed`, or `expired` if not downloaded in "
            "24 hours. Ask for a new one after any of the last three."
        )
    )
    requested_at: datetime
    ready_at: datetime | None
    expires_at: datetime | None = Field(
        description="When an undownloaded file is destroyed; null until ready"
    )
    size_bytes: int | None = Field(description="The file's size; null until ready")
    downloaded_at: datetime | None


class DataExportList(BaseModel):
    """The account's newest exports."""

    items: list[DataExportRead] = Field(
        description="At most the 5 newest, newest first: a bound by rule, not paged"
    )
