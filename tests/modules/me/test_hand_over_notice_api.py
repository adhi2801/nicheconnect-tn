"""Telling creators when a brand changes hands (item 13, D-151).

The rules worth proving: every creator with a deal still unfinished with the
brand is told, once however many deals, with how many; a creator whose deals
are all finished is not; nobody is told of a hand-over that did not happen;
the new owner's first name is read from their membership, so it goes when
that membership is erased; and nobody can mute it.
"""

from sqlalchemy import select

from app.modules.auth.models.brand_team import BrandMember
from app.modules.notifications.models import Notification
from tests.deal_flow import MEMOS_URL, PAYMENT_REFERENCE, User, accepted_memo
from tests.deal_flow import creator_user as make_creator
from tests.modules.me import test_team_api as team
from tests.modules.me import test_team_piece2_api as piece2

owner = team.owner
join = team.join
problem = team.problem
hand_over = piece2.hand_over
shown_to = piece2.shown_to
NOTICE = "brand_changed_hands"


def told(db, user: User) -> int:
    return len(
        db.scalars(
            select(Notification.id).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == NOTICE,
            )
        ).all()
    )


def finished_deal(client, db, clock, brand: User) -> User:
    """A creator whose only deal with the brand is paid and confirmed."""
    creator = make_creator(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof = piece2.submit_proof(client, memo_id, creator)
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=brand.headers)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": PAYMENT_REFERENCE},
        headers=brand.headers,
    )
    confirmed = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers
    )
    assert confirmed.status_code == 200, confirmed.text
    return creator


def test_creators_with_an_unfinished_deal_are_told_once_and_by_name(
    client, db, clock, owner, unlimited
):
    waiting = make_creator(db, clock)
    accepted_memo(client, owner, waiting)
    accepted_memo(client, owner, waiting)  # a second deal: still one notice
    done = finished_deal(client, db, clock, owner)
    stranger = make_creator(db, clock)
    taker = join(client, db, clock, owner, "campaigns", "Kavi")

    handed = hand_over(client, owner, taker.member_id)  # type: ignore[attr-defined]

    assert handed.status_code == 200, handed.text
    assert told(db, waiting) == 1
    details = shown_to(client, waiting, NOTICE)
    assert details["unfinished_deals"] == 2
    assert details["new_owner_first_name"] == "Kavi"
    assert "new_owner_member_id" not in details
    assert (told(db, done), told(db, stranger)) == (0, 0)


def test_a_hand_over_refused_tells_nobody(client, db, clock, owner):
    waiting = make_creator(db, clock)
    accepted_memo(client, owner, waiting)
    taker = join(client, db, clock, owner, "campaigns", "Kavi")

    refused = client.post(
        piece2.OWNERSHIP,
        json={"member_id": taker.member_id, "your_first_name": "Adhi"},  # type: ignore[attr-defined]
        headers=owner.headers,
    )

    problem(refused, 401, "step_up_required")
    assert told(db, waiting) == 0


def test_the_new_owner_s_name_goes_with_their_membership(client, db, clock, owner):
    """Read when the notice is (D-150), so erasing the person erases the name."""
    waiting = make_creator(db, clock)
    accepted_memo(client, owner, waiting)
    taker = join(client, db, clock, owner, "campaigns", "Kavi")
    assert hand_over(client, owner, taker.member_id).status_code == 200  # type: ignore[attr-defined]

    db.execute(
        BrandMember.__table__.delete().where(BrandMember.account_id == taker.account_id)
    )
    db.flush()

    details = shown_to(client, waiting, NOTICE)
    assert "new_owner_first_name" not in details
    assert details["brand_name"]


def test_nobody_can_mute_it(client, db, clock):
    response = client.put(
        "/api/v1/me/notification-preferences",
        json={
            "quiet_from": None,
            "quiet_until": None,
            "digest": "off",
            "digest_hour": 9,
            "muted_types": [NOTICE],
        },
        headers=make_creator(db, clock).headers,
    )

    problem(response, 422, "urgent_type_not_mutable")


def test_many_creators_told_cost_no_query_each(client, db, clock, owner, unlimited):
    """However many are told, the hand-over runs the same number of statements."""
    from tests.query_counts import count_queries
    from tests.step_up import with_code

    def statements(creators: int) -> int:
        brand = piece2.brand_user(db, clock)
        for _ in range(creators):
            accepted_memo(client, brand, make_creator(db, clock))
        taker = join(client, db, clock, brand, "campaigns", "Kavi")
        mid = taker.member_id  # type: ignore[attr-defined]
        headers = with_code(
            client, brand.headers, "change_team", change=f"ownership:{mid}"
        )
        with count_queries() as run:
            handed = client.post(
                piece2.OWNERSHIP,
                json={"member_id": mid, "your_first_name": "Adhi"},
                headers=headers,
            )
        assert handed.status_code == 200, handed.text
        return len(run)

    assert statements(1) == statements(6)
