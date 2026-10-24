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
from app.modules.admin.models.report import Report
from app.modules.auth import attribution_service as attribution
from app.modules.auth import device_service as devices
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.totp_factor import TotpFactor
from app.modules.campaigns import service as campaigns
from app.modules.deal_memo import service as deal_memos
from app.modules.disputes import service as disputes
from app.modules.me import passkey_service as passkey_changes
from app.modules.me import phone_change_service as phone_changes
from app.modules.me.export_models import DataExport
from app.modules.notifications import preference_service as notification_preferences
from app.modules.notifications import service as notifications
from app.modules.payment_status import service as payments
from app.modules.payment_status import upi_service as upi
from app.modules.profiles import brand_domain_service as brand_domains
from app.modules.profiles.models import CreatorChannel, CreatorPackage
from app.modules.safety import block_service as blocks
from app.modules.safety import takedown_service as takedowns

# Bumped whenever the shape of the file changes, so a reader can tell which
# version it is looking at.
SCHEMA_VERSION = 1

# Tables this module answers for. Every other table is claimed by the module
# that owns it, or listed in NOT_EXPORTED below.
EXPORTED_TABLES = frozenset(
    {
        "account",
        "brand",
        "creator",
        "auth_session",
        # An admin's authenticator: when it was set up, locked or waiting,
        # never the secret or the setup ticket (D-105).
        "totp_factor",
        # A creator's own channels and prices are theirs, and unlike most of
        # what we hold they are something they typed rather than something
        # that happened to them (D-055).
        "creator_channel",
        "creator_package",
        "report",
        # The exports asked for (D-111): times and sizes, never the file.
        "data_export",
    }
)

# Things we hold that are deliberately left out, and why. Printed in the file
# itself: a person is entitled to know what exists, not only what we hand over.
NOT_EXPORTED: dict[str, str] = {
    "passkey_challenge": (
        "The one-time challenges we sent your passkeys to sign, each working "
        "once for 5 minutes and deleted a day after. Random numbers, holding "
        "nothing about you; your passkeys themselves are in this file."
    ),
    "otp_challenge": (
        "One-time login codes. We store only an unreadable hash of each code, "
        "never the code itself, and the record is tied to a phone number rather "
        "than an account. Releasing it would tell you nothing you don't know."
    ),
    "creator_embedding": (
        "A list of numbers worked out from your city, niches, languages and "
        "bio, used to find campaigns that suit you. It holds nothing else: no "
        "contact details, no name, no handle. Everything it was built from is "
        "already in this export, in words you can read, and the numbers are "
        "rebuilt from those words whenever your profile changes."
    ),
    "campaign_embedding": (
        "The same kind of list of numbers, worked out from a campaign's own "
        "brief. It describes a campaign rather than a person."
    ),
    "deal_record_checkpoint": (
        "Once a day, one fingerprint covering the latest seal of every deal on "
        "the platform, yours among thousands. It holds no names, amounts or "
        "text: only that single fingerprint and a count. The proof that ties "
        "your own deal to it is available for each of your deals on its own."
    ),
    "admin_action": (
        "Our staff's log of what they did and when they looked at an "
        "account's details, kept so we can answer who looked at yours and "
        "why. It records staff actions rather than anything you gave us, and "
        "whether it must be shown to you is a question we have put to our "
        "legal checklist rather than guessed. You can ask us, and we will tell "
        "you what it says about your account."
    ),
    "deal_record_timestamp": (
        "Independent timestamp authorities' signed statements that a day's "
        "fingerprint existed at a given time. They say nothing about any one "
        "person, and each deal's proof includes the ones that cover it."
    ),
}

DATA_EXPORT_FIELDS = allow(
    "id",
    "requested_at",
    "ready_at",
    "expires_at",
    "size_bytes",
    "downloaded_at",
    "failed_at",
    "file_deleted_at",
    "created_at",
    "updated_at",
)

ACCOUNT_EXPORT_FIELDS = allow(
    "id",
    "phone",
    "role",
    # Whether we suspended you, and the category of reason (D-061). The
    # admin's own note is not here: it is in the admin log, section below.
    "suspended_at",
    "suspension_reason",
    # When you confirmed you are 18 or over (D-086). The date of birth
    # itself was never kept.
    "adult_confirmed_at",
    "created_at",
    "updated_at",
)
# Reports this person made (D-061): their own statements. Who they reported
# is an id and a kind, never the other person's details.
REPORT_EXPORT_FIELDS = allow(
    "id",
    "subject_kind",
    "subject_id",
    "category",
    "note",
    "status",
    # When we must answer it by, under the IT Rules (item 51).
    "due_at",
    "resolved_at",
    "created_at",
)

# Whether an admin cleared the name as a look-alike, and when (D-119); never
# which admin, whose account is someone else's.
BRAND_EXPORT_FIELDS = allow(
    "id", "name", "email", "name_cleared", "name_cleared_at", "created_at", "updated_at"
)

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
    # The other consent: whether their prices are on the open internet, and
    # when they said so (D-055). Same reasoning as the line above.
    "rate_card_public_at",
    # "Booked until", as they set it (D-083).
    "booked_until",
    "created_at",
    "updated_at",
)

CHANNEL_EXPORT_FIELDS = allow(
    "id",
    "platform",
    "profile_url",
    "followers",
    "average_views",
    "figures_as_of",
    "created_at",
    "updated_at",
)

PACKAGE_EXPORT_FIELDS = allow(
    "id",
    "platform",
    "format",
    "title",
    "description",
    "price_paise",
    "currency",
    "delivery_days",
    "usage_rights_days",
    "position",
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
    # When the sign-in behind it proved a second factor (D-105).
    "second_factor_at",
    # When a passkey proved the sign-in behind it (D-113).
    "passkey_at",
    # What the app said it is at sign-in, so you can tell sessions apart (D-114).
    "client_platform",
    "client_label",
    "used_at",
    "revoked_at",
)
# Never the encrypted secret, nor the setup ticket's hash: neither is
# something you gave us, and either would help someone who took the file.
SECOND_FACTOR_EXPORT_FIELDS = allow(
    "id",
    "enrolled_at",
    "ticket_expires_at",
    "consecutive_failures",
    "locked_at",
    "created_at",
    "updated_at",
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

    if creator is not None:
        channels = list(
            db.scalars(
                select(CreatorChannel)
                .where(CreatorChannel.creator_id == creator.id)
                .order_by(CreatorChannel.platform)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )
        sections.append(
            build_section(
                "channels",
                table="creator_channel",
                purpose=(
                    "The Instagram and YouTube channels you told us about, and "
                    "the follower and view figures you gave, with the date you "
                    "gave them. These are your own numbers: we have never "
                    "checked or changed them."
                ),
                objects=channels,
                fields=CHANNEL_EXPORT_FIELDS,
            )
        )

        packages = list(
            db.scalars(
                select(CreatorPackage)
                .where(CreatorPackage.creator_id == creator.id)
                .order_by(CreatorPackage.position, CreatorPackage.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )
        sections.append(
            build_section(
                "rate_card",
                table="creator_package",
                purpose=(
                    "The packages you offer and what you charge for them. "
                    "Prices are in paise, so 800000 is Rs 8,000. Whether these "
                    "are visible on your public page is recorded on your "
                    "profile as rate_card_public_at."
                ),
                objects=packages,
                fields=PACKAGE_EXPORT_FIELDS,
            )
        )

    reports = list(
        db.scalars(
            select(Report)
            .where(Report.reporter_account_id == account.id)
            .order_by(Report.created_at, Report.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    sections.append(
        build_section(
            "reports_made",
            table="report",
            purpose=(
                "Profiles and campaigns you reported to us, and what became of "
                "each report. Who handled it is not included."
            ),
            objects=reports,
            fields=REPORT_EXPORT_FIELDS,
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
                "When you signed in, on what the app said it was, when each "
                "session expires, and whether it was logged out, so you can see "
                "where you are logged in. The sign-in tokens themselves are not "
                "included."
            ),
            objects=sessions,
            fields=SESSION_EXPORT_FIELDS,
        )
    )
    factors = list(
        db.scalars(select(TotpFactor).where(TotpFactor.account_id == account.id)).all()
    )
    sections.append(
        build_section(
            "second_factor",
            table="totp_factor",
            purpose=(
                "Admins only: when your authenticator app was set up, whether a "
                "setup ticket is waiting, and whether it is locked after wrong "
                "codes. The secret itself and the ticket are not included."
            ),
            objects=factors,
            fields=SECOND_FACTOR_EXPORT_FIELDS,
        )
    )
    return sections


def collect_sections(db: Session, account: Account) -> list[ExportedSection]:
    """Every section of this account's export, in reading order."""
    return [
        *_account_sections(db, account),
        *attribution.export_for_account(db, account.id),
        *blocks.export_for_account(db, account.id),
        *takedowns.export_for_account(db, account.id),
        *brand_domains.export_for_account(db, account.id),
        *campaigns.export_for_account(db, account.id),
        *deal_memos.export_for_account(db, account.id),
        *payments.export_for_account(db, account.id),
        *upi.export_for_account(db, account.id),
        *disputes.export_for_account(db, account.id),
        *notifications.export_for_account(db, account.id),
        *notification_preferences.export_for_account(db, account.id),
        *devices.export_for_account(db, account.id),
        *step_ups.export_for_account(db, account.id),
        *phone_changes.export_for_account(db, account.id),
        *passkey_changes.export_for_account(db, account.id),
        _exports_section(db, account),
    ]


def _exports_section(db: Session, account: Account) -> ExportedSection:
    """The exports this account asked for (D-111): when, and what became of each."""
    exports = list(
        db.scalars(
            select(DataExport)
            .where(DataExport.account_id == account.id)
            .order_by(DataExport.requested_at, DataExport.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    return build_section(
        "data_exports",
        table="data_export",
        purpose=(
            "Each time you asked for a copy of your data: when it was ready, "
            "its size, and when it was downloaded or destroyed. The files "
            "themselves are kept only until you download them, at most a day."
        ),
        objects=exports,
        fields=DATA_EXPORT_FIELDS,
    )


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
        | attribution.EXPORTED_TABLES
        | blocks.EXPORTED_TABLES
        | takedowns.EXPORTED_TABLES
        | brand_domains.EXPORTED_TABLES
        | campaigns.EXPORTED_TABLES
        | deal_memos.EXPORTED_TABLES
        | notifications.EXPORTED_TABLES
        | notification_preferences.EXPORTED_TABLES
        | devices.EXPORTED_TABLES
        | payments.EXPORTED_TABLES
        | upi.EXPORTED_TABLES
        | disputes.EXPORTED_TABLES
        | step_ups.EXPORTED_TABLES
        | phone_changes.EXPORTED_TABLES
        | passkey_changes.EXPORTED_TABLES
    )


def export_filename(now: datetime) -> str:
    """A name that says what the file is and when it was made."""
    return f"nicheconnect-export-{now.date().isoformat()}.json"
