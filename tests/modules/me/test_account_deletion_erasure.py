"""Erasing an account once its 30 days are over (item 6, D-122).

The strongest test here fills every table the registry says is erased, for
the person leaving and for a bystander, runs the job, and counts: nothing of
the person's is left, and nothing of the bystander's is touched. Then what
the emptied rows still say, who can still reach them, what the other side
keeps, and what holds or waits an erasure.
"""

import hashlib
import secrets
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.storage import memory_store
from app.db.base import Base
from app.main import app
from app.modules.auth.erasure import (
    LEFT_BRAND_NAME,
    LEFT_CREATOR_NAME,
    LEFT_EMAIL_DOMAIN,
    LEFT_HANDLE_PREFIX,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import AccountPhoneChange
from app.modules.auth.models.agent_token import AgentToken
from app.modules.auth.models.attribution import AccountAttribution, InviteCode
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import HANDLE_PATTERN, Creator
from app.modules.auth.models.device_token import DeviceToken
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.passkey import Passkey, PasskeyChallenge, PasskeyReset
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.auth.models.totp_factor import TotpFactor
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.campaigns.alert_models import CampaignAlert
from app.modules.campaigns.models import Application, Campaign
from app.modules.matching.creator_list_models import CreatorList, CreatorListEntry
from app.modules.matching.models import EMBEDDING_DIMENSIONS, CreatorEmbedding
from app.modules.me import account_deletion_service as service
from app.modules.me.account_deletion_registry import ERASED
from app.modules.me.export_models import DataExport, object_key
from app.modules.notifications.models import Notification
from app.modules.notifications.preference_models import (
    URGENT_TYPES,
    NotificationPreference,
)
from app.modules.payment_status.upi_change_models import CreatorUpiChange
from app.modules.payment_status.upi_models import CreatorUpi
from app.modules.profiles.brand_domain_models import BrandDomain
from app.modules.profiles.connection_models import ConnectedAccount, ConnectionAttempt
from app.modules.profiles.models import CreatorChannel, CreatorPackage
from app.modules.safety.models import AccountBlock
from tests.deal_flow import (
    CAMPAIGNS_URL,
    MEMOS_URL,
    PITCH,
    Clock,
    User,
    accepted_memo,
    brand_user,
    creator_user,
    finish_deal,
)
from tests.factories import build_campaign, create_account, fake_token_hash

WAIT = timedelta(days=30)
# The columns by which a row belongs to an account, its profile or its number.
OWNER_COLUMNS = (
    "account_id",
    "blocker_account_id",
    "blocked_account_id",
    "creator_id",
    "brand_id",
    "phone",
)


@dataclass
class Person:
    user: User
    account_id: uuid.UUID
    profile_id: uuid.UUID
    phone: str


def person(db: Session, user: User) -> Person:
    account = db.get_one(Account, user.account_id)
    model = Brand if user.role == "brand" else Creator
    profile_id = db.scalars(select(model.id).where(model.account_id == account.id)).one()
    assert account.phone is not None
    return Person(user, account.id, profile_id, account.phone)


def hex64() -> str:
    return hashlib.sha256(secrets.token_bytes(16)).hexdigest()


def fill(db: Session, who: Person, other: Person, clock: Clock) -> set[str]:
    """One row or more in every erased table this kind of account can have."""
    now = clock.now
    account_id = who.account_id
    db.add_all(
        [
            AuthSession(
                account_id=account_id,
                family_id=uuid.uuid4(),
                token_hash=fake_token_hash(),
                expires_at=now + timedelta(days=30),
            ),
            AgentToken(
                account_id=account_id,
                name="Claude",
                token_hash=hex64(),
                scopes=["deals:read"],
                expires_at=now + timedelta(days=30),
                created_at=now,
                updated_at=now,
            ),
            DeviceToken(
                account_id=account_id,
                platform="android",
                token=secrets.token_hex(24),
                last_seen_at=now,
            ),
            Passkey(
                account_id=account_id,
                credential_id=secrets.token_bytes(32),
                public_key=secrets.token_bytes(64),
                sign_count=0,
                aaguid=uuid.uuid4(),
                backup_eligible=False,
                backup_state=False,
                name="Phone",
            ),
            PasskeyChallenge(
                account_id=account_id,
                purpose="register",
                challenge=secrets.token_bytes(32),
                created_at=now,
                expires_at=now + timedelta(minutes=5),
            ),
            PasskeyReset(
                account_id=account_id,
                requested_at=now,
                takes_effect_at=now + timedelta(days=7),
            ),
            StepUpChallenge(
                account_id=account_id,
                action="log_out_everywhere",
                value_hash=hex64(),
                code_hash=hex64(),
                created_at=now,
                expires_at=now + timedelta(minutes=5),
            ),
            OtpChallenge(
                phone=who.phone, code_hash=hex64(), expires_at=now + timedelta(minutes=5)
            ),
            AccountPhoneChange(
                account_id=account_id,
                new_phone=f"+9188{uuid.uuid4().int % 10**8:08d}",
                requested_at=now,
                takes_effect_at=now + timedelta(hours=72),
            ),
            TotpFactor(
                account_id=account_id,
                ticket_hash=hex64(),
                ticket_expires_at=now + timedelta(minutes=15),
            ),
            AccountAttribution(account_id=account_id, source="instagram"),
            InviteCode(
                account_id=account_id,
                code="".join(
                    secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8)
                ),
            ),
            Notification(account_id=account_id, notification_type="session_ended"),
            NotificationPreference(account_id=account_id),
            # Blocks both ways: one made by the person, one of them.
            AccountBlock(
                blocker_account_id=account_id, blocked_account_id=other.account_id
            ),
            ConnectionAttempt(
                account_id=account_id,
                platform="youtube",
                state_sha256=hex64(),
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            ),
            DataExport(
                account_id=account_id,
                requested_at=now - timedelta(days=2),
                ready_at=now - timedelta(days=2),
                expires_at=now - timedelta(days=1),
                size_bytes=10,
                file_deleted_at=now - timedelta(days=1),
            ),
        ]
    )
    db.flush()
    db.add(
        AccountBlock(blocker_account_id=other.account_id, blocked_account_id=account_id)
    )
    tables = {
        "auth_session",
        "agent_token",
        "device_token",
        "passkey",
        "passkey_challenge",
        "passkey_reset",
        "step_up_challenge",
        "otp_challenge",
        "account_phone_change",
        "totp_factor",
        "account_attribution",
        "invite_code",
        "notification",
        "notification_preference",
        "account_block",
        "data_export",
        "connection_attempt",
    }
    if who.user.role == "creator":
        channel = CreatorChannel(
            creator_id=who.profile_id,
            platform="instagram",
            profile_url=f"https://www.instagram.com/{uuid.uuid4().hex[:10]}",
            followers=1200,
            figures_as_of=now.date(),
        )
        db.add(channel)
        db.flush()
        db.add_all(
            [
                CreatorPackage(
                    creator_id=who.profile_id,
                    platform="instagram",
                    format="reel",
                    title="One reel",
                    price_paise=500_000,
                    delivery_days=7,
                    position=0,
                ),
                CreatorUpi(
                    creator_id=who.profile_id,
                    upi_id=f"left{uuid.uuid4().hex[:8]}@okaxis",
                    consented_at=now,
                    notice_version="v1",
                ),
                CreatorUpiChange(
                    creator_id=who.profile_id,
                    upi_id=f"new{uuid.uuid4().hex[:8]}@okaxis",
                    consented_at=now,
                    notice_version="v1",
                    usable_at=now + timedelta(hours=24),
                ),
                CreatorEmbedding(
                    creator_id=who.profile_id,
                    embedding=[0.0] * EMBEDDING_DIMENSIONS,
                    source_hash=hex64(),
                    model="test",
                ),
            ]
        )
        # On the other side's list: the line goes, the brand's list stays.
        kept = CreatorList(brand_id=other.profile_id, name=f"Kept {uuid.uuid4().hex[:8]}")
        db.add(kept)
        db.flush()
        db.add(CreatorListEntry(list_id=kept.id, creator_id=who.profile_id))
        db.add(CampaignAlert(creator_id=who.profile_id, niche="food"))
        db.add(
            ConnectedAccount(
                creator_id=who.profile_id,
                platform="instagram",
                platform_user_id=str(uuid.uuid4().int)[:16],
                handle="leaving.creator",
                access_token_sealed=b"sealed",
                notice_version="v1",
                connected_at=now,
            )
        )
        tables |= {
            "creator_channel",
            "creator_package",
            "creator_upi",
            "creator_upi_change",
            "creator_embedding",
            "creator_list_entry",
            "campaign_alert",
            "connected_account",
        }
    else:
        db.add(
            BrandDomain(
                brand_id=who.profile_id,
                domain=f"left{uuid.uuid4().hex[:8]}.in",
                token="".join(
                    secrets.choice("abcdefghijklmnopqrstuvwxyz234567") for _ in range(26)
                ),
                claimed_at=now,
                token_expires_at=now + timedelta(days=7),
            )
        )
        # The brand's own list, and its line about a creator who stays.
        saved = CreatorList(brand_id=who.profile_id, name="Diwali food creators")
        db.add(saved)
        db.flush()
        db.add(CreatorListEntry(list_id=saved.id, creator_id=other.profile_id))
        tables |= {"brand_domain", "creator_list"}
    db.flush()
    return tables


def rows_of(db: Session, table: str, who: Person) -> int:
    """How many of the table's rows belong to the person, by any owner column."""
    columns = Base.metadata.tables[table].columns
    values = {
        "account_id": who.account_id,
        "blocker_account_id": who.account_id,
        "blocked_account_id": who.account_id,
        "creator_id": who.profile_id,
        "brand_id": who.profile_id,
        "phone": who.phone,
    }
    conditions = [
        columns[name] == values[name] for name in OWNER_COLUMNS if name in columns
    ]
    assert conditions, f"{table} has no column tying a row to a person"
    return db.scalar(
        select(func.count())
        .select_from(Base.metadata.tables[table])
        .where(or_(*conditions))
    )


def due(db: Session, who: Person, clock: Clock) -> None:
    """Asked for 30 days and a moment ago."""
    account = db.get_one(Account, who.account_id)
    account.deletion_requested_at = clock.now - WAIT - timedelta(minutes=1)
    account.deletion_takes_effect_at = account.deletion_requested_at + WAIT
    db.commit()


def run(db: Session, clock: Clock, store=None) -> service.DeletionRun:
    return service.run_deletions(
        lambda: nullcontext(db), store or memory_store(), clock.now
    )


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    db.commit()
    return user


@pytest.fixture
def brand(db, clock) -> User:
    user = brand_user(db, clock)
    db.commit()
    return user


@pytest.fixture
def bystanders(db, clock) -> tuple[User, User]:
    """A brand and a creator who are not leaving, with rows of their own."""
    others = (brand_user(db, clock), creator_user(db, clock))
    db.commit()
    return others


# --- every erased table, emptied for the person only ------------------------------


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_every_erased_table_is_emptied_for_the_person_only(
    db, clock, brand, creator, bystanders, role
):
    leaving = person(db, brand if role == "brand" else creator)
    staying = person(db, bystanders[0] if role == "brand" else bystanders[1])
    neither = person(db, creator if role == "brand" else brand)
    filled = fill(db, leaving, neither, clock)
    fill(db, staying, neither, clock)
    db.commit()
    before = {table: rows_of(db, table, staying) for table in filled}
    # The fill reached every table it names, so a count of zero means erased.
    assert all(rows_of(db, table, leaving) >= 1 for table in filled)

    assert run(db, clock).erased == 0  # not due yet
    due(db, leaving, clock)
    assert run(db, clock).erased == 1

    assert {table: rows_of(db, table, leaving) for table in filled} == dict.fromkeys(
        filled, 0
    )
    # The bystander's own rows, blocks included, are all still there.
    assert {table: rows_of(db, table, staying) for table in filled} == before


def test_the_fills_cover_every_erased_table(db, clock, brand, creator, bystanders):
    """Between them, the two fills above reach every table the registry erases."""
    # Each beside one of the other side: a list of a brand's, about a creator.
    filled = fill(db, person(db, brand), person(db, bystanders[1]), clock) | fill(
        db, person(db, creator), person(db, bystanders[0]), clock
    )

    assert filled == ERASED


# --- what the emptied rows say ------------------------------------------------------


def test_a_creator_is_emptied_of_what_identifies_them(db, clock, creator):
    account = db.get_one(Account, creator.account_id)
    profile = db.scalars(select(Creator).where(Creator.account_id == account.id)).one()
    profile.passport_published_at = clock.now - timedelta(days=90)
    profile.rate_card_public_at = clock.now - timedelta(days=90)
    profile.booked_until = clock.now.date() + timedelta(days=60)
    city, niches = profile.city, list(profile.niches)
    who = person(db, creator)
    due(db, who, clock)

    run(db, clock)

    db.refresh(account)
    db.refresh(profile)
    assert account.phone is None
    assert account.deleted_at == clock.now
    assert account.passkey_only is False
    assert account.deletion_requested_at is not None  # kept as its history
    assert profile.display_name == LEFT_CREATOR_NAME
    assert profile.handle.startswith(LEFT_HANDLE_PREFIX)
    assert db.scalar(select(text(f"'{profile.handle}' ~ '{HANDLE_PATTERN}'")))
    assert profile.bio is None
    assert profile.passport_published_at is None
    assert profile.rate_card_public_at is None
    assert profile.booked_until is None
    # Deal facts, gone from search and the figures with the account.
    assert (profile.city, profile.niches) == (city, niches)


def test_a_brand_is_emptied_of_what_identifies_it(db, clock, brand):
    who = person(db, brand)
    profile = db.get_one(Brand, who.profile_id)
    profile.name_cleared = profile.name
    profile.name_cleared_at = clock.now
    due(db, who, clock)

    run(db, clock)

    db.refresh(profile)
    assert profile.name == LEFT_BRAND_NAME
    assert profile.email.endswith("@" + LEFT_EMAIL_DOMAIN)
    assert profile.name_cleared is None
    assert profile.name_cleared_at is None


def test_two_who_leave_get_different_placeholders(db, clock):
    users = [
        creator_user(db, clock),
        creator_user(db, clock),
        brand_user(db, clock),
        brand_user(db, clock),
    ]
    db.commit()
    for user in users:
        due(db, person(db, user), clock)

    assert run(db, clock).erased == 4

    handles = db.scalars(
        select(Creator.handle).where(
            Creator.account_id.in_([u.account_id for u in users[:2]])
        )
    ).all()
    emails = db.scalars(
        select(Brand.email).where(Brand.account_id.in_([u.account_id for u in users[2:]]))
    ).all()
    assert len(set(handles)) == len(set(emails)) == 2


# --- who can still reach it -----------------------------------------------------------


def test_its_tokens_are_refused_at_once(client, db, clock, creator):
    due(db, person(db, creator), clock)
    run(db, clock)

    response = client.get("/api/v1/auth/me", headers=creator.headers)

    assert response.status_code == 401


def test_its_number_makes_a_new_account(client, db, clock, creator):
    who = person(db, creator)
    due(db, who, clock)
    run(db, clock)
    sender = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: sender

    client.post("/api/v1/auth/otp/request", json={"phone": who.phone})
    response = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "phone": who.phone,
            "code": sender.last_code_for(who.phone),
            "role": "creator",
        },
    )

    assert response.status_code == 200, response.text
    new_account = db.scalars(select(Account).where(Account.phone == who.phone)).one()
    assert new_account.id != who.account_id
    assert new_account.deleted_at is None


def test_a_creator_who_left_leaves_search_and_the_passport(
    client, db, clock, brand, creator
):
    profile = db.scalars(
        select(Creator).where(Creator.account_id == creator.account_id)
    ).one()
    profile.passport_published_at = clock.now - timedelta(days=10)
    handle = profile.handle
    db.commit()
    before = client.get(
        "/api/v1/creators", params={"q": handle}, headers=brand.headers
    ).json()
    assert [item["handle"] for item in before["items"]] == [handle]
    due(db, person(db, creator), clock)

    run(db, clock)

    after = client.get(
        "/api/v1/creators", params={"q": handle}, headers=brand.headers
    ).json()
    assert after["items"] == []
    assert client.get(f"/api/v1/creators/by-handle/{handle}").status_code == 404


# --- what the other side keeps ------------------------------------------------------------


def test_the_brand_keeps_the_deal_with_a_creator_who_left(
    client, db, clock, brand, creator
):
    memo_id = accepted_memo(client, brand, creator)
    finish_deal(client, brand, creator, memo_id)
    due(db, person(db, creator), clock)

    assert run(db, clock).erased == 1

    payments = client.get("/api/v1/payments/mine", headers=brand.headers).json()["items"]
    [payment] = [p for p in payments if p["deal_memo_id"] == memo_id]
    assert payment["creator_display_name"] == LEFT_CREATOR_NAME
    assert payment["confirmed_at"] is not None
    memo = client.get(f"{MEMOS_URL}/{memo_id}", headers=brand.headers)
    assert memo.status_code == 200


def test_the_creator_keeps_the_deal_with_a_brand_that_left(
    client, db, clock, brand, creator
):
    memo_id = accepted_memo(client, brand, creator)
    finish_deal(client, brand, creator, memo_id)
    due(db, person(db, brand), clock)

    assert run(db, clock).erased == 1

    payments = client.get("/api/v1/payments/mine", headers=creator.headers).json()[
        "items"
    ]
    [payment] = [p for p in payments if p["deal_memo_id"] == memo_id]
    assert payment["brand_name"] == LEFT_BRAND_NAME


# --- what never became a deal ---------------------------------------------------------------


def open_campaign(
    client, brand: User, title: str = "Karthigai lamps", city: str = "Madurai"
) -> str:
    campaign_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": title,
            "description": "Reels about our brass lamps.",
            "campaign_type": "paid",
            "budget_min_paise": 300_000,
            "budget_max_paise": 900_000,
            "cities": [city],
            "niches": ["food"],
            "deliverables": "1 Instagram reel",
        },
        headers=brand.headers,
    ).json()["id"]
    published = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers
    )
    assert published.status_code == 200, published.text
    return str(campaign_id)


def test_a_brand_that_leaves_ends_its_campaigns_and_invitations(client, db, clock, brand):
    others = [creator_user(db, clock) for _ in range(2)]
    db.commit()
    open_id = open_campaign(client, brand)
    draft_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Draft",
            "description": "Not published yet.",
            "campaign_type": "barter",
            "cities": ["Salem"],
            "niches": ["food"],
            "deliverables": "1 story",
        },
        headers=brand.headers,
    ).json()["id"]
    applied = client.post(
        f"{CAMPAIGNS_URL}/{open_id}/applications",
        json={"pitch": PITCH},
        headers=others[0].headers,
    ).json()["id"]
    invited_creator = db.scalars(
        select(Creator.id).where(Creator.account_id == others[1].account_id)
    ).one()
    invited = client.post(
        f"{CAMPAIGNS_URL}/{open_id}/invitations",
        json={"creator_id": str(invited_creator)},
        headers=brand.headers,
    )
    assert invited.status_code == 201, invited.text
    due(db, person(db, brand), clock)

    run(db, clock)

    statuses = {
        campaign.id: campaign.status
        for campaign in db.scalars(
            select(Campaign).where(Campaign.id.in_([open_id, draft_id]))
        )
    }
    assert statuses == {uuid.UUID(open_id): "closed", uuid.UUID(draft_id): "cancelled"}
    assert db.get_one(Application, invited.json()["id"]).status == "withdrawn"
    # An application to a closed campaign stays as it was, as with any close.
    assert db.get_one(Application, applied).status == "submitted"
    # Nobody is told: the brand is gone, and the creators see the campaign closed.
    assert (
        db.scalars(
            select(Notification.id).where(
                Notification.account_id.in_([u.account_id for u in others]),
                Notification.notification_type.in_(["invitation_withdrawn"]),
            )
        ).all()
        == []
    )


def test_a_creator_who_leaves_withdraws_applications_and_declines_invitations(
    client, db, clock, brand, creator
):
    first, second, third = (
        open_campaign(client, brand, f"Campaign {n}") for n in range(3)
    )
    submitted = client.post(
        f"{CAMPAIGNS_URL}/{first}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    shortlisted = client.post(
        f"{CAMPAIGNS_URL}/{second}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{shortlisted}/shortlist", headers=brand.headers)
    creator_id = db.scalars(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    ).one()
    invitation = client.post(
        f"{CAMPAIGNS_URL}/{third}/invitations",
        json={"creator_id": str(creator_id)},
        headers=brand.headers,
    ).json()["id"]
    due(db, person(db, creator), clock)

    run(db, clock)

    assert db.get_one(Application, submitted).status == "withdrawn"
    assert db.get_one(Application, shortlisted).status == "withdrawn"
    declined = db.get_one(Application, invitation)
    assert (declined.status, declined.decline_reason) == ("declined", "other")


def test_nothing_new_starts_with_a_creator_who_left(client, db, clock, brand, creator):
    campaign_id = open_campaign(client, brand)
    accepted_on = open_campaign(client, brand, "Accepted, no memo")
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{accepted_on}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    creator_id = db.scalars(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    ).one()
    due(db, person(db, creator), clock)
    run(db, clock)

    invitation = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/invitations",
        json={"creator_id": str(creator_id)},
        headers=brand.headers,
    )
    memo = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "1 reel.", "fee_amount_paise": 400_000},
        headers=brand.headers,
    )

    assert invitation.status_code == 404
    assert invitation.json()["code"] == "creator_not_found"
    assert memo.status_code == 409
    assert memo.json()["code"] == "creator_left"


# --- what holds or waits it ------------------------------------------------------------------


def test_a_deal_begun_in_the_wait_holds_it_and_tells_the_owner_once(
    client, db, clock, brand, creator
):
    memo_id = accepted_memo(client, brand, creator)
    who = person(db, creator)
    due(db, who, clock)

    first, second = run(db, clock), run(db, clock)

    assert (first.held, second.held) == (1, 1)
    assert db.get_one(Account, who.account_id).deleted_at is None
    held = db.scalars(
        select(Notification).where(
            Notification.account_id == who.account_id,
            Notification.notification_type == "deletion_held_by_deals",
        )
    ).all()
    assert [n.details for n in held] == [{"unfinished_deals": 1}]
    assert "deletion_held_by_deals" in URGENT_TYPES

    finish_deal(client, brand, creator, memo_id)
    assert run(db, clock).erased == 1


def test_a_cancelled_deletion_is_left_alone(client, db, clock, creator):
    who = person(db, creator)
    due(db, who, clock)
    assert (
        client.delete("/api/v1/me/deletion", headers=creator.headers).status_code == 204
    )

    assert run(db, clock).due == 0
    assert db.get_one(Account, who.account_id).deleted_at is None


def test_a_second_run_erases_nothing_more(db, clock, creator):
    due(db, person(db, creator), clock)
    assert run(db, clock).erased == 1

    again = run(db, clock)

    assert again.due == again.erased == 0


def test_erasing_one_already_gone_does_nothing(db, clock, creator):
    who = person(db, creator)
    due(db, who, clock)
    assert service.erase(db, who.account_id, clock.now) == "erased"

    assert service.erase(db, who.account_id, clock.now) is None


def test_an_export_being_prepared_waits_it(db, clock, creator):
    who = person(db, creator)
    db.add(DataExport(account_id=who.account_id, requested_at=clock.now))
    due(db, who, clock)

    run_ = run(db, clock)

    assert run_.waiting_for_export == 1
    assert db.get_one(Account, who.account_id).deleted_at is None


def test_a_stored_export_file_is_destroyed_first(db, clock, creator):
    who = person(db, creator)
    export = DataExport(
        account_id=who.account_id,
        requested_at=clock.now - timedelta(hours=2),
        ready_at=clock.now - timedelta(hours=1),
        expires_at=clock.now + timedelta(hours=23),
        size_bytes=4,
    )
    db.add(export)
    db.flush()
    export_id = export.id
    store = memory_store()
    store.write(object_key(export_id), b"{}\n\n", content_type="application/json")
    due(db, who, clock)

    assert run(db, clock, store).erased == 1

    assert object_key(export_id) not in store.keys()  # noqa: SIM118 - a method, not a dict
    assert db.scalar(select(DataExport.id).where(DataExport.id == export_id)) is None


def test_an_admin_is_never_erased_by_the_job(db, clock):
    # The route refuses an admin; even with the dates written by hand, the
    # job leaves the account alone: only the founders remove one.
    admin = create_account(db, "admin")
    admin.deletion_requested_at = clock.now - WAIT - timedelta(minutes=1)
    admin.deletion_takes_effect_at = admin.deletion_requested_at + WAIT
    db.commit()

    assert service.erase(db, admin.id, clock.now) is None
    db.refresh(admin)
    assert admin.phone is not None
    assert admin.deleted_at is None


def test_a_brand_with_only_a_closed_campaign_is_erased(db, clock):
    lone = brand_user(db, clock)
    db.add(build_campaign(db, brand_id=person(db, lone).profile_id, status="closed"))
    db.commit()
    due(db, person(db, lone), clock)

    assert run(db, clock).erased == 1


def test_a_deleted_account_is_refused_even_with_a_session_left(
    client, db, clock, creator
):
    """The request check alone, in case a session ever outlived the erasure."""
    db.execute(
        text(
            "UPDATE account SET deletion_requested_at = :asked,"
            " deletion_takes_effect_at = :asked + interval '30 days',"
            " deleted_at = :now, phone = NULL WHERE id = :a"
        ),
        {"asked": clock.now - WAIT, "now": clock.now, "a": creator.account_id},
    )
    db.commit()

    # A route that never reads the number, so only this check can refuse it.
    assert client.get("/api/v1/me/deletion", headers=creator.headers).status_code == 401


def mark_deleted(db, account_id, clock) -> None:
    """Deleted by hand, nothing else erased: each guard below alone."""
    db.execute(
        text(
            "UPDATE account SET deletion_requested_at = :asked,"
            " deletion_takes_effect_at = :asked + interval '30 days',"
            " deleted_at = :now, phone = NULL WHERE id = :a"
        ),
        {"asked": clock.now - WAIT, "now": clock.now, "a": account_id},
    )
    db.commit()


def test_a_deleted_creator_is_never_searched_even_if_still_published(
    client, db, clock, brand, creator
):
    profile = db.scalars(
        select(Creator).where(Creator.account_id == creator.account_id)
    ).one()
    profile.passport_published_at = clock.now - timedelta(days=10)
    handle = profile.handle
    db.commit()
    mark_deleted(db, creator.account_id, clock)

    found = client.get("/api/v1/creators", params={"q": handle}, headers=brand.headers)

    assert found.json()["items"] == []
    assert client.get(f"/api/v1/creators/by-handle/{handle}").status_code == 404


def test_a_deleted_brands_campaign_is_never_discovered_even_if_still_open(
    client, db, clock, brand, creator
):
    # A city of its own, so no other open campaign pushes it off the page.
    city = f"Town {uuid.uuid4().hex[:8]}"
    campaign_id = open_campaign(client, brand, "Still open by hand", city=city)
    listed = client.get(
        "/api/v1/campaigns/discover", params={"city": city}, headers=creator.headers
    ).json()
    assert [item["id"] for item in listed["items"]] == [campaign_id]
    mark_deleted(db, brand.account_id, clock)

    found = client.get(
        "/api/v1/campaigns/discover", params={"city": city}, headers=creator.headers
    ).json()
    applied = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )

    assert campaign_id not in [item["id"] for item in found["items"]]
    assert applied.status_code == 409
    assert applied.json()["code"] == "campaign_not_open"
