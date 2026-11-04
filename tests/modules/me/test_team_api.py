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
from app.modules.auth.models.brand_team import (
    MAX_INVITES_PER_DAY,
    MAX_TEAM_MEMBERS,
    BrandInvite,
    BrandMember,
)
from app.modules.auth.models.creator import Creator
from tests.deal_flow import MEMOS_URL, PAYMENT_REFERENCE, User, accepted_memo, brand_user
from tests.deal_flow import creator_user as make_creator
from tests.factories import create_account, unique_test_phone
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


def test_a_deal_note_follows_the_role_and_names_who_wrote_it(client, db, clock, owner):
    """Routes either side may call reach a member through the deal itself (D-148)."""
    from app.modules.deal_memo.record_models import DealRecordEntry

    manager = join(client, db, clock, owner, "campaigns", name="Ravi")
    finance = join(client, db, clock, owner, "finance", name="Meena")
    memo_id = accepted_memo(client, owner, make_creator(db, clock))
    url = f"{MEMOS_URL}/{memo_id}/notes"

    written = client.post(
        url, json={"body": "Shooting on Friday."}, headers=manager.headers
    )
    assert written.status_code == 201, written.text
    problem(
        client.post(url, json={"body": "Paid soon."}, headers=finance.headers),
        403,
        "brand_role_not_allowed",
    )
    assert client.get(url, headers=finance.headers).status_code == 200
    sealed = db.scalar(
        select(DealRecordEntry.actor_account_id).where(
            DealRecordEntry.deal_memo_id == memo_id, DealRecordEntry.kind == "note_added"
        )
    )
    assert sealed == manager.account_id


def test_a_stranger_brand_member_never_reaches_the_deal(client, db, clock, owner):
    memo_id = accepted_memo(client, owner, make_creator(db, clock))
    outsider = join(client, db, clock, brand_user(db, clock), "admin")

    problem(
        client.get(f"{MEMOS_URL}/{memo_id}/notes", headers=outsider.headers),
        404,
        "memo_not_found",
    )


def test_a_member_never_finds_a_creator_who_blocked_the_brand(client, db, clock, owner):
    """Search hides blocks either way (item 59); a member searches as the brand."""
    creator = make_creator(db, clock)
    published = client.post(
        "/api/v1/creators/me/passport/publish", headers=creator.headers
    )
    assert published.status_code == 200, published.text
    handle = db.scalar(
        select(Creator.handle).where(Creator.account_id == creator.account_id)
    )
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))
    member = join(client, db, clock, owner, "campaigns")

    def found(user: User) -> list[str]:
        page = client.get("/api/v1/creators", params={"q": handle}, headers=user.headers)
        assert page.status_code == 200, page.text
        return [row["handle"] for row in page.json()["items"]]

    assert found(member) == [handle]
    blocked = client.post(
        "/api/v1/me/blocks", json={"brand_id": str(brand_id)}, headers=creator.headers
    )
    assert blocked.status_code == 201, blocked.text

    assert found(owner) == []
    assert found(member) == []


def test_a_member_reads_the_brand_s_draft_campaign_and_a_stranger_does_not(
    client, db, clock, owner
):
    """A draft is private to the brand (security.md section 2): its team included."""
    draft = client.post(CAMPAIGNS, json=CAMPAIGN, headers=owner.headers)
    assert draft.status_code == 201, draft.text
    url = f"{CAMPAIGNS}/{draft.json()['id']}"
    member = join(client, db, clock, owner, "finance")
    outsider = join(client, db, clock, brand_user(db, clock), "admin")

    assert client.get(url, headers=member.headers).status_code == 200
    problem(client.get(url, headers=outsider.headers), 404, "campaign_not_found")


def test_a_brand_sends_twenty_invites_a_day_however_many_send_them(
    client, db, clock, owner, unlimited
):
    """The ceiling is the brand's (D-148): an admin's invites count with the owner's."""
    admin = join(client, db, clock, owner, "admin")  # the brand's first invite

    def send(user: User):
        return client.post(
            INVITES,
            json={"phone": unique_test_phone(), "role": "finance", "first_name": "Meena"},
            headers=user.headers,
        )

    for n in range(MAX_INVITES_PER_DAY - 1):
        assert send(owner if n % 2 else admin).status_code == 201

    problem(send(admin), 429, "team_invites_daily_limit")
    problem(send(owner), 429, "team_invites_daily_limit")
    clock.advance(timedelta(days=1, seconds=1))
    assert send(owner).status_code == 201


def test_nobody_already_acting_for_the_brand_is_invited_again(client, db, clock, owner):
    member, phone = person(db, clock)
    made = client.post(
        INVITES,
        json={"phone": phone, "role": "finance", "first_name": "Meena"},
        headers=owner.headers,
    ).json()["id"]
    client.post(f"{MY_INVITES}/{made}/accept", json={}, headers=member.headers)
    owner_phone = db.get_one(Account, owner.account_id).phone

    for number in (phone, owner_phone):
        problem(
            client.post(
                INVITES,
                json={"phone": number, "role": "campaigns", "first_name": "Ravi"},
                headers=owner.headers,
            ),
            409,
            "already_on_team",
        )


def test_a_lapsed_invite_makes_room_for_a_new_one(client, db, clock, owner):
    invited, phone = person(db, clock)
    body = {"phone": phone, "role": "finance", "first_name": "Meena"}
    lapsed = client.post(INVITES, json=body, headers=owner.headers).json()["id"]
    clock.advance(timedelta(days=7, seconds=1))

    fresh = client.post(INVITES, json=body, headers=owner.headers)

    assert fresh.status_code == 201, fresh.text
    assert db.get_one(BrandInvite, lapsed).revoked_at == clock.now
    assert [i["id"] for i in client.get(MY_INVITES, headers=invited.headers).json()] == [
        fresh.json()["id"]
    ]


def test_a_taken_back_invite_is_gone_and_cannot_be_taken_back_twice(
    client, db, clock, owner
):
    invited, phone = person(db, clock)
    made = client.post(
        INVITES,
        json={"phone": phone, "role": "finance", "first_name": "Meena"},
        headers=owner.headers,
    ).json()["id"]
    url = f"{INVITES}/{made}"

    assert client.delete(url, headers=owner.headers).status_code == 204
    assert client.get(TEAM, headers=owner.headers).json()["invites"] == []
    assert client.get(MY_INVITES, headers=invited.headers).json() == []
    problem(client.delete(url, headers=owner.headers), 404, "team_invite_not_found")
    problem(
        client.post(f"{MY_INVITES}/{made}/accept", json={}, headers=invited.headers),
        404,
        "team_invite_not_found",
    )


def test_another_brand_never_takes_back_this_brand_s_invite(client, db, clock, owner):
    _, phone = person(db, clock)
    made = client.post(
        INVITES,
        json={"phone": phone, "role": "finance", "first_name": "Meena"},
        headers=owner.headers,
    ).json()["id"]

    problem(
        client.delete(f"{INVITES}/{made}", headers=brand_user(db, clock).headers),
        404,
        "team_invite_not_found",
    )
    assert db.get_one(BrandInvite, made).revoked_at is None


def test_an_unknown_invite_is_not_found_to_accept_or_decline(client, db, clock):
    invited, _ = person(db, clock)
    unknown = "00000000-0000-4000-8000-000000000000"

    problem(
        client.post(f"{MY_INVITES}/{unknown}/accept", json={}, headers=invited.headers),
        404,
        "team_invite_not_found",
    )
    problem(
        client.post(f"{MY_INVITES}/{unknown}/decline", headers=invited.headers),
        404,
        "team_invite_not_found",
    )


def test_someone_already_on_the_team_cannot_join_it_twice(client, db, clock, owner):
    """A second open invite to a member's number, as a race could leave one."""
    from app.modules.auth.models.brand_team import INVITE_LIFETIME
    from app.modules.auth.team_invites import hash_invited_phone

    member = join(client, db, clock, owner, "finance")
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))
    second = BrandInvite(
        brand_id=brand_id,
        role="campaigns",
        first_name="Ravi",
        phone_hash=hash_invited_phone(db.get_one(Account, member.account_id).phone),
        invited_by_account_id=owner.account_id,
        expires_at=clock.now + INVITE_LIFETIME,
        created_at=clock.now,
        updated_at=clock.now,
    )
    db.add(second)
    db.flush()

    problem(
        client.post(f"{MY_INVITES}/{second.id}/accept", json={}, headers=member.headers),
        409,
        "already_on_team",
    )


def test_an_admin_moves_a_member_between_campaigns_and_finance(client, db, clock, owner):
    admin = join(client, db, clock, owner, "admin")
    member = join(client, db, clock, owner, "campaigns")
    url = f"{TEAM}/members/{member.member_id}"  # type: ignore[attr-defined]

    changed = client.patch(url, json={"role": "finance"}, headers=admin.headers)

    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "finance"
    assert client.get(TEAM, headers=member.headers).json()["your_role"] == "finance"
    kinds = [
        n["notification_type"]
        for n in client.get("/api/v1/notifications", headers=member.headers).json()[
            "items"
        ]
    ]
    assert "team_role_changed" in kinds
    same = client.patch(url, json={"role": "finance"}, headers=admin.headers)
    assert same.status_code == 200 and same.json()["role"] == "finance"


def test_only_the_owner_makes_a_member_an_admin_and_only_with_a_code(
    client, db, clock, owner
):
    admin = join(client, db, clock, owner, "admin")
    member = join(client, db, clock, owner, "finance")
    mid = member.member_id  # type: ignore[attr-defined]
    url = f"{TEAM}/members/{mid}"
    body = {"role": "admin"}

    problem(
        client.patch(
            url,
            json=body,
            headers=with_code(
                client, admin.headers, "change_team", change=f"role:{mid}:admin"
            ),
        ),
        403,
        "team_change_not_allowed",
    )
    problem(client.patch(url, json=body, headers=owner.headers), 401, "step_up_required")
    promoted = client.patch(
        url,
        json=body,
        headers=with_code(
            client, owner.headers, "change_team", change=f"role:{mid}:admin"
        ),
    )
    assert promoted.status_code == 200, promoted.text
    assert client.get(TEAM, headers=member.headers).json()["your_role"] == "admin"


def test_an_admin_never_changes_an_admin_s_role(client, db, clock, owner):
    first = join(client, db, clock, owner, "admin", name="Asha")
    second = join(client, db, clock, owner, "admin", name="Bala")

    problem(
        client.patch(
            f"{TEAM}/members/{second.member_id}",  # type: ignore[attr-defined]
            json={"role": "finance"},
            headers=first.headers,
        ),
        403,
        "team_change_not_allowed",
    )


def test_changing_someone_not_on_the_team_is_not_found(client, db, clock, owner):
    outsider = join(client, db, clock, brand_user(db, clock), "finance")

    problem(
        client.patch(
            f"{TEAM}/members/{outsider.member_id}",  # type: ignore[attr-defined]
            json={"role": "campaigns"},
            headers=owner.headers,
        ),
        404,
        "team_member_not_found",
    )


def test_leaving_a_brand_you_are_not_in_is_not_found(client, db, clock, owner):
    stranger, _ = person(db, clock)
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))

    for url in (
        f"/api/v1/me/teams/{brand_id}",
        "/api/v1/me/teams/00000000-0000-4000-8000-000000000000",
    ):
        problem(
            client.delete(url, headers=stranger.headers), 404, "team_member_not_found"
        )


def test_a_creator_never_sees_or_accepts_an_invite_to_their_number(
    client, db, clock, owner
):
    """A creator account on the invited number is not the brand account invited."""
    creator = make_creator(db, clock)
    made = client.post(
        INVITES,
        json={
            "phone": db.get_one(Account, creator.account_id).phone,
            "role": "finance",
            "first_name": "Meena",
        },
        headers=owner.headers,
    ).json()["id"]

    problem(
        client.post(f"{MY_INVITES}/{made}/accept", json={}, headers=creator.headers),
        404,
        "team_invite_not_found",
    )
    assert client.get(MY_INVITES, headers=creator.headers).json() == []
