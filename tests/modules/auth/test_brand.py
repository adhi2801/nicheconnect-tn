import pytest
from sqlalchemy.exc import DataError, IntegrityError

from app.modules.auth.models.brand import Brand
from tests.factories import build_brand


def assert_rejected_by(db, brand: Brand, constraint_name: str) -> None:
    db.add(brand)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def assert_too_long(db, brand: Brand) -> None:
    db.add(brand)
    with pytest.raises(DataError) as exc_info:
        db.flush()
    assert "value too long" in str(exc_info.value)


def test_create_and_query_brand(db):
    db.add(build_brand(db))
    db.flush()

    fetched = db.query(Brand).filter_by(email="acme@example.com").one()
    assert fetched.name == "Acme"
    assert fetched.id is not None
    assert fetched.account_id is not None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_duplicate_email_raises_integrity_error(db):
    db.add(build_brand(db, name="First", email="dup@example.com"))
    db.flush()

    assert_rejected_by(
        db, build_brand(db, name="Second", email="dup@example.com"), "uq_brand_email"
    )


def test_email_with_capital_letters_is_rejected(db):
    assert_rejected_by(
        db, build_brand(db, email="Acme@Example.com"), "ck_brand_email_lowercase"
    )


def test_same_email_in_different_case_cannot_be_stored_twice(db):
    db.add(build_brand(db, name="First", email="case@example.com"))
    db.flush()

    assert_rejected_by(
        db,
        build_brand(db, name="Second", email="CASE@example.com"),
        "ck_brand_email_lowercase",
    )


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_is_rejected(db, name):
    assert_rejected_by(db, build_brand(db, name=name), "ck_brand_name_not_blank")


def test_name_of_150_characters_is_allowed(db):
    db.add(build_brand(db, name="n" * 150))
    db.flush()


def test_name_over_150_characters_is_rejected(db):
    assert_too_long(db, build_brand(db, name="n" * 151))


def test_email_of_320_characters_is_allowed(db):
    email = "a" * 308 + "@example.com"
    assert len(email) == 320
    db.add(build_brand(db, email=email))
    db.flush()


def test_email_over_320_characters_is_rejected(db):
    assert_too_long(db, build_brand(db, email="a" * 309 + "@example.com"))


def test_brand_without_account_is_rejected(db):
    assert_rejected_by(db, build_brand(db, account_id=None), "account_id")


def test_two_brands_cannot_share_an_account(db):
    first = build_brand(db, email="first@example.com")
    db.add(first)
    db.flush()

    assert_rejected_by(
        db,
        build_brand(db, email="second@example.com", account_id=first.account_id),
        "uq_brand_account_id",
    )
