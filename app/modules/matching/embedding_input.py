"""What text goes into an embedding, and what never does (constraint 2).

`CLAUDE.md` constraint 2: phone numbers, bank details and similar never enter
anything embedded in pgvector. An embedding is not anonymous — text can be
approximately recovered from a vector — so a field that reaches this module
should be treated as published, not hidden.

Two defences, because one is not enough:

1. **A name that looks like a secret raises at import**, the same way
   `app/core/export.py` guards a data export. The mistake becomes a failed
   start-up rather than a leak nobody notices.
2. **Every column is accounted for**, either embedded or deliberately left
   out. A new column on `creator` or `campaign` fails the test in
   `tests/modules/matching/test_embedding_input_model.py` until somebody
   decides which it is. It fails closed: silence is not consent.

Nothing here embeds anything. It builds the string an embedding would be made
from, so that string can be tested on its own, before any model or extension
exists (docs/PROPOSAL_MATCHING.md, step 1).
"""

from typing import Any

# Substrings that may never appear in the name of an embedded field. Wider
# than the export list on purpose: an export goes to the person the data is
# about, an embedding goes into a shared index.
NEVER_EMBEDDED = frozenset(
    {
        "phone",
        "email",
        "bank",
        "upi",
        "address",
        "account",
        "hash",
        "token",
        "secret",
        "password",
    }
)


class ForbiddenEmbeddingField(ValueError):
    """Raised at import time when a field that must not be embedded is listed."""


def embeddable(*names: str) -> tuple[str, ...]:
    """Declare the fields whose text may go into a vector."""
    for name in names:
        lowered = name.lower()
        for banned in NEVER_EMBEDDED:
            if banned in lowered:
                raise ForbiddenEmbeddingField(
                    f"'{name}' cannot be embedded: names containing "
                    f"'{banned}' never enter a vector (CLAUDE.md constraint 2)"
                )
    return names


# What a creator is matched on. Each is something the creator chose to put on
# a public profile.
CREATOR_FIELDS = embeddable("city", "niches", "languages", "bio")

# Left out on purpose, so a new column cannot join either list by accident.
# `display_name` and `handle` are not secret, but a name does nothing for a
# match and would pull a person's identity into a shared index.
CREATOR_NOT_EMBEDDED = frozenset(
    {
        "id",
        "account_id",
        "account_role",
        "display_name",
        "handle",
        "passport_published_at",
        "created_at",
        "updated_at",
    }
)

# What a campaign is matched on. A brand wrote all of it to be read.
CAMPAIGN_FIELDS = embeddable(
    "title", "description", "campaign_type", "cities", "niches", "deliverables"
)

# Budget, dates and status decide whether a campaign is a candidate at all.
# They are filters, and a filter belongs in a WHERE clause where it is exact
# and explainable, never blurred into a vector.
CAMPAIGN_NOT_EMBEDDED = frozenset(
    {
        "id",
        "brand_id",
        "applications_close_on",
        "budget_max_paise",
        "budget_min_paise",
        "currency",
        "status",
        "created_at",
        "updated_at",
    }
)


def _render(value: Any) -> str:
    """One field as text. A list becomes its items, comma separated."""
    if value is None:
        return ""
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value if item)
    return str(value).strip()


def _build(source: object, fields: tuple[str, ...]) -> str:
    """`field: value` lines, in the declared order, skipping empty ones.

    The field name is kept in the text: "city: Madurai" reads to a model as a
    labelled fact, where a bare "Madurai" is just a word.
    """
    lines = []
    for field in fields:
        rendered = _render(getattr(source, field, None))
        if rendered:
            lines.append(f"{field}: {rendered}")
    return "\n".join(lines)


def creator_text(creator: object) -> str:
    """The text a creator's embedding is built from."""
    return _build(creator, CREATOR_FIELDS)


def campaign_text(campaign: object) -> str:
    """The text a campaign's embedding is built from."""
    return _build(campaign, CAMPAIGN_FIELDS)
