import pytest
from sqlalchemy.exc import DataError, IntegrityError

from app.modules.auth.models.creator import Creator
from tests.factories import build_creator


def assert_rejected_by(db, creator: Creator, constraint_name: str) -> None:
    db.add(creator)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def test_valid_creator_is_saved_with_generated_fields(db):
    db.add(build_creator(db))
    db.flush()

    fetched = db.query(Creator).filter_by(handle="priya.eats").one()
    assert fetched.display_name == "Priya Eats"
    assert fetched.niches == ["food", "travel"]
    assert fetched.languages == ["en"]
    assert fetched.id is not None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_creator_without_bio_is_saved(db):
    db.add(build_creator(db, bio=None))
    db.flush()

    assert db.query(Creator).filter_by(handle="priya.eats").one().bio is None


def test_duplicate_handle_is_rejected(db):
    db.add(build_creator(db))
    db.flush()

    assert_rejected_by(
        db, build_creator(db, display_name="Someone Else"), "uq_creator_handle"
    )


@pytest.mark.parametrize(
    "handle",
    ["Priya.Eats", "pr", "priya eats", "priya-eats", "priya@eats"],
)
def test_badly_formatted_handle_is_rejected(db, handle):
    assert_rejected_by(db, build_creator(db, handle=handle), "ck_creator_handle_format")


def test_handle_over_30_characters_is_rejected(db):
    # VARCHAR(30) rejects this before the format check runs.
    db.add(build_creator(db, handle="a" * 31))
    with pytest.raises(DataError) as exc_info:
        db.flush()
    assert "value too long" in str(exc_info.value)


@pytest.mark.parametrize(
    "niches",
    [[], ["food", "fashion", "beauty", "tech", "travel", "fitness"]],
)
def test_niche_count_outside_one_to_five_is_rejected(db, niches):
    assert_rejected_by(db, build_creator(db, niches=niches), "ck_creator_niches_count")


def test_five_niches_is_allowed(db):
    db.add(build_creator(db, niches=["food", "fashion", "beauty", "tech", "travel"]))
    db.flush()


def test_unknown_niche_is_rejected(db):
    assert_rejected_by(
        db, build_creator(db, niches=["food", "gaming"]), "ck_creator_niches_allowed"
    )


def test_empty_languages_is_rejected(db):
    assert_rejected_by(db, build_creator(db, languages=[]), "ck_creator_languages_count")


def test_language_other_than_english_is_rejected(db):
    assert_rejected_by(
        db, build_creator(db, languages=["en", "ta"]), "ck_creator_languages_allowed"
    )


@pytest.mark.parametrize("display_name", ["", "   "])
def test_blank_display_name_is_rejected(db, display_name):
    assert_rejected_by(
        db,
        build_creator(db, display_name=display_name),
        "ck_creator_display_name_not_blank",
    )


def test_blank_city_is_rejected(db):
    assert_rejected_by(db, build_creator(db, city="  "), "ck_creator_city_not_blank")


def test_bio_of_500_characters_is_allowed(db):
    db.add(build_creator(db, bio="x" * 500))
    db.flush()


def test_bio_over_500_characters_is_rejected(db):
    assert_rejected_by(db, build_creator(db, bio="x" * 501), "ck_creator_bio_length")


def test_creator_without_account_is_rejected(db):
    assert_rejected_by(db, build_creator(db, account_id=None), "account_id")


def test_two_creators_cannot_share_an_account(db):
    first = build_creator(db)
    db.add(first)
    db.flush()

    assert_rejected_by(
        db,
        build_creator(db, handle="second.creator", account_id=first.account_id),
        "uq_creator_account_id",
    )
