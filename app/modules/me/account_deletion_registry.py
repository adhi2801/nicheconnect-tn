"""What happens to every table when an account is deleted (item 6, D-122).

Every table the app has is in exactly one place below, and
tests/modules/me/test_account_deletion_registry.py fails when one is in
none, or two. So a new table cannot hold personal data that deletion
quietly forgets:

- ERASED: the account's rows are deleted, each by the module that owns it;
- EMPTIED: the row stays, because deals point at it, emptied of whatever
  identifies the person (`auth.erasure`);
- HELD: kept, because a law may require it, under a retention kind whose
  period is a setting left unset until the validation pack gives it
  (constraint 6). Unset means kept, as the law may require; deleting each
  kind once its period ends is a later item;
- NOT_PERSONAL: holds nothing about a person.

The kinds and what they hold are also what the owner is shown before
asking (`GET /api/v1/me/deletion`), so nobody is told "everything goes".
"""

from dataclasses import dataclass

from app.core.config import Settings, settings

ERASED: frozenset[str] = frozenset(
    {
        # auth (auth.erasure)
        "auth_session",
        "device_token",
        "passkey",
        "passkey_challenge",
        "passkey_reset",
        "step_up_challenge",
        "otp_challenge",
        "account_phone_change",
        "totp_factor",
        "account_attribution",
        "invite_code",
        # notifications
        "notification",
        "notification_preference",
        # safety
        "account_block",
        # payment_status
        "creator_upi",
        "creator_upi_change",
        # profiles
        "creator_channel",
        "creator_package",
        "brand_domain",
        # matching
        "creator_embedding",
        # me
        "data_export",
    }
)

EMPTIED: frozenset[str] = frozenset({"account", "brand", "creator"})


@dataclass(frozen=True)
class KeptKind:
    """One kind of record kept after deletion, and the setting for how long."""

    kind: str
    tables: frozenset[str]
    setting: str
    what: str

    def kept_for_days(self, values: Settings = settings) -> int | None:
        """The period in days, or None: kept, as the law may require."""
        days: int | None = getattr(values, self.setting)
        return days


KEPT: tuple[KeptKind, ...] = (
    KeptKind(
        kind="deal_record",
        tables=frozenset(
            {
                "campaign",
                # The deliverables as a list (item 26), each the brief's or
                # the terms' own lines.
                "campaign_deliverable",
                "memo_deliverable",
                # Notes written on a deal (item 17), sealed onto its record.
                "deal_note",
                "application",
                # Counter-offers on a quote (item 44): the negotiation both
                # sides keep a record of.
                "quote_offer",
                "deal_memo",
                "deliverable_proof",
                "deal_record_entry",
            }
        ),
        setting="retention_deal_record_days",
        what=(
            "Your deals as the other side agreed them: campaigns, "
            "applications and the offers on them, memos, proof links and the "
            "sealed record of each. "
            "The other side keeps their own record of the deal, with you "
            "shown as someone who left."
        ),
    ),
    KeptKind(
        kind="payment_record",
        tables=frozenset({"payment_status"}),
        setting="retention_payment_record_days",
        what=(
            "Whether and when each deal was paid, and how much: the record "
            "tax law may ask about. Never a UPI ID, which is erased."
        ),
    ),
    KeptKind(
        kind="dispute",
        tables=frozenset({"dispute", "dispute_event"}),
        setting="retention_dispute_days",
        what="Payment disputes about your deals, with both sides' accounts.",
    ),
    KeptKind(
        kind="proof_file",
        tables=frozenset({"proof_file", "proof_file_reading"}),
        setting="retention_proof_file_days",
        what="Screenshots sent as proof of work, and what was read from them.",
    ),
    KeptKind(
        kind="report",
        tables=frozenset({"report"}),
        setting="retention_report_days",
        what="Reports you made, or that were made about you, and how they ended.",
    ),
    KeptKind(
        kind="takedown",
        tables=frozenset({"takedown"}),
        setting="retention_takedown_days",
        what=(
            "Anything withheld on a legal order, kept at least 180 days as "
            "the IT Rules require."
        ),
    ),
    KeptKind(
        kind="admin_log",
        tables=frozenset({"admin_action"}),
        setting="retention_admin_log_days",
        what="Our staff's log of what they did, and when they looked at your account.",
    ),
)

HELD: frozenset[str] = frozenset().union(*(kind.tables for kind in KEPT))

NOT_PERSONAL: dict[str, str] = {
    "campaign_embedding": "Numbers worked out from a campaign's brief, not a person",
    "deal_record_checkpoint": "One fingerprint a day over every deal, and a count",
    "deal_record_timestamp": "Timestamp authorities' signatures over a checkpoint",
}
