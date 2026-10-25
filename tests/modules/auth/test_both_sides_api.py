"""One number, both sides (item 8, D-126), through the API.

A brand and a creator account may share a number, each exactly as before.
Signing in as the other side starts it; an admin's number, a suspended
side, or a side waiting to move refuses that. The two never deal with each
other. Everything that belongs to the number covers both: a phone change
moves both, a lost-number change is cancelled by either, a deletion takes
one and leaves the number's codes for the other. Two first logins at once
are in test_both_sides_concurrency.py.
"""

import uuid
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.main import app
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.passkey import Passkey, PasskeyReset
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.me import account_deletion_service as deletions
from app.modules.me import passkey_service
from app.modules.me import phone_change_service as phone_changes
from app.modules.notifications.models import Notification
from tests.deal_flow import CAMPAIGNS_URL, PITCH, User, brand_user
from tests.factories import build_creator, unique_test_phone
from tests.step_up import STEP_UP_URL

OTP_REQUEST_URL = "/api/v1/auth/otp/request"
OTP_VERIFY_URL = "/api/v1/auth/otp/verify"
ME_URL = "/api/v1/auth/me"
PHONE_CHANGE_URL = "/api/v1/me/phone-change"
LOST_URL = "/api/v1/me/phone-change/without-current-number"


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


def code_for(client, sender, phone: str) -> str:
    response = client.post(OTP_REQUEST_URL, json={"phone": phone})
    assert response.status_code == 202, response.text
    code = sender.last_code_for(phone)
    assert code is not None
    return code


def sign_in(client, sender, phone: str, role: str):
    return client.post(
        OTP_VERIFY_URL,
        json={"phone": phone, "code": code_for(client, sender, phone), "role": role},
    )


def phone_of(db, user: User) -> str:
    return db.scalars(
        select(Account.phone)
        .where(Account.id == user.account_id)
        .execution_options(populate_existing=True)
    ).one()


@pytest.fixture
def both(db, clock) -> tuple[User, User]:
    """A brand and a creator account on one number, with their profiles."""
    brand = brand_user(db, clock)
    phone = phone_of(db, brand)
    creator_account = Account(phone=phone, role="creator")
    db.add(creator_account)
    db.flush()
    db.add(
        build_creator(
            db, account_id=creator_account.id, handle=f"bs{uuid.uuid4().hex[:12]}"
        )
    )
    db.commit()
    return brand, User(creator_account.id, "creator", clock)


def accounts_on(db, phone: str) -> list[Account]:
    return list(
        db.scalars(
            select(Account)
            .where(Account.phone == phone)
            .order_by(Account.role)
            .execution_options(populate_existing=True)
        ).all()
    )


# --- signing in as the other side -------------------------------------------------------


def test_signing_in_as_the_other_side_starts_it(client, db, clock, sender):
    brand = brand_user(db, clock)
    db.commit()
    phone = phone_of(db, brand)

    response = sign_in(client, sender, phone, "creator")

    assert response.status_code == 200, response.text
    assert [a.role for a in accounts_on(db, phone)] == ["brand", "creator"]
    creator_id = next(a.id for a in accounts_on(db, phone) if a.role == "creator")
    assert creator_id != brand.account_id


def test_each_side_signs_in_to_its_own_account(client, db, clock, sender, both):
    brand, creator = both
    phone = phone_of(db, brand)

    as_brand = sign_in(client, sender, phone, "brand").json()
    # A moment later, as a person's second code always is: the latest code
    # counts, and two in one instant would tie.
    clock.advance(timedelta(minutes=1))
    as_creator = sign_in(client, sender, phone, "creator").json()

    for tokens, user in ((as_brand, brand), (as_creator, creator)):
        me = client.get(
            ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert me.json()["id"] == str(user.account_id)


def test_each_side_is_told_of_the_other(client, db, both):
    brand, creator = both

    assert client.get(ME_URL, headers=brand.headers).json()["other_side"] == "creator"
    assert client.get(ME_URL, headers=creator.headers).json()["other_side"] == "brand"


def test_a_lone_account_has_no_other_side(client, db, clock):
    brand = brand_user(db, clock)
    db.commit()

    assert client.get(ME_URL, headers=brand.headers).json()["other_side"] is None


def test_an_admin_has_no_other_side(client, db, clock):
    from tests.factories import create_account

    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()

    assert client.get(ME_URL, headers=admin.headers).json()["other_side"] is None


def test_a_suspended_side_cannot_be_stepped_round(client, db, clock, sender):
    brand = brand_user(db, clock)
    account = db.get_one(Account, brand.account_id)
    account.suspended_at = clock.now
    account.suspension_reason = "fake_profile"
    db.commit()

    response = sign_in(client, sender, phone_of(db, brand), "creator")

    assert response.status_code == 403
    assert response.json()["code"] == "account_suspended"
    assert len(accounts_on(db, phone_of(db, brand))) == 1


def test_a_side_waiting_to_move_takes_no_second_side(client, db, clock, sender):
    """Else the change would carry the new account to the owner's new number."""
    brand = brand_user(db, clock)
    db.commit()
    phone = phone_of(db, brand)
    asked = client.post(
        LOST_URL,
        json={
            "new_phone": (new := unique_test_phone()),
            "new_phone_code": code_for(client, sender, new),
        },
        headers=brand.headers,
    )
    assert asked.status_code == 202, asked.text

    response = sign_in(client, sender, phone, "creator")

    assert response.status_code == 409
    assert response.json()["code"] == "phone_change_waiting"


# --- the two sides never deal ------------------------------------------------------------


def open_campaign(client, brand: User) -> str:
    campaign_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Pongal sweets launch",
            "description": "Reels featuring our new sweet box.",
            "campaign_type": "paid",
            "budget_min_paise": 300_000,
            "budget_max_paise": 900_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "2 Instagram reels",
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    return str(campaign_id)


def test_a_creator_cannot_apply_to_their_own_brands_campaign(client, both):
    brand, creator = both
    campaign_id = open_campaign(client, brand)

    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "campaign_not_found"


def test_a_brand_cannot_invite_its_own_creator_side(client, db, both):
    brand, creator = both
    campaign_id = open_campaign(client, brand)
    creator_id = db.scalars(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    ).one()

    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/invitations",
        json={"creator_id": str(creator_id)},
        headers=brand.headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "creator_not_found"


# --- what belongs to the number covers both --------------------------------------------------


def test_a_phone_change_moves_both_sides_and_ends_both_sides_sessions(
    client, db, clock, sender, both
):
    brand, creator = both
    old = phone_of(db, brand)
    new = unique_test_phone()
    step = client.post(
        STEP_UP_URL,
        json={"action": "change_phone", "new_phone": new},
        headers=brand.headers,
    )
    assert step.status_code == 202, step.text
    current_code = sender.last_code_for(old)
    asked = client.post(
        PHONE_CHANGE_URL,
        json={"new_phone": new, "new_phone_code": code_for(client, sender, new)},
        headers={**brand.headers, "Step-Up-Code": current_code},
    )
    assert asked.status_code == 202, asked.text
    clock.advance(timedelta(hours=73))

    run = phone_changes.run_changes(lambda: nullcontext(db), clock.now)

    assert run.made == 1
    assert [a.role for a in accounts_on(db, new)] == ["brand", "creator"]
    assert accounts_on(db, old) == []
    for user in (brand, creator):
        told = db.scalars(
            select(Notification.id).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == "phone_changed",
            )
        ).all()
        assert len(told) == 1


def test_one_number_waits_for_one_change(client, db, sender, both):
    brand, creator = both
    first = client.post(
        LOST_URL,
        json={
            "new_phone": (new := unique_test_phone()),
            "new_phone_code": code_for(client, sender, new),
        },
        headers=brand.headers,
    )
    assert first.status_code == 202, first.text

    second = client.post(
        LOST_URL,
        json={
            "new_phone": (other := unique_test_phone()),
            "new_phone_code": code_for(client, sender, other),
        },
        headers=creator.headers,
    )

    assert second.status_code == 409
    assert second.json()["code"] == "phone_change_on_other_side"


def test_no_change_while_a_deletion_waits_on_the_number(client, db, clock, sender, both):
    brand, creator = both
    account = db.get_one(Account, creator.account_id)
    account.deletion_requested_at = clock.now
    account.deletion_takes_effect_at = clock.now + timedelta(days=30)
    db.commit()

    response = client.post(
        LOST_URL,
        json={
            "new_phone": (new := unique_test_phone()),
            "new_phone_code": code_for(client, sender, new),
        },
        headers=brand.headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "deletion_waiting"


def test_signing_in_to_either_side_cancels_a_lost_number_change(
    client, db, clock, sender, both
):
    """The number was not lost: its other side just used it (D-110, D-126)."""
    brand, _creator = both
    phone = phone_of(db, brand)
    asked = client.post(
        LOST_URL,
        json={
            "new_phone": (new := unique_test_phone()),
            "new_phone_code": code_for(client, sender, new),
        },
        headers=brand.headers,
    )
    assert asked.status_code == 202, asked.text
    clock.advance(timedelta(minutes=5))

    assert sign_in(client, sender, phone, "creator").status_code == 200
    run = phone_changes.run_changes(lambda: nullcontext(db), clock.now)

    assert run.voided == 1
    assert phone_of(db, brand) == phone


def test_deleting_one_side_leaves_the_other_and_the_numbers_codes(
    client, db, clock, sender, both
):
    brand, creator = both
    phone = phone_of(db, brand)
    code_for(client, sender, phone)
    account = db.get_one(Account, brand.account_id)
    account.deletion_requested_at = clock.now - timedelta(days=31)
    account.deletion_takes_effect_at = account.deletion_requested_at + timedelta(days=30)
    db.commit()

    assert deletions.erase(db, brand.account_id, clock.now) == "erased"

    assert [a.id for a in accounts_on(db, phone)] == [creator.account_id]
    assert db.scalars(select(OtpChallenge.id).where(OtpChallenge.phone == phone)).all()
    clock.advance(timedelta(minutes=1))
    assert sign_in(client, sender, phone, "creator").status_code == 200


def test_a_lost_phone_resets_both_sides_passkeys(db, clock, both):
    """One phone lost loses both sides' keys, so one reset covers both."""
    from app.modules.auth.service import request_otp

    brand, creator = both
    phone = phone_of(db, brand)
    for user in (brand, creator):
        db.add(
            Passkey(
                account_id=user.account_id,
                credential_id=uuid.uuid4().bytes + uuid.uuid4().bytes,
                public_key=b"k" * 64,
                sign_count=0,
                aaguid=uuid.uuid4(),
                backup_eligible=False,
                backup_state=False,
                name="Phone",
            )
        )
    db.commit()
    pending = request_otp(db, phone, clock.now)

    passkey_service.request_reset(db, phone, pending.code, clock.now)

    resets = db.scalars(
        select(PasskeyReset.account_id).where(
            PasskeyReset.account_id.in_([brand.account_id, creator.account_id])
        )
    ).all()
    assert sorted(resets) == sorted([brand.account_id, creator.account_id])
