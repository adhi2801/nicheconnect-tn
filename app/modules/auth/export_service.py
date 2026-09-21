"""Assemble everything this service holds about one account.

This is the "right to access" half of data protection: handing someone their
own data back. It is deliberately separate from deletion, which needs
retention rules we don't have yet (CLAUDE.md constraint 6) — giving people a
copy of their own records never needs a policy answer, removing them does.

Each module describes its own data. This file only puts the pieces in order,
adds the account itself, and writes the manifest that explains what is in the
file and why we hold it.

The file is self-describing on purpose. Someone opening it should be able to
tell what each section is, why it exists, and what we hold that is *not* in
there — rather than having to trust that nothing was left out.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ExportedSection,
    allow,
    build_section,
    to_json_value,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import service as campaigns
from app.modules.deal_memo import service as deal_memos
from app.modules.disputes import service as disputes
from app.modules.notifications import service as notifications
from app.modules.payment_status import service as payments

# Bumped whenever the shape of the file changes, so a reader can tell which
# version it is looking at.
SCHEMA_VERSION = 1

# Tables this module answers for. Every other table is claimed by the module
# that owns it, or listed in NOT_EXPORTED below.
EXPORTED_TABLES = frozenset({"account", "brand", "creator", "auth_session"})

# Things we hold that are deliberately left out, and why. Printed in the file
# itself: a person is entitled to know what exists, not only what we hand over.
NOT_EXPORTED: dict[str, str] = {
    "otp_challenge": (
        "One-time login codes. We store only an unreadable hash of each code, "
        "never the code itself, and the record is tied to a phone number rather "
        "than an account. Releasing it would tell you nothing you don't know."
    ),
}

ACCOUNT_EXPORT_FIELDS = allow("id", "phone", "role", "created_at", "updated_at")

BRAND_EXPORT_FIELDS = allow("id", "name", "email", "created_at", "updated_at")

CREATOR_EXPORT_FIELDS = allow(
    "id",
    "display_name",
    "handle",
    "city",
    "niches",
    "languages",
    "bio",
    # When they chose to publish their Passport, or null if they never did.
    # It is their consent, so it belongs in their own copy of their data.
    "passport_published_at",
    "created_at",
    "updated_at",
)

# Metadata only. The stored hash of each refresh token is not exportable —
# `allow()` would refuse the name — and would be useless if it were.
SESSION_EXPORT_FIELDS = allow(
    "id",
    "family_id",
    "created_at",
    "expires_at",
    "used_at",
    "revoked_at",
)


def _account_sections(db: Session, account: Account) -> list[ExportedSection]:
    """The account itself, its profile, and its login sessions."""
    sections = [
        build_section(
            "account",
            table="account",
            purpose=(
                "Your login identity. We hold your phone number because it is "
                "how you sign in."
            ),
            objects=[account],
            fields=ACCOUNT_EXPORT_FIELDS,
        )
    ]

    brand = db.scalars(select(Brand).where(Brand.account_id == account.id)).first()
    if brand is not None:
        sections.append(
            build_section(
                "brand_profile",
                table="brand",
                purpose="Your business details, shown to creators you work with.",
                objects=[brand],
                fields=BRAND_EXPORT_FIELDS,
            )
        )

    creator = db.scalars(select(Creator).where(Creator.account_id == account.id)).first()
    if creator is not None:
        sections.append(
            build_section(
                "creator_profile",
                table="creator",
                purpose=(
                    "Your creator profile. If you turned your Creator "
                    "Passport on, everything here except that timestamp is "
                    "visible to anyone with your link; if you did not, none "
                    "of it is."
                ),
                objects=[creator],
                fields=CREATOR_EXPORT_FIELDS,
            )
        )

    sessions = list(
        db.scalars(
            select(AuthSession)
            .where(AuthSession.account_id == account.id)
            .order_by(AuthSession.created_at, AuthSession.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    sections.append(
        build_section(
            "login_sessions",
            table="auth_session",
            purpose=(
                "When you signed in, when each session expires, and whether it "
                "was logged out. The sign-in tokens themselves are not included."
            ),
            objects=sessions,
            fields=SESSION_EXPORT_FIELDS,
        )
    )
    return sections


def collect_sections(db: Session, account: Account) -> list[ExportedSection]:
    """Every section of this account's export, in reading order."""
    return [
        *_account_sections(db, account),
        *campaigns.export_for_account(db, account.id),
        *deal_memos.export_for_account(db, account.id),
        *payments.export_for_account(db, account.id),
        *disputes.export_for_account(db, account.id),
        *notifications.export_for_account(db, account.id),
    ]


def build_export(db: Session, account: Account, now: datetime) -> dict[str, Any]:
    """The whole file: the data, a manifest, and what was left out."""
    sections = collect_sections(db, account)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": to_json_value(now),
        "account_id": str(account.id),
        "about": (
            "Everything NicheConnect TN holds about this account. Each section "
            "below is listed in the manifest with the reason we hold it. "
            "NicheConnect TN never receives or holds campaign money; payment "
            "records describe what the two sides told us happened."
        ),
        "manifest": [section.manifest_entry() for section in sections],
        "not_included": [
            {"data": table, "reason": reason}
            for table, reason in sorted(NOT_EXPORTED.items())
        ],
        "data": {section.name: section.records for section in sections},
    }


def exported_tables() -> frozenset[str]:
    """Every table some module claims to export.

    The completeness test compares this against the real schema, so a new
    table has to be dealt with rather than forgotten.
    """
    return (
        EXPORTED_TABLES
        | campaigns.EXPORTED_TABLES
        | deal_memos.EXPORTED_TABLES
        | notifications.EXPORTED_TABLES
        | payments.EXPORTED_TABLES
        | disputes.EXPORTED_TABLES
    )


def export_filename(now: datetime) -> str:
    """A name that says what the file is and when it was made."""
    return f"nicheconnect-export-{now.date().isoformat()}.json"
