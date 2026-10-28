"""Response shapes for what is waiting on you and your data export (D-099)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.core.attention import AttentionList
from app.core.taxonomy import CURRENCY
from app.modules.auth.schemas import AttentionKind, ClientPlatform, SignInMethod


class ExportManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    records: int
    purpose: str = Field(description="Why we hold this data")
    truncated: bool | None = Field(
        default=None, description="Present, and true, only when rows were left out"
    )
    note: str | None = None


class ExportNotIncluded(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: str
    reason: str


class ExportFile(BaseModel):
    """The file `POST /api/v1/me/exports/{export_id}/download` returns, for the API docs.

    The route builds the file itself so it can offer it as a download, so
    FastAPI cannot see this shape on its own. A test checks every real
    export against this model, so the two cannot drift apart.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    generated_at: str = Field(description="UTC, ISO 8601")
    account_id: uuid.UUID
    about: str
    manifest: list[ExportManifestEntry]
    not_included: list[ExportNotIncluded] = Field(
        description="What we hold but deliberately leave out, and why"
    )
    data: dict[str, list[dict[str, Any]]] = Field(
        description="One list of records per manifest section"
    )


class AttentionItemRead(BaseModel):
    """One thing waiting on the caller. The words belong to the frontend."""

    kind: AttentionKind
    due_on: date | None = Field(
        description="The Tamil Nadu date it is due by; null when nothing sets a date"
    )
    days_left: int | None = Field(
        description="Days until due_on; negative when overdue, 0 on the day itself"
    )
    campaign_id: uuid.UUID | None = Field(
        description=(
            "The campaign it is about; null for an item about the account itself "
            "(a domain item, added 17 October 2026). Clients must tolerate null"
        )
    )
    campaign_title: str | None
    counterparty: str | None = Field(
        description="A creator's handle for a brand, a brand's name for a creator"
    )
    application_id: uuid.UUID | None
    memo_id: uuid.UUID | None
    proof_id: uuid.UUID | None
    draft_id: uuid.UUID | None = Field(
        default=None, description="For review_draft: the draft waiting (item 27)"
    )
    amount_paise: int | None
    currency: Literal["INR"] | None
    count: int | None = Field(
        description="For an item that stands for several things, such as applications"
    )
    domain: str | None = Field(
        default=None,
        description="The brand's domain, for fix_domain_record, domain_lapsed and domain_claim_expired",
    )
    session_id: uuid.UUID | None = Field(
        default=None,
        description="For new_sign_in: the session, to end at DELETE /api/v1/me/sessions/{id}",
    )
    signed_in_at: datetime | None = Field(
        default=None, description="For new_sign_in: when it signed in"
    )
    device_platform: ClientPlatform | None = Field(
        default=None,
        description="For new_sign_in: what the app said it is; null when it said nothing",
    )
    device_label: str | None = Field(
        default=None,
        description=(
            "For new_sign_in: the name the app gave itself, never checked; "
            "null when it said nothing"
        ),
    )
    signed_in_with: SignInMethod | None = Field(
        default=None,
        description="For new_sign_in: `phone_code`, `passkey` or `two_factors`",
    )


class AttentionRead(BaseModel):
    """What is waiting on the signed-in account, the most urgent first."""

    role: Literal["brand", "creator"]
    as_of: date = Field(description="The Tamil Nadu date the list was worked out for")
    total: int
    truncated: bool = Field(description="True when more items exist than are listed")
    counts: dict[AttentionKind, int] = Field(
        description="Items per kind, every kind for the role present, zeros included"
    )
    items: list[AttentionItemRead]


def to_attention_read(result: AttentionList) -> AttentionRead:
    return AttentionRead(
        role=result.role,
        as_of=result.as_of,
        total=result.total,
        truncated=result.truncated,
        counts=result.counts,
        items=[
            AttentionItemRead(
                kind=item.kind,
                due_on=item.due_on,
                days_left=(
                    None if item.due_on is None else (item.due_on - result.as_of).days
                ),
                campaign_id=item.campaign_id,
                campaign_title=item.campaign_title,
                counterparty=item.counterparty,
                application_id=item.application_id,
                memo_id=item.memo_id,
                proof_id=item.proof_id,
                draft_id=item.draft_id,
                amount_paise=item.amount_paise,
                currency=None if item.amount_paise is None else CURRENCY,
                count=item.count,
                domain=item.domain,
                session_id=item.session_id,
                signed_in_at=item.signed_in_at,
                device_platform=cast("ClientPlatform | None", item.device_platform),
                device_label=item.device_label,
                signed_in_with=cast("SignInMethod | None", item.signed_in_with),
            )
            for item in result.items
        ],
    )
