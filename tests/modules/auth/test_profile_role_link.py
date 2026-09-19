"""A profile may only belong to an account of its own role (D-014)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from tests.factories import build_brand, build_creator, create_account, fake_phone


def assert_rejected_by(db, row, constraint_name: str) -> None:
    db.add(row)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def test_profiles_record_their_account_role(db):
    brand, creator = build_brand(db), build_creator(db)
    db.add_all([brand, creator])
    db.flush()
    db.refresh(brand)
    db.refresh(creator)

    assert brand.account_role == "brand"
    assert creator.account_role == "creator"


def test_brand_profile_cannot_belong_to_a_creator_account(db):
    creator_account = create_account(db, "creator")

    assert_rejected_by(
        db,
        build_brand(db, account_id=creator_account.id),
        "fk_brand_account_id_account",
    )


def test_creator_profile_cannot_belong_to_a_brand_account(db):
    brand_account = create_account(db, "brand")

    assert_rejected_by(
        db,
        build_creator(db, account_id=brand_account.id),
        "fk_creator_account_id_account",
    )


def test_one_account_cannot_own_both_profiles(db):
    brand = build_brand(db)
    db.add(brand)
    db.flush()

    assert_rejected_by(
        db,
        build_creator(db, account_id=brand.account_id),
        "fk_creator_account_id_account",
    )


@pytest.mark.parametrize(
    ("build_profile", "wrong_role", "constraint_name"),
    [
        (build_brand, "creator", "ck_brand_account_role_fixed"),
        (build_creator, "brand", "ck_creator_account_role_fixed"),
    ],
)
def test_account_role_column_cannot_be_set_to_the_other_role(
    db, build_profile, wrong_role, constraint_name
):
    assert_rejected_by(db, build_profile(db, account_role=wrong_role), constraint_name)


@pytest.mark.parametrize("build_profile", [build_brand, build_creator])
def test_account_role_cannot_change_while_a_profile_exists(db, build_profile):
    profile = build_profile(db)
    db.add(profile)
    db.flush()
    account = db.get(Account, profile.account_id)
    other_role = "creator" if account.role == "brand" else "brand"

    account.role = other_role
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert "account_id_account" in str(exc_info.value)


def test_account_role_can_change_when_no_profile_exists(db):
    account = create_account(db, "brand")

    account.role = "creator"
    db.flush()

    assert db.get(Account, account.id).role == "creator"


def test_a_raw_insert_cannot_bypass_the_pairing(db):
    """Even SQL that skips the models is refused (the point of D-014)."""
    creator_account = create_account(db, "creator")

    with pytest.raises(IntegrityError) as exc_info:
        db.execute(
            text(
                "INSERT INTO brand (account_id, account_role, name, email) "
                "VALUES (:account_id, 'brand', 'Sneaky', 'sneaky@example.com')"
            ),
            {"account_id": creator_account.id},
        )
    assert "fk_brand_account_id_account" in str(exc_info.value)


def test_valid_profiles_still_save(db):
    brand, creator = build_brand(db), build_creator(db)
    db.add_all([brand, creator])
    db.flush()

    assert db.get(Brand, brand.id) is brand
    assert db.get(Creator, creator.id) is creator


def test_deleting_an_account_with_a_profile_is_still_refused(db):
    brand = build_brand(db)
    db.add(brand)
    db.flush()
    account = db.get(Account, brand.account_id)

    db.delete(account)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert "fk_brand_account_id_account" in str(exc_info.value)


def test_unknown_account_is_still_refused(db):
    import uuid

    assert_rejected_by(
        db,
        build_creator(db, account_id=uuid.uuid4()),
        "fk_creator_account_id_account",
    )


def test_phone_stays_unique_per_account(db):
    phone = fake_phone()
    create_account(db, "brand", phone=phone)

    assert_rejected_by(db, Account(phone=phone, role="creator"), "uq_account_phone")
