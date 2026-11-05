"""The database's own rules for brand teams (item 13, D-148), broken with raw SQL."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.brand_team import BrandInvite, BrandMember
from tests.factories import FIXED_NOW, build_brand, create_account

HASH = "a" * 64


def _brand(db) -> uuid.UUID:
    brand = build_brand(db, email=f"team-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    return brand.id


def _member(db, brand_id, account_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "brand_id": brand_id,
        "account_id": account_id,
        "role": "campaigns",
        "first_name": "Ravi",
        "removed_at": None,
        "created_at": FIXED_NOW,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO brand_member (brand_id, account_id, role, first_name,"
            " removed_at, created_at, updated_at) VALUES (:brand_id, :account_id,"
            " :role, :first_name, :removed_at, :created_at, :created_at)"
        ),
        values,
    )


def _invite(db, brand_id, **overrides: object) -> None:
    values: dict[str, object] = {
        "brand_id": brand_id,
        "role": "finance",
        "first_name": "Meena",
        "phone_hash": HASH,
        "expires_at": FIXED_NOW + timedelta(days=7),
        "accepted_at": None,
        "accepted_by_account_id": None,
        "declined_at": None,
        "revoked_at": None,
        "created_at": FIXED_NOW,
        **overrides,
    }
    db.execute(
        text(
            "INSERT INTO brand_invite (brand_id, role, first_name, phone_hash,"
            " expires_at, accepted_at, accepted_by_account_id, declined_at,"
            " revoked_at, created_at, updated_at) VALUES (:brand_id, :role,"
            " :first_name, :phone_hash, :expires_at, :accepted_at,"
            " :accepted_by_account_id, :declined_at, :revoked_at, :created_at,"
            " :created_at)"
        ),
        values,
    )


def test_good_rows_are_kept(db):
    brand_id = _brand(db)
    account = create_account(db, "brand")

    _member(db, brand_id, account.id)
    _invite(db, brand_id)

    assert db.scalars(
        select(BrandMember.role).where(BrandMember.brand_id == brand_id)
    ).all() == ["campaigns"]
    assert db.scalars(
        select(BrandInvite.role).where(BrandInvite.brand_id == brand_id)
    ).all() == ["finance"]


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"role": "owner"}, "role_allowed"),
        ({"role": "viewer"}, "role_allowed"),
        ({"first_name": ""}, "first_name_shape"),
        ({"first_name": " Ravi"}, "first_name_shape"),
        ({"first_name": "Ravi\n+919000000001"}, "first_name_shape"),
        ({"removed_at": FIXED_NOW - timedelta(seconds=1)}, "removed_after_joined"),
    ],
)
def test_a_bad_membership_is_refused(db, overrides, constraint):
    brand_id = _brand(db)
    account = create_account(db, "brand")

    with (
        pytest.raises(IntegrityError, match=f"ck_brand_member_{constraint}"),
        db.begin_nested(),
    ):
        _member(db, brand_id, account.id, **overrides)


def test_one_live_membership_per_brand_and_person(db):
    brand_id = _brand(db)
    account = create_account(db, "brand")
    _member(db, brand_id, account.id)

    with pytest.raises(IntegrityError, match="uq_brand_member_live"), db.begin_nested():
        _member(db, brand_id, account.id, role="finance")


def test_a_removed_membership_leaves_room_to_rejoin(db):
    brand_id = _brand(db)
    account = create_account(db, "brand")
    _member(db, brand_id, account.id, removed_at=FIXED_NOW + timedelta(days=1))

    _member(db, brand_id, account.id)

    assert (
        len(
            db.scalars(
                select(BrandMember.id).where(BrandMember.brand_id == brand_id)
            ).all()
        )
        == 2
    )


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"role": "owner"}, "role_allowed"),
        ({"first_name": "Meena "}, "first_name_shape"),
        ({"phone_hash": "+919000000001"}, "phone_hash_format"),
        ({"phone_hash": "A" * 64}, "phone_hash_format"),
        ({"expires_at": FIXED_NOW}, "lifetime_within_limit"),
        (
            {"expires_at": FIXED_NOW + timedelta(days=7, seconds=1)},
            "lifetime_within_limit",
        ),
        (
            {"accepted_at": FIXED_NOW, "declined_at": FIXED_NOW},
            "ends_once",
        ),
        ({"declined_at": FIXED_NOW, "revoked_at": FIXED_NOW}, "ends_once"),
    ],
)
def test_a_bad_invite_is_refused(db, overrides, constraint):
    brand_id = _brand(db)

    with (
        pytest.raises(IntegrityError, match=f"ck_brand_invite_{constraint}"),
        db.begin_nested(),
    ):
        _invite(db, brand_id, **overrides)


def test_who_accepted_needs_the_acceptance(db):
    brand_id = _brand(db)
    account = create_account(db, "brand")

    with (
        pytest.raises(
            IntegrityError, match="ck_brand_invite_accepted_by_only_when_accepted"
        ),
        db.begin_nested(),
    ):
        _invite(db, brand_id, accepted_by_account_id=account.id)


def test_one_open_invite_per_brand_and_number(db):
    brand_id = _brand(db)
    _invite(db, brand_id)

    with pytest.raises(IntegrityError, match="uq_brand_invite_open"), db.begin_nested():
        _invite(db, brand_id, role="campaigns")


def test_an_ended_invite_leaves_room_for_a_new_one(db):
    brand_id = _brand(db)
    _invite(db, brand_id, revoked_at=FIXED_NOW)

    _invite(db, brand_id)

    assert (
        len(
            db.scalars(
                select(BrandInvite.id).where(BrandInvite.brand_id == brand_id)
            ).all()
        )
        == 2
    )


def test_a_team_goes_with_its_brand(db):
    brand_id = _brand(db)
    account = create_account(db, "brand")
    _member(db, brand_id, account.id)
    _invite(db, brand_id)

    db.execute(text("DELETE FROM brand WHERE id = :id"), {"id": brand_id})

    assert (
        db.scalars(select(BrandMember.id).where(BrandMember.brand_id == brand_id)).all()
        == []
    )
    assert (
        db.scalars(select(BrandInvite.id).where(BrandInvite.brand_id == brand_id)).all()
        == []
    )
