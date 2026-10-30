"""Team seats for brands, through the API (item 13, D-148).

The rules worth proving: an invite keeps no number and reaches only that
number; roles allow exactly their acts (`auth.brand_acts`); an admin is the
owner's to make, with a code; removing anyone needs a code; a removed member
loses the brand at once; someone in two brands says which; a brand whose
owner is suspended is closed to its members; the team is capped.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import MAX_TEAM_MEMBERS, BrandInvite, BrandMember
from tests.deal_flow import MEMOS_URL, PAYMENT_REFERENCE, User, accepted_memo, brand_user
from tests.deal_flow import creator_user as make_creator
from tests.factories import create_account
from tests.step_up import with_code

TEAM = "/api/v1/brands/me/team"
INVITES = f"{TEAM}/invites"
MY_INVITES = "/api/v1/me/team-invites"
CAMPAIGNS = "/api/v1/campaigns"
CAMPAIGN = {
    "title": "Pongal sweets launch",
    "description": "Three reels featuring our new sweet box.",
    "campaign_type": "paid",
    "budget_min_paise": 500_000,
    "budget_max_paise": 1_500_000,
    "cities": ["Madurai"],
    "niches": ["food"],
    "deliverables": "3 Instagram reels",
}


def problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


@pytest.fixture
def owner(db, clock) -> User:
    return brand_user(db, clock)


def person(db, clock) -> tuple[User, str]:
    """A brand account with no brand of its own, and its number."""
    account = create_account(db, "brand")
    return User(account.id, "brand", clock), str(account.phone)


def join(client, db, clock, owner: User, role: str, name: str = "Ravi") -> User:
    """Invite a new person in `role` and have them accept; the member."""
    member, phone = person(db, clock)
    headers = owner.headers
    if role == "admin":
        headers = with_code(
            client, owner.headers, "change_team", change=f"invite:{phone}:admin"
        )
    made = client.post(
        INVITES, json={"phone": phone, "role": role, "first_name": name}, headers=headers
    )
    assert made.status_code == 201, made.text
    joined = client.post(
        f"{MY_INVITES}/{made.json()['id']}/accept", json={}, headers=member.headers
    )
    assert joined.status_code == 201, joined.text
    member.member_id = joined.json()["id"]  # type: ignore[attr-defined]
    return member


def test_an_invite_keeps_no_number_and_reaches_only_that_number(client, db, clock, owner):
    invited, phone = person(db, clock)
    stranger, _ = person(db, clock)

    made = client.post(
        INVITES,
        json={"phone": phone, "role": "campaigns", "first_name": "Ravi"},
        headers=owner.headers,
    )

    assert made.status_code == 201, made.text
    assert phone not in made.text
    row = db.get_one(BrandInvite, made.json()["id"])
    assert row.phone_hash != phone and phone not in row.phone_hash
    [mine] = client.get(MY_INVITES, headers=invited.headers).json()
    assert (mine["id"], mine["role"]) == (made.json()["id"], "campaigns")
    assert client.get(MY_INVITES, headers=stranger.headers).json() == []
    problem(
        client.post(
            f"{MY_INVITES}/{mine['id']}/accept", json={}, headers=stranger.headers
        ),
        404,
        "team_invite_not_found",
    )


def test_joining_puts_the_person_on_the_team_and_tells_the_owner(
    client, db, clock, owner
):
    member = join(client, db, clock, owner, "campaigns", name="Ravi")

    team = client.get(TEAM, headers=owner.headers).json()
    assert [(m["first_name"], m["role"]) for m in team["members"]] == [
        ("Ravi", "campaigns")
    ]
    assert team["invites"] == [] and team["your_role"] == "owner"
    assert client.get(TEAM, headers=member.headers).json()["your_role"] == "campaigns"
    kinds = [
        n["notification_type"]
        for n in client.get("/api/v1/notifications", headers=owner.headers).json()[
            "items"
        ]
    ]
    assert "team_joined" in kinds


def test_a_campaign_manager_runs_campaigns_but_never_marks_money(
    client, db, clock, owner
):
    member = join(client, db, clock, owner, "campaigns")

    assert (
        client.post(CAMPAIGNS, json=CAMPAIGN, headers=member.headers).status_code == 201
    )
    problem(
        client.post(
            "/api/v1/brands/me/payments/mark-paid",
            json={"items": [], "method": "upi"},
            headers=member.headers,
        ),
        403,
        "brand_role_not_allowed",
    )


def test_finance_marks_payments_but_never_runs_campaigns(client, db, clock, owner):
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={
            "content_url": "https://www.instagram.com/reel/abc123/",
            "format": "reel",
            "disclosure_confirmed": True,
        },
        headers=creator.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=owner.headers)
    finance = join(client, db, clock, owner, "finance")

    problem(
        client.post(CAMPAIGNS, json=CAMPAIGN, headers=finance.headers),
        403,
        "brand_role_not_allowed",
    )
    marked = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": PAYMENT_REFERENCE},
        headers=finance.headers,
    )
    assert marked.status_code == 200, marked.text


def test_only_the_owner_makes_an_admin_and_only_with_a_code(client, db, clock, owner):
    admin = join(client, db, clock, owner, "admin")
    _, phone = person(db, clock)
    body = {"phone": phone, "role": "admin", "first_name": "Meena"}

    problem(
        client.post(INVITES, json=body, headers=admin.headers),
        403,
        "team_change_not_allowed",
    )
    problem(
        client.post(INVITES, json=body, headers=owner.headers), 401, "step_up_required"
    )


def test_removing_needs_a_code_and_takes_the_brand_away_at_once(client, db, clock, owner):
    member = join(client, db, clock, owner, "campaigns")
    url = f"{TEAM}/members/{member.member_id}"  # type: ignore[attr-defined]

    problem(client.delete(url, headers=owner.headers), 401, "step_up_required")
    removed = client.delete(
        url,
        headers=with_code(
            client, owner.headers, "change_team", change=f"remove:{member.member_id}"
        ),  # type: ignore[attr-defined]
    )

    assert removed.status_code == 204, removed.text
    problem(client.get(TEAM, headers=member.headers), 409, "brand_profile_required")


def test_an_admin_never_removes_an_admin(client, db, clock, owner):
    first = join(client, db, clock, owner, "admin", name="Asha")
    second = join(client, db, clock, owner, "admin", name="Bala")
    mid = second.member_id  # type: ignore[attr-defined]

    problem(
        client.delete(
            f"{TEAM}/members/{mid}",
            headers=with_code(
                client, first.headers, "change_team", change=f"remove:{mid}"
            ),
        ),
        403,
        "team_change_not_allowed",
    )


def test_a_member_may_leave_with_no_code(client, db, clock, owner):
    member = join(client, db, clock, owner, "finance")
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))

    assert (
        client.delete(f"/api/v1/me/teams/{brand_id}", headers=member.headers).status_code
        == 204
    )
    problem(client.get(TEAM, headers=member.headers), 409, "brand_profile_required")


def test_someone_in_two_brands_says_which(client, db, clock, owner):
    other_owner = brand_user(db, clock)
    member, phone = person(db, clock)
    for who in (owner, other_owner):
        made = client.post(
            INVITES,
            json={"phone": phone, "role": "campaigns", "first_name": "Ravi"},
            headers=who.headers,
        ).json()["id"]
        client.post(f"{MY_INVITES}/{made}/accept", json={}, headers=member.headers)
    other_brand = db.scalar(
        select(Brand.id).where(Brand.account_id == other_owner.account_id)
    )
    unrelated = db.scalar(
        select(Brand.id).where(Brand.account_id == brand_user(db, clock).account_id)
    )

    problem(client.get(TEAM, headers=member.headers), 422, "brand_choice_needed")
    chosen = client.get(TEAM, headers={**member.headers, "Brand-Id": str(other_brand)})
    assert chosen.status_code == 200 and chosen.json()["brand_id"] == str(other_brand)
    problem(
        client.get(TEAM, headers={**member.headers, "Brand-Id": str(unrelated)}),
        404,
        "brand_not_found",
    )


def test_a_suspended_owner_closes_the_brand_to_its_members(client, db, clock, owner):
    member = join(client, db, clock, owner, "campaigns")
    account = db.get_one(Account, owner.account_id)
    account.suspended_at = clock.now
    account.suspension_reason = "non_payment"
    db.flush()

    problem(client.get(TEAM, headers=member.headers), 404, "brand_not_found")


def test_an_invite_lapses_after_seven_days(client, db, clock, owner):
    invited, phone = person(db, clock)
    made = client.post(
        INVITES,
        json={"phone": phone, "role": "finance", "first_name": "Meena"},
        headers=owner.headers,
    ).json()["id"]
    clock.advance(timedelta(days=7, seconds=1))

    problem(
        client.post(f"{MY_INVITES}/{made}/accept", json={}, headers=invited.headers),
        404,
        "team_invite_not_found",
    )


def test_a_declined_invite_cannot_be_accepted(client, db, clock, owner):
    invited, phone = person(db, clock)
    made = client.post(
        INVITES,
        json={"phone": phone, "role": "finance", "first_name": "Meena"},
        headers=owner.headers,
    ).json()["id"]

    assert (
        client.post(f"{MY_INVITES}/{made}/decline", headers=invited.headers).status_code
        == 204
    )
    problem(
        client.post(f"{MY_INVITES}/{made}/accept", json={}, headers=invited.headers),
        404,
        "team_invite_not_found",
    )


def test_one_open_invite_per_number(client, db, clock, owner):
    _, phone = person(db, clock)
    body = {"phone": phone, "role": "finance", "first_name": "Meena"}
    client.post(INVITES, json=body, headers=owner.headers)

    problem(
        client.post(INVITES, json=body, headers=owner.headers), 409, "team_invite_exists"
    )


def test_the_team_is_capped(client, db, clock, owner):
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))
    for i in range(MAX_TEAM_MEMBERS):
        db.add(
            BrandMember(
                brand_id=brand_id,
                account_id=create_account(db, "brand").id,
                role="finance",
                first_name=f"Member{i}",
                created_at=clock.now,
                updated_at=clock.now,
            )
        )
    db.flush()
    invited, phone = person(db, clock)
    made = client.post(
        INVITES,
        json={"phone": phone, "role": "finance", "first_name": "Meena"},
        headers=owner.headers,
    ).json()["id"]

    problem(
        client.post(f"{MY_INVITES}/{made}/accept", json={}, headers=invited.headers),
        409,
        "team_full",
    )


def test_a_creator_has_no_team(client, db, clock):
    problem(
        client.get(TEAM, headers=make_creator(db, clock).headers), 403, "role_not_allowed"
    )


def test_the_team_needs_a_login(client):
    assert client.get(TEAM).status_code == 401


def test_the_record_names_the_team_member_who_acted(client, db, clock, owner):
    """A campaign manager's approval is sealed as theirs, never the owner's (D-148)."""
    from app.modules.deal_memo.record_models import DealRecordEntry

    member = join(client, db, clock, owner, "campaigns")

    def approve(by: User) -> str:
        creator = make_creator(db, clock)
        memo_id = accepted_memo(client, owner, creator)
        proof = client.post(
            f"{MEMOS_URL}/{memo_id}/proof",
            json={
                "content_url": "https://www.instagram.com/reel/abc123/",
                "format": "reel",
                "disclosure_confirmed": True,
            },
            headers=creator.headers,
        ).json()["id"]
        done = client.post(
            f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=by.headers
        )
        assert done.status_code == 200, done.text
        return memo_id

    def approver(memo_id: str):
        return db.scalar(
            select(DealRecordEntry.actor_account_id).where(
                DealRecordEntry.deal_memo_id == memo_id,
                DealRecordEntry.kind == "proof_approved",
            )
        )

    assert approver(approve(member)) == member.account_id
    assert approver(approve(owner)) == owner.account_id
