"""Nothing private reaches a vector (CLAUDE.md constraint 2).

An embedding is not anonymous: text can be approximately recovered from a
vector, and unlike a row in a table it lands in a shared index that matching
searches across accounts. So these tests are about the one rule that has no
exceptions, and they are written to fail closed — a new column on `creator`
or `campaign` breaks them until somebody says which side it belongs on.
"""

import pytest

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign
from app.modules.matching.embedding_input import (
    CAMPAIGN_FIELDS,
    CAMPAIGN_NOT_EMBEDDED,
    CREATOR_FIELDS,
    CREATOR_NOT_EMBEDDED,
    ForbiddenEmbeddingField,
    campaign_text,
    creator_text,
    embeddable,
)
from tests.factories import FIXED_NOW

# --- the rule itself ------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["phone", "email", "bank_account", "upi_id", "address", "account_id", "code_hash"],
)
def test_a_field_that_looks_private_cannot_be_declared(name):
    """It raises at import, so the mistake stops the app instead of leaking."""
    with pytest.raises(ForbiddenEmbeddingField) as exc_info:
        embeddable(name)

    assert name in str(exc_info.value)


def test_the_declared_lists_are_themselves_checked():
    """The guard is only worth having if the real lists went through it."""
    assert embeddable(*CREATOR_FIELDS) == CREATOR_FIELDS
    assert embeddable(*CAMPAIGN_FIELDS) == CAMPAIGN_FIELDS


# --- every column is accounted for ----------------------------------------


def test_every_creator_column_is_embedded_or_deliberately_not():
    """A new column on creator fails this until somebody decides.

    Silence is not consent: the failure mode this prevents is a column being
    added later and quietly going into a shared index.
    """
    columns = set(Creator.__table__.columns.keys())
    accounted = set(CREATOR_FIELDS) | CREATOR_NOT_EMBEDDED

    assert columns == accounted, (
        f"unaccounted: {sorted(columns - accounted)}; "
        f"listed but gone: {sorted(accounted - columns)}"
    )


def test_every_campaign_column_is_embedded_or_deliberately_not():
    columns = set(Campaign.__table__.columns.keys())
    accounted = set(CAMPAIGN_FIELDS) | CAMPAIGN_NOT_EMBEDDED

    assert columns == accounted, (
        f"unaccounted: {sorted(columns - accounted)}; "
        f"listed but gone: {sorted(accounted - columns)}"
    )


def test_the_two_lists_never_overlap():
    assert not set(CREATOR_FIELDS) & CREATOR_NOT_EMBEDDED
    assert not set(CAMPAIGN_FIELDS) & CAMPAIGN_NOT_EMBEDDED


# --- what the built text actually contains --------------------------------


def creator_carrying_every_private_value() -> Creator:
    """A creator whose every non-embedded field is a findable marker."""
    return Creator(
        account_id="00000000-0000-0000-0000-00000000dead",
        account_role="creator",
        display_name="PRIVATE-DISPLAY-NAME",
        handle="private-handle",
        city="Madurai",
        niches=["food", "travel"],
        languages=["en"],
        bio="Street food across Tamil Nadu.",
        passport_published_at=FIXED_NOW,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def test_no_private_creator_value_reaches_the_text():
    text = creator_text(creator_carrying_every_private_value())

    for forbidden in (
        "PRIVATE-DISPLAY-NAME",
        "private-handle",
        "00000000-0000-0000-0000-00000000dead",
    ):
        assert forbidden not in text


def test_the_creator_text_carries_what_a_match_needs():
    text = creator_text(creator_carrying_every_private_value())

    assert "city: Madurai" in text
    assert "niches: food, travel" in text
    assert "bio: Street food across Tamil Nadu." in text


def test_a_creator_with_no_bio_still_builds():
    """bio is nullable; an empty field is left out rather than written blank."""
    creator = creator_carrying_every_private_value()
    creator.bio = None

    text = creator_text(creator)

    assert "bio" not in text
    assert "city: Madurai" in text


def test_no_private_campaign_value_reaches_the_text():
    campaign = Campaign(
        brand_id="00000000-0000-0000-0000-0000000000ff",
        title="Pongal sweets launch",
        description="Three reels featuring our new sweet box.",
        campaign_type="paid",
        budget_min_paise=500_000,
        budget_max_paise=1_500_000,
        cities=["Madurai"],
        niches=["food"],
        deliverables="3 Instagram reels.",
        status="open",
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )

    text = campaign_text(campaign)

    assert "00000000-0000-0000-0000-0000000000ff" not in text
    # Budget is a filter, exact in a WHERE clause; blurring it into a vector
    # would make "within my budget" a matter of similarity.
    assert "500000" not in text
    assert "1500000" not in text
    assert "title: Pongal sweets launch" in text
    assert "niches: food" in text
