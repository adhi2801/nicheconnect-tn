"""The words stored for matching (D-173): `creator.bio_words`, `campaign.brief_words`.

The rules worth proving: the database stores exactly the words matching would
cut from the same text (the two configs cannot drift apart); the words follow
every change to the text; nothing can write them by hand; and an ordinary
read of a creator or a campaign does not fetch them.
"""

import uuid

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign
from app.modules.matching import fusion
from tests.factories import build_campaign, build_creator

TEXTS = [
    "Chettinad home cooking, slow and spicy. Cooking classes every Sunday!",
    "Order at shop.example/menu?a=1&b=2 — சென்னை filter coffee",
    "",
]


def a_creator(db, bio):
    creator = build_creator(db, handle=f"w{uuid.uuid4().hex[:12]}", bio=bio)
    db.add(creator)
    db.flush()
    return creator


def a_campaign(db, title, description):
    campaign = build_campaign(db, title=title, description=description)
    db.add(campaign)
    db.flush()
    return campaign


def stored(db, column, row_id, id_column):
    return set(
        db.scalar(select(func.tsvector_to_array(column)).where(id_column == row_id))
    )


def cut(db, words):
    return set(db.scalar(select(fusion.words_of(words))))


@pytest.mark.parametrize("bio", [*TEXTS, None])
def test_a_bio_s_stored_words_are_the_words_matching_cuts(db, bio):
    creator = a_creator(db, bio)

    assert stored(db, Creator.bio_words, creator.id, Creator.id) == cut(
        db, fusion.bio_words(creator)
    )


@pytest.mark.parametrize("title", ["Filter coffee mornings", "Biryani week"])
@pytest.mark.parametrize("description", TEXTS)
def test_a_brief_s_stored_words_are_the_words_matching_cuts(db, title, description):
    campaign = a_campaign(db, title, description)

    assert stored(db, Campaign.brief_words, campaign.id, Campaign.id) == cut(
        db, fusion.brief_words(campaign)
    )


def test_the_words_follow_every_change_to_the_text(db):
    creator = a_creator(db, "Street food reels.")
    campaign = a_campaign(db, "Weekend specials", "Street food.")

    creator.bio = "Filter coffee every morning."
    campaign.description = "Dum biryani."
    db.flush()

    assert stored(db, Creator.bio_words, creator.id, Creator.id) == {
        "filter",
        "coffe",
        "everi",
        "morn",
    }
    assert "biryani" in stored(db, Campaign.brief_words, campaign.id, Campaign.id)
    assert "street" not in stored(db, Campaign.brief_words, campaign.id, Campaign.id)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE creator SET bio_words = to_tsvector('planted')",
        "UPDATE campaign SET brief_words = to_tsvector('planted')",
    ],
)
def test_nothing_can_write_the_words_by_hand(db, statement):
    a_creator(db, "Street food reels.")
    a_campaign(db, "Weekend specials", "Street food.")

    with (
        pytest.raises(DBAPIError, match="can only be updated to DEFAULT"),
        db.begin_nested(),
    ):
        db.execute(text(statement))


def test_an_ordinary_read_does_not_fetch_the_words(db):
    creator = a_creator(db, "Street food reels.")
    campaign = a_campaign(db, "Weekend specials", "Street food.")
    db.expire_all()

    read_creator = db.get(Creator, creator.id)
    read_campaign = db.get(Campaign, campaign.id)

    assert "bio_words" in inspect(read_creator).unloaded
    assert "brief_words" in inspect(read_campaign).unloaded
