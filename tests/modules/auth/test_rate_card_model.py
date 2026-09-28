"""The channel and package tables: what the database refuses (D-055).

Every CHECK here exists because a bad row is worse than a rejected write. A
price of zero would quietly poison fair-rate guidance later; an arbitrary
`profile_url` would put a link of someone else's choosing on a public page;
two Instagram rows for one creator would make "their Instagram" ambiguous.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from tests.factories import build_creator

AS_OF = date(2026, 9, 20)


def a_creator(db) -> Creator:
    creator = build_creator(db, handle=f"rc{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    return creator


def channel(db, creator, **overrides) -> CreatorChannel:
    fields = {
        "creator_id": creator.id,
        "platform": "instagram",
        "profile_url": "https://instagram.com/priya.eats",
        "followers": 12_000,
        "average_views": 4_500,
        "figures_as_of": AS_OF,
    }
    fields.update(overrides)
    return CreatorChannel(**fields)


def package(db, creator, **overrides) -> CreatorPackage:
    fields = {
        "creator_id": creator.id,
        "platform": "instagram",
        "format": "reel",
        "title": "1 Instagram Reel",
        "description": "One reel, shot and edited by me.",
        "price_paise": 800_000,
        "currency": "INR",
        "delivery_days": 5,
        "usage_rights_days": 30,
        "position": 0,
    }
    fields.update(overrides)
    return CreatorPackage(**fields)


def assert_rejected_by(db, row, constraint: str) -> None:
    db.add(row)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint in str(exc_info.value)
    db.rollback()


# --- channels --------------------------------------------------------------


def test_a_valid_channel_is_stored(db):
    creator = a_creator(db)
    db.add(channel(db, creator))
    db.flush()

    row = db.scalars(
        select(CreatorChannel).where(CreatorChannel.creator_id == creator.id)
    ).one()
    assert row.followers == 12_000
    assert row.figures_as_of == AS_OF


def test_average_views_may_be_unknown(db):
    """Plenty of creators genuinely do not know it, and a required field would
    only teach them to invent one."""
    creator = a_creator(db)
    db.add(channel(db, creator, average_views=None))
    db.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"platform": "tiktok"}, "platform_allowed"),
        ({"profile_url": "http://instagram.com/x"}, "profile_url_https"),
        ({"followers": -1}, "followers_not_negative"),
        ({"average_views": -1}, "average_views_not_negative"),
    ],
)
def test_the_database_refuses_a_bad_channel(db, overrides, constraint):
    creator = a_creator(db)

    assert_rejected_by(db, channel(db, creator, **overrides), constraint)


def test_one_channel_per_platform_per_creator(db):
    """Otherwise "their Instagram" is ambiguous."""
    creator = a_creator(db)
    db.add(channel(db, creator))
    db.flush()

    assert_rejected_by(db, channel(db, creator), "uq_creator_channel_platform")


def test_the_same_platform_for_two_creators_is_fine(db):
    first, second = a_creator(db), a_creator(db)
    db.add(channel(db, first))
    db.add(channel(db, second))
    db.flush()


def test_deleting_the_creator_takes_their_channels(db):
    creator = a_creator(db)
    db.add(channel(db, creator))
    db.flush()

    db.execute(delete(Creator).where(Creator.id == creator.id))
    db.flush()

    assert (
        db.scalars(
            select(CreatorChannel).where(CreatorChannel.creator_id == creator.id)
        ).all()
        == []
    )


# --- packages --------------------------------------------------------------


def test_a_valid_package_is_stored(db):
    creator = a_creator(db)
    db.add(package(db, creator))
    db.flush()

    row = db.scalars(
        select(CreatorPackage).where(CreatorPackage.creator_id == creator.id)
    ).one()
    assert row.price_paise == 800_000
    assert row.currency == "INR"


def test_a_package_may_omit_description_and_usage_rights(db):
    creator = a_creator(db)
    db.add(package(db, creator, description=None, usage_rights_days=None))
    db.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"platform": "tiktok"}, "platform_allowed"),
        ({"format": "podcast"}, "format_allowed"),
        ({"title": "   "}, "title_not_blank"),
        ({"description": "x" * 501}, "description_length"),
        ({"price_paise": 0}, "price_positive"),
        ({"price_paise": -1}, "price_positive"),
        ({"currency": "USD"}, "currency_allowed"),
        ({"delivery_days": 0}, "delivery_days_range"),
        ({"delivery_days": 91}, "delivery_days_range"),
        ({"usage_rights_days": -1}, "usage_rights_days_range"),
        ({"usage_rights_days": 3651}, "usage_rights_days_range"),
        ({"position": -1}, "position_range"),
        ({"position": 20}, "position_range"),
    ],
)
def test_the_database_refuses_a_bad_package(db, overrides, constraint):
    creator = a_creator(db)

    assert_rejected_by(db, package(db, creator, **overrides), constraint)


def test_a_free_package_is_refused(db):
    """A price of zero is not a price, it is a conversation — and it would
    quietly skew fair-rate guidance, which reads these rows."""
    creator = a_creator(db)

    assert_rejected_by(db, package(db, creator, price_paise=0), "price_positive")


def test_several_packages_keep_their_order(db):
    creator = a_creator(db)
    for i in range(3):
        db.add(package(db, creator, position=i, title=f"Package {i}"))
    db.flush()

    rows = db.scalars(
        select(CreatorPackage)
        .where(CreatorPackage.creator_id == creator.id)
        .order_by(CreatorPackage.position)
    ).all()
    assert [r.position for r in rows] == [0, 1, 2]


def test_deleting_the_creator_takes_their_packages(db):
    creator = a_creator(db)
    db.add(package(db, creator))
    db.flush()

    db.execute(delete(Creator).where(Creator.id == creator.id))
    db.flush()

    assert (
        db.scalars(
            select(CreatorPackage).where(CreatorPackage.creator_id == creator.id)
        ).all()
        == []
    )


# --- the consent column ----------------------------------------------------


def test_prices_are_private_until_the_creator_says_otherwise(db):
    """Like the Passport (D-036): NULL for everybody, because publishing
    someone's rates cannot be undone once search engines have read them."""
    creator = a_creator(db)

    assert creator.rate_card_public_at is None
