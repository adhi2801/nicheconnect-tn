"""Notification preferences: the delivery rule, the API, and the database (D-079)."""

from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.clock import IST
from app.modules.notifications.preference_models import (
    MUTABLE_TYPES,
    URGENT_TYPES,
    NotificationPreference,
)
from app.modules.notifications.preference_service import (
    DEFAULTS,
    DIGEST,
    HELD,
    IN_APP_ONLY,
    NOW,
    Delivery,
    Preferences,
    decide,
)
from tests.deal_flow import brand_user, creator_user
from tests.factories import create_account

URL = "/api/v1/me/notification-preferences"


def at(hour: int, minute: int = 0) -> datetime:
    """A moment on 8 October 2026, Tamil Nadu time."""
    return datetime(2026, 10, 8, hour, minute, tzinfo=IST)


def prefs(**changes: object) -> Preferences:
    values = {**DEFAULTS.__dict__, **changes}
    return Preferences(**values)  # type: ignore[arg-type]


# --- the rule ------------------------------------------------------------------------------


@pytest.mark.parametrize("urgent", URGENT_TYPES)
def test_urgent_goes_now_even_at_three_in_the_morning(urgent):
    everything_off = prefs(digest="daily", muted_types=MUTABLE_TYPES)

    assert decide(everything_off, urgent, at(3)) == Delivery(NOW)


def test_by_default_a_late_night_notification_waits_until_eight():
    found = decide(DEFAULTS, "application_received", at(23, 30))

    assert found.how == HELD
    assert found.send_at == datetime(2026, 10, 9, 8, 0, tzinfo=IST)


def test_quiet_hours_after_midnight_end_the_same_morning():
    found = decide(DEFAULTS, "application_received", at(2))

    assert found == Delivery(HELD, datetime(2026, 10, 8, 8, 0, tzinfo=IST))


@pytest.mark.parametrize("moment", [at(8), at(12), at(21, 59)])
def test_outside_quiet_hours_it_goes_now(moment):
    assert decide(DEFAULTS, "application_received", moment) == Delivery(NOW)


def test_a_daytime_quiet_window_works_too():
    lunch = prefs(quiet_from=time(13), quiet_until=time(15))

    assert decide(lunch, "proof_approved", at(14)).how == HELD
    assert decide(lunch, "proof_approved", at(15)).how == NOW


def test_no_quiet_hours_means_never_held():
    assert (
        decide(prefs(quiet_from=None, quiet_until=None), "proof_approved", at(3)).how
        == NOW
    )


def test_muted_stays_in_the_app():
    found = decide(prefs(muted_types=("proof_approved",)), "proof_approved", at(12))

    assert found == Delivery(IN_APP_ONLY)


def test_the_digest_collects_for_the_next_digest_hour():
    daily = prefs(digest="daily", digest_hour=19)

    assert decide(daily, "proof_approved", at(12)) == Delivery(
        DIGEST, datetime(2026, 10, 8, 19, 0, tzinfo=IST)
    )
    assert decide(daily, "proof_approved", at(20)).send_at == datetime(
        2026, 10, 9, 19, 0, tzinfo=IST
    )


def test_the_rule_reads_the_clock_in_tamil_nadu_whatever_zone_it_is_given():
    utc_evening = datetime(2026, 10, 8, 17, 0, tzinfo=UTC)  # 22:30 in Tamil Nadu

    assert decide(DEFAULTS, "proof_approved", utc_evening).how == HELD


def test_every_type_is_either_urgent_or_mutable():
    from app.modules.notifications.models import NOTIFICATION_TYPES

    assert set(URGENT_TYPES) | set(MUTABLE_TYPES) == set(NOTIFICATION_TYPES)
    assert not set(URGENT_TYPES) & set(MUTABLE_TYPES)


# --- the API -------------------------------------------------------------------------------


def body(**changes: object) -> dict:
    values: dict[str, object] = {
        "quiet_from": "23:00",
        "quiet_until": "07:30",
        "digest": "off",
        "digest_hour": 19,
        "muted_types": ["application_withdrawn"],
    }
    values.update(changes)
    return values


def test_a_new_account_reads_the_defaults(client, db, clock):
    response = client.get(URL, headers=creator_user(db, clock).headers)

    assert response.status_code == 200
    assert response.json() == {
        "quiet_from": "22:00",
        "quiet_until": "08:00",
        "digest": "off",
        "digest_hour": 19,
        "muted_types": [],
        "always_sent": list(URGENT_TYPES),
        "is_default": True,
        "saved_at": None,
    }


def test_saving_replaces_them_and_reads_back(client, db, clock):
    user = brand_user(db, clock)

    saved = client.put(URL, json=body(), headers=user.headers)
    read = client.get(URL, headers=user.headers)

    assert saved.status_code == 200, saved.text
    assert read.json() == saved.json()
    assert read.json()["quiet_from"] == "23:00"
    assert read.json()["muted_types"] == ["application_withdrawn"]
    assert read.json()["is_default"] is False


def test_saving_twice_keeps_one_set(client, db, clock):
    user = creator_user(db, clock)
    client.put(URL, json=body(), headers=user.headers)
    client.put(
        URL,
        json=body(quiet_from=None, quiet_until=None, digest="daily"),
        headers=user.headers,
    )

    read = client.get(URL, headers=user.headers).json()

    assert (read["quiet_from"], read["digest"]) == (None, "daily")
    assert (
        db.query(NotificationPreference).filter_by(account_id=user.account_id).count()
        == 1
    )


def test_one_persons_settings_never_touch_anothers(client, db, clock):
    first, second = creator_user(db, clock), creator_user(db, clock)
    client.put(URL, json=body(digest="daily"), headers=first.headers)

    assert client.get(URL, headers=second.headers).json()["is_default"] is True


def test_an_urgent_type_cannot_be_muted(client, db, clock):
    response = client.put(
        URL,
        json=body(muted_types=["payment_marked_paid"]),
        headers=creator_user(db, clock).headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "urgent_type_not_mutable"
    assert "payment_marked_paid" in response.json()["detail"]


@pytest.mark.parametrize(
    "changes",
    [
        {"quiet_from": "22:00", "quiet_until": None},
        {"quiet_from": "22:00", "quiet_until": "22:00"},
        {"quiet_from": "22:00:30"},
        {"digest": "weekly"},
        {"digest_hour": 24},
        {"muted_types": ["not_a_type"]},
        {"surprise": True},
    ],
)
def test_a_bad_set_is_refused(client, db, clock, changes):
    response = client.put(
        URL, json=body(**changes), headers=creator_user(db, clock).headers
    )

    assert response.status_code == 422


def test_it_needs_a_login(client):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json=body()).status_code == 401


def test_they_are_in_the_data_export(client, db, clock):
    user = creator_user(db, clock)
    client.put(URL, json=body(), headers=user.headers)

    export = client.get("/api/v1/me/export", headers=user.headers).json()

    section = export["data"]["notification_preferences"]
    assert section[0]["quiet_from"] == "23:00"
    assert section[0]["muted_types"] == ["application_withdrawn"]


# --- the database --------------------------------------------------------------------------


def test_the_database_itself_refuses_a_muted_urgent_type(db):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match="muted_types_allowed"):
        db.execute(
            text(
                "INSERT INTO notification_preference (account_id, muted_types) "
                "VALUES (:account, ARRAY['memo_sent']::varchar[])"
            ),
            {"account": account.id},
        )
        db.flush()


def test_the_database_refuses_half_a_quiet_window(db):
    account = create_account(db, "creator")

    with pytest.raises(IntegrityError, match="quiet_hours_whole"):
        db.add(NotificationPreference(account_id=account.id, quiet_from=time(22)))
        db.flush()


def test_saved_at_moves_with_each_save(client, db, clock):
    user = creator_user(db, clock)
    first = client.put(URL, json=body(), headers=user.headers).json()["saved_at"]
    clock.advance(timedelta(minutes=5))

    second = client.put(URL, json=body(), headers=user.headers).json()["saved_at"]

    assert second > first
