import uuid
from datetime import date

import pytest
from sqlalchemy.exc import DataError, IntegrityError

from app.modules.campaigns.models import Campaign
from tests.factories import build_campaign


def assert_rejected_by(db, campaign: Campaign, constraint_name: str) -> None:
    db.add(campaign)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def test_valid_campaign_is_saved_with_defaults(db):
    campaign = build_campaign(db, status=None)
    campaign.status = None
    db.add(campaign)
    db.flush()
    db.refresh(campaign)

    assert campaign.id is not None
    assert campaign.currency == "INR"
    assert campaign.status == "draft"
    assert campaign.applications_close_on is None
    assert campaign.created_at is not None


def test_campaign_keeps_its_budget_in_paise(db):
    campaign = build_campaign(db, budget_min_paise=500_000, budget_max_paise=1_500_000)
    db.add(campaign)
    db.flush()
    db.refresh(campaign)

    # 5,00,000 paise is Rs 5,000.
    assert campaign.budget_min_paise == 500_000
    assert isinstance(campaign.budget_min_paise, int)
    assert campaign.budget_max_paise == 1_500_000


def test_campaign_accepts_a_closing_date(db):
    campaign = build_campaign(db, applications_close_on=date(2026, 10, 15))
    db.add(campaign)
    db.flush()

    assert campaign.applications_close_on == date(2026, 10, 15)


# --- owner ---------------------------------------------------------------


def test_campaign_needs_a_real_brand(db):
    assert_rejected_by(
        db, build_campaign(db, brand_id=uuid.uuid4()), "fk_campaign_brand_id_brand"
    )


def test_campaign_without_a_brand_is_rejected(db):
    assert_rejected_by(db, build_campaign(db, brand_id=None), "brand_id")


def test_brand_with_campaigns_cannot_be_deleted(db):
    from app.modules.auth.models.brand import Brand

    campaign = build_campaign(db)
    db.add(campaign)
    db.flush()
    brand = db.get(Brand, campaign.brand_id)

    db.delete(brand)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert "fk_campaign_brand_id_brand" in str(exc_info.value)


# --- type, status, currency ----------------------------------------------


@pytest.mark.parametrize("campaign_type", ["paid", "commission", "local_business"])
def test_budgeted_and_commission_types_are_allowed(db, campaign_type):
    db.add(build_campaign(db, campaign_type=campaign_type))
    db.flush()


def test_barter_campaign_carries_no_budget(db):
    db.add(
        build_campaign(
            db, campaign_type="barter", budget_min_paise=None, budget_max_paise=None
        )
    )
    db.flush()


def test_barter_campaign_with_a_budget_is_rejected(db):
    assert_rejected_by(
        db,
        build_campaign(db, campaign_type="barter"),
        "ck_campaign_budget_matches_type",
    )


@pytest.mark.parametrize("campaign_type", ["paid", "local_business"])
def test_paid_campaign_without_a_budget_is_rejected(db, campaign_type):
    assert_rejected_by(
        db,
        build_campaign(
            db,
            campaign_type=campaign_type,
            budget_min_paise=None,
            budget_max_paise=None,
        ),
        "ck_campaign_budget_matches_type",
    )


def test_commission_campaign_may_leave_the_budget_open(db):
    db.add(
        build_campaign(
            db,
            campaign_type="commission",
            budget_min_paise=None,
            budget_max_paise=None,
        )
    )
    db.flush()


@pytest.mark.parametrize("campaign_type", ["gift", "PAID", ""])
def test_unknown_campaign_type_is_rejected(db, campaign_type):
    assert_rejected_by(
        db, build_campaign(db, campaign_type=campaign_type), "ck_campaign_type_allowed"
    )


@pytest.mark.parametrize("status", ["draft", "open", "closed", "cancelled"])
def test_every_allowed_status_is_accepted(db, status):
    db.add(build_campaign(db, status=status))
    db.flush()


@pytest.mark.parametrize("status", ["archived", "Open", ""])
def test_unknown_status_is_rejected(db, status):
    assert_rejected_by(db, build_campaign(db, status=status), "ck_campaign_status_allowed")


def test_currency_other_than_rupees_is_rejected(db):
    assert_rejected_by(db, build_campaign(db, currency="USD"), "ck_campaign_currency_allowed")


# --- budget rules --------------------------------------------------------


def test_maximum_below_minimum_is_rejected(db):
    assert_rejected_by(
        db,
        build_campaign(db, budget_min_paise=1_500_000, budget_max_paise=500_000),
        "ck_campaign_budget_range",
    )


@pytest.mark.parametrize("budget_min_paise", [0, -100])
def test_zero_or_negative_budget_is_rejected(db, budget_min_paise):
    assert_rejected_by(
        db,
        build_campaign(db, budget_min_paise=budget_min_paise, budget_max_paise=500_000),
        "ck_campaign_budget_range",
    )


def test_minimum_without_maximum_is_rejected(db):
    assert_rejected_by(
        db,
        build_campaign(db, budget_min_paise=500_000, budget_max_paise=None),
        "ck_campaign_budget_range",
    )


def test_equal_minimum_and_maximum_is_allowed(db):
    db.add(build_campaign(db, budget_min_paise=500_000, budget_max_paise=500_000))
    db.flush()


def test_large_budget_fits(db):
    # Rs 1 crore in paise, far beyond a 32-bit integer.
    db.add(build_campaign(db, budget_min_paise=1_000_000_000, budget_max_paise=1_000_000_000))
    db.flush()


# --- text and lists ------------------------------------------------------


@pytest.mark.parametrize("title", ["", "   "])
def test_blank_title_is_rejected(db, title):
    assert_rejected_by(db, build_campaign(db, title=title), "ck_campaign_title_not_blank")


def test_title_over_120_characters_is_rejected(db):
    db.add(build_campaign(db, title="t" * 121))
    with pytest.raises(DataError) as exc_info:
        db.flush()
    assert "value too long" in str(exc_info.value)


def test_description_over_4000_characters_is_rejected(db):
    assert_rejected_by(
        db, build_campaign(db, description="d" * 4001), "ck_campaign_description_length"
    )


@pytest.mark.parametrize("deliverables", ["", "  "])
def test_blank_deliverables_are_rejected(db, deliverables):
    assert_rejected_by(
        db,
        build_campaign(db, deliverables=deliverables),
        "ck_campaign_deliverables_not_blank",
    )


def test_deliverables_over_2000_characters_are_rejected(db):
    assert_rejected_by(
        db, build_campaign(db, deliverables="d" * 2001), "ck_campaign_deliverables_length"
    )


@pytest.mark.parametrize("cities", [[], ["c"] * 11])
def test_city_count_outside_one_to_ten_is_rejected(db, cities):
    assert_rejected_by(db, build_campaign(db, cities=cities), "ck_campaign_cities_count")


@pytest.mark.parametrize("niches", [[], ["food", "fashion", "beauty", "tech", "travel", "fitness"]])
def test_niche_count_outside_one_to_five_is_rejected(db, niches):
    assert_rejected_by(db, build_campaign(db, niches=niches), "ck_campaign_niches_count")


def test_unknown_niche_is_rejected(db):
    assert_rejected_by(
        db, build_campaign(db, niches=["food", "gaming"]), "ck_campaign_niches_allowed"
    )


def test_campaign_and_creator_share_one_niche_list():
    from app.core.taxonomy import NICHES
    from app.modules.auth.models.creator import CREATOR_NICHES

    assert CREATOR_NICHES is NICHES
