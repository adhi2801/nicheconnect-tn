"""Joining a campaign while the brand closes it (audit C11, D-180).

Applying checks "still open" and then writes. Until audit C11 it read the
campaign without a lock, so a close committed between the check and the
write left an application on a closed campaign. Now applying holds a shared
lock on the campaign until it commits, and closing (`change_status`, which
locks it for update) must wait for it, or applying waits for the close.

Which commit came first cannot be read from the final rows, so these prove
the lock itself. Each thread signals the moment its lock is taken, seen in
the SQL it sends, never a guessed sleep; a lock timeout is recognised by
PostgreSQL's own code (55P03, lock_not_available), never by message text.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, event, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import invitation_service as invitations
from app.modules.campaigns import offer_service as offers
from app.modules.campaigns import service as campaigns
from app.modules.campaigns.exceptions import CampaignNotOpen
from app.modules.campaigns.models import Application, Campaign
from app.modules.campaigns.offer_models import QuoteOffer
from app.modules.notifications.models import Notification
from tests.factories import (
    build_brand,
    build_campaign,
    build_creator,
    create_account,
    unique_test_phone,
)
from tests.modules.conftest import CONCURRENCY_NOW as NOW

LOCK_NOT_AVAILABLE = "55P03"
PITCH = {"pitch": "A Madurai food page, joining in a race test."}


@pytest.fixture
def world() -> Iterator[tuple[uuid.UUID, list[uuid.UUID]]]:
    """A committed open campaign and two creators who may apply: (campaign, creators)."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"join-close-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        accounts = [brand_account.id]
        creators = []
        for _ in range(2):
            account = create_account(session, "creator", phone=unique_test_phone())
            creator = build_creator(
                session, handle=f"jc{uuid.uuid4().hex[:12]}", account_id=account.id
            )
            session.add(creator)
            accounts.append(account.id)
            creators.append(creator)
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        session.commit()
        ids = (campaign.id, [c.id for c in creators], brand.id, accounts)
    try:
        yield ids[0], ids[1]
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Notification).where(Notification.account_id.in_(ids[3]))
            )
            session.execute(
                delete(QuoteOffer).where(
                    QuoteOffer.application_id.in_(
                        select(Application.id).where(Application.campaign_id == ids[0])
                    )
                )
            )
            session.execute(delete(Application).where(Application.campaign_id == ids[0]))
            session.execute(delete(Campaign).where(Campaign.id == ids[0]))
            session.execute(delete(Creator).where(Creator.id.in_(ids[1])))
            session.execute(delete(Brand).where(Brand.id == ids[2]))
            session.execute(delete(Account).where(Account.id.in_(ids[3])))
            session.commit()


def signal_when(session: Any, clause: str, done: threading.Event) -> None:
    """Set `done` once this session has sent a statement with `clause`."""
    connection: Connection = session.connection()

    def seen(conn, cursor, statement, parameters, context, executemany) -> None:
        if clause in statement:
            done.set()

    event.listen(connection, "after_cursor_execute", seen)


def run_both(*works: Callable[[], None]) -> None:
    threads = [threading.Thread(target=work) for work in works]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)


def timed_out(error: OperationalError) -> bool:
    return getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE


def test_a_close_waits_for_an_application_in_flight(world, slow_writes):
    campaign_id, (creator_id, _) = world
    locked = threading.Event()
    results: dict[str, object] = {}

    def apply() -> None:
        with SessionLocal() as session:
            signal_when(session, "FOR SHARE", locked)
            creator = session.get_one(Creator, creator_id)
            results["apply"] = campaigns.apply_to_campaign(
                session, campaign_id, creator, dict(PITCH), NOW
            ).status

    def close() -> None:
        assert locked.wait(timeout=10)
        with SessionLocal() as session:
            session.execute(text("SET LOCAL lock_timeout = '50ms'"))
            campaign = session.get_one(Campaign, campaign_id)
            try:
                campaigns.change_status(session, campaign, "closed", NOW)
                results["close"] = "closed at once"
            except OperationalError as error:
                session.rollback()
                results["close"] = "waited" if timed_out(error) else error

    run_both(apply, close)

    assert results == {"apply": "submitted", "close": "waited"}
    with SessionLocal() as session:  # once the application is in, it closes as usual
        campaign = session.get_one(Campaign, campaign_id)
        assert (
            campaigns.change_status(session, campaign, "closed", NOW).status == "closed"
        )


def test_an_application_after_a_close_in_flight_is_refused_cleanly(world, slow_writes):
    """The close goes first: the application waits for it, then reads the
    campaign closed and answers 409, never a raw database error."""
    campaign_id, (creator_id, _) = world
    locked = threading.Event()
    results: dict[str, object] = {}

    def close() -> None:
        with SessionLocal() as session:
            signal_when(session, "FOR UPDATE", locked)
            campaign = session.get_one(Campaign, campaign_id)
            results["close"] = campaigns.change_status(
                session, campaign, "closed", NOW
            ).status

    def apply() -> None:
        assert locked.wait(timeout=10)
        with SessionLocal() as session:
            creator = session.get_one(Creator, creator_id)
            try:
                campaigns.apply_to_campaign(
                    session, campaign_id, creator, dict(PITCH), NOW
                )
                results["apply"] = "applied to a closed campaign"
            except CampaignNotOpen:
                results["apply"] = "refused"

    run_both(close, apply)

    assert results == {"close": "closed", "apply": "refused"}


def test_two_creators_applying_at_once_never_wait_for_each_other(world, slow_writes):
    """A shared lock: the second applicant, with a 50 ms lock timeout, still
    gets in while the first holds the campaign."""
    campaign_id, (first, second) = world
    locked = threading.Event()
    results: dict[str, object] = {}

    def apply_first() -> None:
        with SessionLocal() as session:
            signal_when(session, "FOR SHARE", locked)
            creator = session.get_one(Creator, first)
            results["first"] = campaigns.apply_to_campaign(
                session, campaign_id, creator, dict(PITCH), NOW
            ).status

    def apply_second() -> None:
        assert locked.wait(timeout=10)
        with SessionLocal() as session:
            session.execute(text("SET LOCAL lock_timeout = '50ms'"))
            creator = session.get_one(Creator, second)
            try:
                results["second"] = campaigns.apply_to_campaign(
                    session, campaign_id, creator, dict(PITCH), NOW
                ).status
            except OperationalError as error:
                session.rollback()
                results["second"] = "blocked" if timed_out(error) else error

    run_both(apply_first, apply_second)

    assert results == {"first": "submitted", "second": "submitted"}


# The independent review of audit C11: the two other ways in took the same
# shared lock, but no test failed when it was removed from either.
def committed_application(
    campaign_id: uuid.UUID, creator_id: uuid.UUID, status: str
) -> uuid.UUID:
    """An invitation (`invited`) or an application (`submitted`), committed."""
    with SessionLocal() as session:
        application = Application(
            campaign_id=campaign_id,
            creator_id=creator_id,
            origin="invited" if status == "invited" else "applied",
            pitch=None if status == "invited" else PITCH["pitch"],
            status=status,
            status_changed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(application)
        session.commit()
        return application.id


def close_waits_for(
    campaign_id: uuid.UUID, join: Callable[[Any], str]
) -> dict[str, object]:
    """Run `join` until it holds the campaign's shared lock, then try to close
    the campaign with a 50 ms lock timeout: it must wait."""
    locked = threading.Event()
    results: dict[str, object] = {}

    def joining() -> None:
        with SessionLocal() as session:
            signal_when(session, "FOR SHARE", locked)
            results["join"] = join(session)

    def close() -> None:
        assert locked.wait(timeout=10)
        with SessionLocal() as session:
            session.execute(text("SET LOCAL lock_timeout = '50ms'"))
            campaign = session.get_one(Campaign, campaign_id)
            try:
                campaigns.change_status(session, campaign, "closed", NOW)
                results["close"] = "closed at once"
            except OperationalError as error:
                session.rollback()
                results["close"] = "waited" if timed_out(error) else error

    run_both(joining, close)
    return results


def test_a_close_waits_for_an_invitation_being_accepted(world, slow_writes):
    campaign_id, (creator_id, _) = world
    invitation_id = committed_application(campaign_id, creator_id, "invited")

    def accept(session: Any) -> str:
        invitation = session.get_one(Application, invitation_id)
        return invitations.accept_invitation(session, invitation, NOW).status

    assert close_waits_for(campaign_id, accept) == {"join": "accepted", "close": "waited"}


def test_a_close_waits_for_an_offer_being_made(world, slow_writes):
    campaign_id, (creator_id, _) = world
    application_id = committed_application(campaign_id, creator_id, "submitted")

    def offer(session: Any) -> str:
        application = session.get_one(Application, application_id)
        offers.make_offer(session, application, "creator", 700_000, None, NOW)
        return "offered"

    assert close_waits_for(campaign_id, offer) == {"join": "offered", "close": "waited"}
