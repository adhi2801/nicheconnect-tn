import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.account import Account
from tests.factories import build_brand, build_creator, create_account, fake_phone


def assert_rejected_by(db, account: Account, constraint_name: str) -> None:
    db.add(account)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_valid_account_is_saved_with_generated_fields(db, role):
    phone = fake_phone()
    create_account(db, role, phone=phone)

    fetched = db.query(Account).filter_by(phone=phone).one()
    assert fetched.role == role
    assert fetched.id is not None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_duplicate_phone_is_rejected(db):
    phone = fake_phone()
    create_account(db, "brand", phone=phone)

    assert_rejected_by(db, Account(phone=phone, role="creator"), "uq_account_phone")


@pytest.mark.parametrize(
    "phone",
    [
        "9876543210",  # missing +91
        "919876543210",  # missing +
        "+915876543210",  # Indian mobiles start 6-9
        "+14155550123",  # not Indian
        "+91987654321",  # 9 digits
        "+9198765432100",  # 11 digits
        "+91 9876543210",  # space
    ],
)
def test_badly_formatted_phone_is_rejected(db, phone):
    assert_rejected_by(
        db, Account(phone=phone, role="creator"), "ck_account_phone_format"
    )


@pytest.mark.parametrize("role", ["admin", "Brand", ""])
def test_unknown_role_is_rejected(db, role):
    assert_rejected_by(
        db, Account(phone=fake_phone(), role=role), "ck_account_role_allowed"
    )


@pytest.mark.parametrize(
    ("build_profile", "constraint_name"),
    [
        (build_brand, "fk_brand_account_id_account"),
        (build_creator, "fk_creator_account_id_account"),
    ],
)
def test_account_with_profile_cannot_be_deleted(db, build_profile, constraint_name):
    profile = build_profile(db)
    db.add(profile)
    db.flush()
    account = db.get(Account, profile.account_id)

    db.delete(account)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def test_account_without_profile_can_be_deleted(db):
    account = create_account(db, "creator")

    db.delete(account)
    db.flush()

    assert db.get(Account, account.id) is None
