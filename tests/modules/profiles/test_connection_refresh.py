"""Keeping connected accounts current (item 29 piece 2, D-134).

The rules worth proving: Instagram's token is renewed only once 30 days or
fewer remain (and a day after connecting), Google's each run; the count is
read again and dated; a platform that refuses expires the connection and
tells its creator exactly once; one that does not answer is left alone.
"""

from contextlib import nullcontext
from datetime import timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import settings
from app.modules.me import connection_jobs
from app.modules.notifications.models import Notification
from app.modules.profiles import connection_refresh_service as refresh
from app.modules.profiles.connection_models import ConnectedAccount
from tests.deal_flow import User, creator_user
from tests.modules.profiles.connections_world import profile
from tests.modules.profiles.test_connections_api import connected


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def run(db, clock) -> refresh.RefreshRun:
    return refresh.refresh_all(
        lambda: nullcontext(db), clock.now, connection_jobs.tell_creator
    )


def connection(db) -> ConnectedAccount:
    db.expire_all()
    return db.scalars(select(ConnectedAccount)).one()


def notices(db, user: User) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == "connection_expired",
            )
        ).all()
    )


def test_a_fresh_instagram_token_is_only_read(client, db, clock, creator, platforms):
    connected(client, creator, platforms, followers=24_000)
    platforms["instagram"].profiles["good-code"] = profile(followers=25_000)
    clock.advance(timedelta(days=2))

    assert run(db, clock) == refresh.RefreshRun(read=1, expired=0, unavailable=0)

    assert platforms["instagram"].refreshed == []
    found = connection(db)
    assert (found.verified_followers, found.verified_as_of) == (25_000, clock.now)


def test_an_instagram_token_is_renewed_thirty_days_before_it_lapses(
    client, db, clock, creator, platforms
):
    connected(client, creator, platforms)
    before = connection(db).token_expires_at
    clock.advance(timedelta(days=30))  # 30 of its 60 days left

    run(db, clock)

    assert platforms["instagram"].refreshed == ["access-for-good-code"]
    assert connection(db).token_expires_at == clock.now + timedelta(days=60) > before


def test_google_access_is_renewed_every_run(client, db, clock, creator, platforms):
    connected(client, creator, platforms, "youtube", code="yt")
    clock.advance(timedelta(hours=2))

    run(db, clock)

    assert platforms["youtube"].refreshed == ["access-for-yt"]


def test_a_refusing_platform_expires_the_connection_and_tells_once(
    client, db, clock, creator, platforms
):
    connected(client, creator, platforms)
    platforms["instagram"].refused = True
    clock.advance(timedelta(days=2))

    assert run(db, clock).expired == 1
    assert connection(db).status == "expired"
    (notice,) = notices(db, creator)
    assert notice.details == {"platform": "instagram"}

    clock.advance(timedelta(days=1))
    assert run(db, clock) == refresh.RefreshRun(read=0, expired=0, unavailable=0)
    assert len(notices(db, creator)) == 1


def test_a_silent_platform_leaves_the_connection_as_it_was(
    client, db, clock, creator, platforms
):
    body = connected(client, creator, platforms)
    platforms["instagram"].unavailable = True
    clock.advance(timedelta(days=2))

    assert run(db, clock).unavailable == 1
    found = connection(db)
    assert (found.status, found.verified_followers) == (
        "active",
        body["verified_followers"],
    )
    assert notices(db, creator) == []


def test_a_lapsed_instagram_token_expires_without_asking(
    client, db, clock, creator, platforms
):
    connected(client, creator, platforms)
    clock.advance(timedelta(days=61))

    assert run(db, clock).expired == 1
    assert platforms["instagram"].refreshed == []
    assert len(notices(db, creator)) == 1


def test_a_rotated_key_expires_the_connection(
    client, db, clock, creator, platforms, monkeypatch
):
    connected(client, creator, platforms)
    monkeypatch.setattr(
        settings, "platform_token_key", SecretStr("a-rotated-test-key-" * 2)
    )
    clock.advance(timedelta(days=2))

    assert run(db, clock).expired == 1


def test_switched_off_nothing_is_read(client, db, clock, creator, platforms, monkeypatch):
    connected(client, creator, platforms)
    monkeypatch.setattr(settings, "platform_connections_enabled", False)
    clock.advance(timedelta(days=2))

    assert run(db, clock) == refresh.RefreshRun(read=0, expired=0, unavailable=0)


def test_a_connection_changed_meanwhile_is_left_as_it_now_is(
    client, db, clock, creator, platforms
):
    connected(client, creator, platforms)
    found = connection(db)
    seen = found.updated_at
    found.updated_at = seen + timedelta(
        seconds=1
    )  # reconnected while the platform was asked
    db.flush()

    assert refresh._locked_if_unchanged(db, found.id, seen) is None


@pytest.mark.parametrize(
    ("platform", "age_days", "left_days", "renew"),
    [
        ("instagram", 0, 60, False),  # not a day old: Meta refuses to renew it
        ("instagram", 0, 10, False),  # not a day old, even with few days left
        ("instagram", 2, 58, False),
        ("instagram", 30, 30, True),
        ("instagram", 31, 29, True),
        ("instagram", 2, 10, True),
        ("youtube", 0, 0, True),
    ],
)
def test_when_a_token_is_renewed(clock, platform, age_days, left_days, renew):
    now = clock.now
    item = ConnectedAccount(
        platform=platform,
        connected_at=now - timedelta(days=age_days),
        token_expires_at=now + timedelta(days=left_days),
    )

    assert refresh.needs_renewal(item, now) is renew
