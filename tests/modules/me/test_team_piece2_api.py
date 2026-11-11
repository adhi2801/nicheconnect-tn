"""Who on a team hears what, who creators see acted, and handing a brand over (item 13 piece 2, D-148).

The rules worth proving: a brand's notification reaches the owner and every
member whose role holds the act it concerns, and nobody else; a creator told
of a member's act sees that member's first name, never for the owner and
never for the deal's own rules; the record's reads name the member who acted;
ownership moves only by the owner, with a code, to a live member who owns no
brand; an assistant's token and the attention list act within the member's
role.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.modules.auth import agent_tokens
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import BrandMember
from app.modules.notifications.models import Notification
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    PAYMENT_REFERENCE,
    User,
    accepted_memo,
    brand_user,
)
from tests.deal_flow import creator_user as make_creator
from tests.modules.me import test_team_api as team
from tests.step_up import log_out_everywhere, with_code

owner = team.owner
join = team.join
problem = team.problem
OWNERSHIP = f"{team.TEAM}/ownership"


def kinds_for(db, user: User) -> list[str]:
    return list(
        db.scalars(
            select(Notification.notification_type).where(
                Notification.account_id == user.account_id
            )
        )
    )


def submit_proof(client, memo_id: str, creator: User) -> str:
    sent = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert sent.status_code == 201, sent.text
    return sent.json()["id"]


# --- who hears what ------------------------------------------------------------------


def test_a_brand_notice_reaches_the_roles_that_act_on_it(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    finance = join(client, db, clock, owner, "finance", "Meena")
    admin = join(client, db, clock, owner, "admin", "Kavi")
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)

    # A new application and an accepted memo concern campaigns and deals.
    for kind in ("application_received", "memo_accepted"):
        assert kind in kinds_for(db, owner)
        assert kind in kinds_for(db, campaigns)
        assert kind in kinds_for(db, admin)
        assert kind not in kinds_for(db, finance)

    # Work sent concerns those who judge it.
    submit_proof(client, memo_id, creator)
    assert "proof_submitted" in kinds_for(db, campaigns)
    assert "proof_submitted" not in kinds_for(db, finance)


def test_a_confirmed_payment_reaches_finance_not_campaigns(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    finance = join(client, db, clock, owner, "finance", "Meena")
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)
    proof = submit_proof(client, memo_id, creator)
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=owner.headers)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": PAYMENT_REFERENCE},
        headers=finance.headers,
    )
    confirmed = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers
    )
    assert confirmed.status_code == 200, confirmed.text

    assert "payment_confirmed" in kinds_for(db, owner)
    assert "payment_confirmed" in kinds_for(db, finance)
    assert "payment_confirmed" not in kinds_for(db, campaigns)


def test_a_removed_member_hears_nothing_more(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    removed = client.delete(
        f"{team.TEAM}/members/{campaigns.member_id}",  # type: ignore[attr-defined]
        headers=with_code(
            client,
            owner.headers,
            "change_team",
            change=f"remove:{campaigns.member_id}",  # type: ignore[attr-defined]
        ),
    )
    assert removed.status_code == 204, removed.text

    accepted_memo(client, owner, make_creator(db, clock))

    assert "application_received" not in kinds_for(db, campaigns)


def test_a_personal_notice_stays_with_its_person(client, db, clock, owner):
    """The owner's own account matters (a session, a passkey) are never copied."""
    admin = join(client, db, clock, owner, "admin", "Kavi")
    ended = log_out_everywhere(client, owner.headers)
    assert ended.status_code in (200, 204), ended.text

    assert "logged_out_everywhere" in kinds_for(db, owner)
    assert "logged_out_everywhere" not in kinds_for(db, admin)


# --- what creators see of who acted ------------------------------------------------


def acted_on_proof(client, db, clock, owner, by: User) -> tuple[User, str]:
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)
    proof = submit_proof(client, memo_id, creator)
    done = client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=by.headers)
    assert done.status_code == 200, done.text
    return creator, memo_id


def shown_to(client, user: User, notification_type: str) -> dict:
    """A notice's details exactly as its reader is shown them."""
    [details] = [
        n["details"]
        for n in client.get("/api/v1/notifications", headers=user.headers).json()["items"]
        if n["notification_type"] == notification_type
    ]
    return details


def approval_details(client, creator: User) -> dict:
    return shown_to(client, creator, "proof_approved")


def test_a_creator_sees_the_first_name_of_the_member_who_acted(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")

    by_member, _ = acted_on_proof(client, db, clock, owner, campaigns)
    by_owner, _ = acted_on_proof(client, db, clock, owner, owner)

    assert approval_details(client, by_member)["acting_first_name"] == "Ravi"
    assert "acting_first_name" not in approval_details(client, by_owner)


def test_the_record_shows_the_member_s_first_name(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    creator, memo_id = acted_on_proof(client, db, clock, owner, campaigns)

    read = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=creator.headers)

    assert read.status_code == 200, read.text
    names = {e["kind"]: e["actor_first_name"] for e in read.json()["entries"]}
    assert names["proof_approved"] == "Ravi"
    assert names["memo_sent"] is None  # the owner: the brand's own name stands
    assert names["memo_accepted"] is None  # the creator's own act


def test_a_read_never_names_its_reader(client, db, clock, owner):
    """A member reading a deal acts for nobody: no later notice carries their name."""
    finance = join(client, db, clock, owner, "finance", "Meena")
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)
    proof = submit_proof(client, memo_id, creator)
    assert (
        client.get(f"{MEMOS_URL}/{memo_id}", headers=finance.headers).status_code == 200
    )

    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=owner.headers)

    assert "acting_first_name" not in approval_details(client, creator)


# --- handing the brand over --------------------------------------------------------


def hand_over(client, owner: User, member_id: str, first_name: str = "Adhi"):
    return client.post(
        OWNERSHIP,
        json={"member_id": member_id, "your_first_name": first_name},
        headers=with_code(
            client, owner.headers, "change_team", change=f"ownership:{member_id}"
        ),
    )


def test_the_owner_hands_the_brand_to_a_member(client, db, clock, owner):
    admin = join(client, db, clock, owner, "admin", "Kavi")
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))

    handed = hand_over(client, owner, admin.member_id)  # type: ignore[attr-defined]

    assert handed.status_code == 200, handed.text
    assert handed.json()["your_role"] == "admin"
    assert db.get(Brand, brand_id).account_id == admin.account_id
    former = db.scalars(
        select(BrandMember).where(
            BrandMember.brand_id == brand_id,
            BrandMember.account_id == owner.account_id,
            BrandMember.removed_at.is_(None),
        )
    ).one()
    assert (former.role, former.first_name) == ("admin", "Adhi")
    # The new owner is no longer also a member of their own brand.
    assert not db.scalars(
        select(BrandMember).where(
            BrandMember.account_id == admin.account_id, BrandMember.removed_at.is_(None)
        )
    ).first()
    # And acts as the owner: the former owner, now an admin, cannot hand it back.
    problem(hand_over(client, owner, str(former.id)), 403, "brand_role_not_allowed")
    assert "team_role_changed" in kinds_for(db, admin)


def test_only_the_owner_hands_over(client, db, clock, owner):
    admin = join(client, db, clock, owner, "admin", "Kavi")
    other = join(client, db, clock, owner, "campaigns", "Ravi")

    problem(
        hand_over(client, admin, other.member_id),  # type: ignore[attr-defined]
        403,
        "brand_role_not_allowed",
    )


def test_handing_over_needs_a_code_for_that_member(client, db, clock, owner):
    admin = join(client, db, clock, owner, "admin", "Kavi")
    other = join(client, db, clock, owner, "campaigns", "Ravi")

    no_code = client.post(
        OWNERSHIP,
        json={"member_id": admin.member_id, "your_first_name": "Adhi"},  # type: ignore[attr-defined]
        headers=owner.headers,
    )
    wrong = client.post(
        OWNERSHIP,
        json={"member_id": admin.member_id, "your_first_name": "Adhi"},  # type: ignore[attr-defined]
        headers=with_code(
            client,
            owner.headers,
            "change_team",
            change=f"ownership:{other.member_id}",  # type: ignore[attr-defined]
        ),
    )

    problem(no_code, 401, "step_up_required")
    assert wrong.status_code == 400, wrong.text
    assert db.scalar(select(Brand.account_id).where(Brand.account_id == owner.account_id))


def test_a_member_who_owns_a_brand_cannot_take_another(client, db, clock, owner):
    member = join(client, db, clock, owner, "admin", "Kavi")
    from tests.factories import build_brand

    db.add(build_brand(db, account_id=member.account_id, email="kavi@example.com"))
    db.flush()

    problem(
        hand_over(client, owner, member.member_id),  # type: ignore[attr-defined]
        409,
        "owns_a_brand",
    )


def test_only_a_live_member_can_receive_it(client, db, clock, owner):
    problem(
        hand_over(client, owner, "8d5b4f7e-0c2a-4c41-9a8e-6f1f6f2b9a10"),
        404,
        "team_member_not_found",
    )


# --- assistants and attention ------------------------------------------------------


def test_a_member_s_assistant_reads_the_brand_s_deals_and_changes_nothing(
    client, db, clock, owner
):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    memo_id = accepted_memo(client, owner, make_creator(db, clock))
    _, token = agent_tokens.add(
        db,
        db.get_one(Account, campaigns.account_id),
        "Claude",
        ["deals:read"],
        clock.now + timedelta(days=30),
        clock.now,
    )
    headers = {"Authorization": f"Bearer {token}"}

    listed = client.get(f"{MEMOS_URL}/mine", headers=headers)
    refused = client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=headers)

    assert listed.status_code == 200, listed.text
    assert memo_id in {m["id"] for m in listed.json()["items"]}
    assert refused.status_code == 403, refused.text


def test_a_member_s_attention_holds_the_brand_s_work(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)
    submit_proof(client, memo_id, creator)

    read = client.get("/api/v1/me/attention", headers=campaigns.headers)

    assert read.status_code == 200, read.text
    assert read.json()["role"] == "brand"
    assert read.json()["counts"].get("review_proof", 0) >= 1


def test_someone_in_no_brand_gets_brand_profile_required_not_others_work(
    client, db, clock
):
    lonely, _ = team.person(db, clock)
    db.execute(Brand.__table__.delete().where(Brand.account_id == lonely.account_id))

    problem(
        client.get(f"{MEMOS_URL}/mine", headers=lonely.headers),
        409,
        "brand_profile_required",
    )


# --- what piece 2 added beside its first tests ------------------------------------


def test_a_copy_says_which_brand_and_never_reaches_whoever_acted(db, clock, owner):
    """Someone in several brands must know which one; nobody hears of their own act."""
    from app.modules.auth import brand_access
    from app.modules.notifications import service as notifications

    brand = db.scalars(select(Brand).where(Brand.account_id == owner.account_id)).one()
    members = []
    for name in ("Ravi", "Kavi"):
        account = team.create_account(db, "brand")
        db.add(
            BrandMember(
                brand_id=brand.id,
                account_id=account.id,
                role="campaigns",
                first_name=name,
                created_at=clock.now,
                updated_at=clock.now,
            )
        )
        members.append(account)
    db.flush()
    brand_access.note_acting(db, brand_access.Acting(members[0].id, brand.id, None))

    notifications.record(
        db,
        account_id=owner.account_id,
        notification_type="application_received",
        now=clock.now,
        details={"campaign_title": "Pongal"},
    )
    db.flush()

    def sent_to(account_id) -> list[dict]:
        return list(
            db.scalars(
                select(Notification.details).where(Notification.account_id == account_id)
            )
        )

    assert sent_to(owner.account_id) == [{"campaign_title": "Pongal"}]
    assert sent_to(members[0].id) == []
    assert sent_to(members[1].id) == [
        {
            "campaign_title": "Pongal",
            "for_brand_id": str(brand.id),
            "for_brand_name": brand.name,
        }
    ]


def test_a_creator_paid_by_finance_sees_who_marked_it(client, db, clock, owner):
    finance = join(client, db, clock, owner, "finance", "Meena")
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)
    proof = submit_proof(client, memo_id, creator)
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=owner.headers)

    marked = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": PAYMENT_REFERENCE},
        headers=finance.headers,
    )

    assert marked.status_code == 200, marked.text
    assert (
        shown_to(client, creator, "payment_marked_paid")["acting_first_name"] == "Meena"
    )


def test_creators_paid_by_finance_in_one_batch_see_who_marked_it(
    client, db, clock, owner
):
    """The bulk path writes its notices and record entries together, by code
    of its own (audit C16, D-184), so it names the member as the single path
    does, on every deal of the batch, and every record still verifies."""
    finance = join(client, db, clock, owner, "finance", "Meena")
    creators = [make_creator(db, clock) for _ in range(2)]
    memo_ids = []
    for creator in creators:
        memo_id = accepted_memo(client, owner, creator)
        proof = submit_proof(client, memo_id, creator)
        client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=owner.headers)
        memo_ids.append(memo_id)

    marked = client.post(
        "/api/v1/brands/me/payments/mark-paid",
        json={
            "payments": [
                {"memo_id": memo_id, "method": "upi", "reference": f"41234567890{i}"}
                for i, memo_id in enumerate(memo_ids)
            ]
        },
        headers=finance.headers,
    )

    assert marked.status_code == 200, marked.text
    assert marked.json()["recorded"] == 2
    for creator, memo_id in zip(creators, memo_ids, strict=True):
        shown = shown_to(client, creator, "payment_marked_paid")
        assert shown["acting_first_name"] == "Meena"
        read = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=creator.headers)
        assert read.json()["intact"] is True
        names = {e["kind"]: e["actor_first_name"] for e in read.json()["entries"]}
        assert names["payment_marked_paid"] == "Meena"


def test_the_record_keeps_the_name_of_a_member_who_left(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    creator, memo_id = acted_on_proof(client, db, clock, owner, campaigns)
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))
    left = client.delete(f"/api/v1/me/teams/{brand_id}", headers=campaigns.headers)
    assert left.status_code == 204

    read = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=creator.headers)

    names = {e["kind"]: e["actor_first_name"] for e in read.json()["entries"]}
    assert names["proof_approved"] == "Ravi"


def test_a_suspended_or_departing_member_cannot_take_the_brand(client, db, clock, owner):
    for change in (
        {"suspended_at": clock.now, "suspension_reason": "non_payment"},
        {
            "deletion_requested_at": clock.now,
            "deletion_takes_effect_at": clock.now + timedelta(days=30),
        },
    ):
        # Any role may take it over; a campaign manager needs no code to invite.
        admin = join(client, db, clock, owner, "campaigns", "Kavi")
        account = db.get_one(Account, admin.account_id)
        for field, value in change.items():
            setattr(account, field, value)
        db.flush()

        problem(
            hand_over(client, owner, admin.member_id),  # type: ignore[attr-defined]
            409,
            "cannot_take_brand",
        )
        assert db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))


# --- the independent review's findings, each with a test that fails without its fix --


def test_a_read_leaves_nobody_noted_as_acting(client, db, clock, owner):
    """A read acts for nobody: nothing is left on the session to name them later."""
    from app.modules.auth import brand_access

    finance = join(client, db, clock, owner, "finance", "Meena")
    memo_id = accepted_memo(client, owner, make_creator(db, clock))

    assert (
        client.get(f"{MEMOS_URL}/{memo_id}", headers=finance.headers).status_code == 200
    )
    assert brand_access.acting(db) is None


def test_the_deal_s_own_rules_never_name_a_member(client, db, clock, owner):
    """Approval by the clock, noticed inside a member's write, is nobody's act."""
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, owner, creator)
    proof = submit_proof(client, memo_id, creator)
    clock.advance(timedelta(days=30))

    # The member's answer comes too late: the clock approved it first.
    client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof}/request-revision",
        json={"note": "The ad label is missing from the caption."},
        headers=campaigns.headers,
    )

    assert "acting_first_name" not in shown_to(client, creator, "proof_auto_approved")


def test_an_erased_member_s_name_leaves_every_notice(client, db, clock, owner):
    """The notice keeps the membership; the name is read from it, so erasure takes it."""
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    creator, _ = acted_on_proof(client, db, clock, owner, campaigns)

    def shown() -> dict:
        [item] = [
            n
            for n in client.get("/api/v1/notifications", headers=creator.headers).json()[
                "items"
            ]
            if n["notification_type"] == "proof_approved"
        ]
        return item["details"]

    assert shown()["acting_first_name"] == "Ravi"
    assert "acting_member_id" not in shown()
    db.execute(
        BrandMember.__table__.delete().where(
            BrandMember.account_id == campaigns.account_id
        )
    )
    db.flush()

    assert "acting_first_name" not in shown()


def test_a_suspended_member_hears_nothing(client, db, clock, owner):
    campaigns = join(client, db, clock, owner, "campaigns", "Ravi")
    account = db.get_one(Account, campaigns.account_id)
    account.suspended_at = clock.now
    account.suspension_reason = "non_payment"
    db.flush()

    accepted_memo(client, owner, make_creator(db, clock))

    assert "application_received" not in kinds_for(db, campaigns)


def test_a_new_login_cannot_hand_the_brand_over(client, db, clock, owner):
    """A SIM swapper's login is new: the brand does not move on it (D-109)."""
    member = join(client, db, clock, owner, "campaigns", "Kavi")
    owner.logged_in_at = clock.now

    refused = hand_over(client, owner, member.member_id)  # type: ignore[attr-defined]

    problem(refused, 403, "login_too_recent")
    assert db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))


def test_the_former_owner_is_told(client, db, clock, owner):
    """Their other sessions see it, nobody can mute it, so a stolen session cannot hide it."""
    admin = join(client, db, clock, owner, "admin", "Kavi")

    assert hand_over(client, owner, admin.member_id).status_code == 200  # type: ignore[attr-defined]

    [told] = db.scalars(
        select(Notification.details).where(
            Notification.account_id == owner.account_id,
            Notification.notification_type == "team_role_changed",
        )
    )
    assert told["role"] == "admin"


def test_only_someone_on_this_team_can_receive_it(client, db, clock, owner, unlimited):
    left = join(client, db, clock, owner, "campaigns", "Ravi")
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))
    client.delete(f"/api/v1/me/teams/{brand_id}", headers=left.headers)
    elsewhere = join(client, db, clock, brand_user(db, clock), "campaigns", "Kavi")

    for member in (left, elsewhere):
        problem(
            hand_over(client, owner, member.member_id),  # type: ignore[attr-defined]
            404,
            "team_member_not_found",
        )


def test_the_service_refuses_anyone_but_the_owner(db, clock, owner):
    """Behind the route's act check, the service holds the rule itself."""
    import pytest

    from app.modules.auth.brand_access import BrandAccess
    from app.modules.me import team_service
    from app.modules.me.exceptions import TeamChangeNotAllowed

    brand = db.scalars(select(Brand).where(Brand.account_id == owner.account_id)).one()
    account = db.get_one(Account, owner.account_id)

    with pytest.raises(TeamChangeNotAllowed):
        team_service.hand_over(
            db,
            BrandAccess(brand, "admin"),
            account,
            brand.id,
            "Adhi",
            None,
            clock.now - timedelta(days=30),
            clock.now,
        )


def test_moved_blocks_keep_their_ids_and_when_they_were_placed(client, db, clock, owner):
    from app.modules.auth.models.creator import Creator
    from app.modules.safety.models import AccountBlock

    def block(by: User, creator: User) -> dict:
        creator_id = db.scalar(
            select(Creator.id).where(Creator.account_id == creator.account_id)
        )
        placed = client.post(
            "/api/v1/me/blocks", json={"creator_id": str(creator_id)}, headers=by.headers
        )
        assert placed.status_code == 201, placed.text
        return placed.json()

    only_the_brand, both = make_creator(db, clock), make_creator(db, clock)
    placed = block(owner, only_the_brand)
    block(owner, both)
    clock.advance(timedelta(hours=1))
    member = join(client, db, clock, owner, "campaigns", "Kavi")
    # The new owner had blocked one of them before joining: kept once, as theirs.
    db.add(
        AccountBlock(
            blocker_account_id=member.account_id,
            blocked_account_id=both.account_id,
            created_at=clock.now,
            updated_at=clock.now,
        )
    )
    db.flush()

    assert hand_over(client, owner, member.member_id).status_code == 200  # type: ignore[attr-defined]

    moved = db.get_one(AccountBlock, uuid.UUID(placed["id"]))
    assert moved.blocker_account_id == member.account_id
    assert moved.created_at == clock.now - timedelta(hours=1)
    assert (
        len(
            db.scalars(
                select(AccountBlock).where(
                    AccountBlock.blocked_account_id == both.account_id
                )
            ).all()
        )
        == 1
    )
    assert not db.scalars(
        select(AccountBlock).where(AccountBlock.blocker_account_id == owner.account_id)
    ).first()


def test_the_brand_s_takedowns_go_to_its_new_owner(client, db, clock, owner):
    from app.modules.safety.takedown_models import Takedown

    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))
    member = join(client, db, clock, owner, "campaigns", "Kavi")
    db.add(
        Takedown(
            subject_kind="brand",
            subject_id=brand_id,
            owner_account_id=owner.account_id,
            basis="court_order",
            issued_by="Madras High Court",
            order_reference="WP 1234 of 2026",
            reference_sealed=False,
            preserved={},
            withheld_at=clock.now,
            withheld_by_account_id=owner.account_id,
            received_at=clock.now,
            due_at=clock.now + timedelta(hours=3),
            created_at=clock.now,
            updated_at=clock.now,
        )
    )
    db.flush()

    assert hand_over(client, owner, member.member_id).status_code == 200  # type: ignore[attr-defined]

    assert (
        db.scalar(
            select(Takedown.owner_account_id).where(Takedown.subject_id == brand_id)
        )
        == member.account_id
    )


def test_naming_members_costs_no_query_per_notice(client, db, clock, owner):
    """Every member's name on a page of notices comes in one query, however many."""
    from tests.query_counts import queries_for

    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == owner.account_id))
    creator = make_creator(db, clock)

    def notify(count: int) -> None:
        for _ in range(count):
            account = team.create_account(db, "brand")
            member = BrandMember(
                brand_id=brand_id,
                account_id=account.id,
                role="campaigns",
                first_name=f"Ravi{uuid.uuid4().hex[:6]}",
                created_at=clock.now,
                updated_at=clock.now,
            )
            db.add(member)
            db.flush()
            db.add(
                Notification(
                    account_id=creator.account_id,
                    notification_type="proof_approved",
                    details={"acting_member_id": str(member.id)},
                    created_at=clock.now,
                    updated_at=clock.now,
                )
            )
        db.flush()

    notify(2)
    short = queries_for(client, "/api/v1/notifications", creator.headers)
    notify(18)
    long = queries_for(client, "/api/v1/notifications", creator.headers)

    assert short == long, f"{short} queries for 2 named notices, {long} for 20"
    names = {
        n["details"].get("acting_first_name")
        for n in client.get("/api/v1/notifications", headers=creator.headers).json()[
            "items"
        ]
    }
    assert len(names) == 20


def test_a_member_s_name_goes_only_to_creators(db, clock, owner):
    """A notice that names a person's act, sent to the brand's own side, names nobody."""
    from app.modules.auth import brand_access
    from app.modules.notifications import service as notifications

    brand = db.scalars(select(Brand).where(Brand.account_id == owner.account_id)).one()
    account = team.create_account(db, "brand")
    member = BrandMember(
        brand_id=brand.id,
        account_id=account.id,
        role="campaigns",
        first_name="Ravi",
        created_at=clock.now,
        updated_at=clock.now,
    )
    db.add(member)
    db.flush()
    brand_access.note_acting(db, brand_access.Acting(account.id, brand.id, member.id))

    notifications.record(
        db,
        account_id=owner.account_id,
        notification_type="memo_cancelled",
        now=clock.now,
        details={},
    )
    db.flush()

    [details] = db.scalars(
        select(Notification.details).where(Notification.account_id == owner.account_id)
    )
    assert "acting_member_id" not in details


def test_copying_to_a_whole_team_costs_no_statement_per_member(db, clock):
    """Twelve members' copies are written as one statement, as two members' are."""
    from app.modules.notifications import service as notifications
    from tests.query_counts import count_queries

    def statements(members: int) -> int:
        brand_owner = brand_user(db, clock)
        brand = db.scalars(
            select(Brand).where(Brand.account_id == brand_owner.account_id)
        ).one()
        for _ in range(members):
            db.add(
                BrandMember(
                    brand_id=brand.id,
                    account_id=team.create_account(db, "brand").id,
                    role="campaigns",
                    first_name="Ravi",
                    created_at=clock.now,
                    updated_at=clock.now,
                )
            )
        db.flush()
        with count_queries() as run:
            notifications.record(
                db,
                account_id=brand_owner.account_id,
                notification_type="application_received",
                now=clock.now,
                details={},
            )
            db.flush()
        copies = db.scalars(
            select(Notification.account_id).where(
                Notification.notification_type == "application_received",
                Notification.details["for_brand_id"].astext == str(brand.id),
            )
        ).all()
        assert len(copies) == members
        return len(run)

    assert statements(2) == statements(12)
