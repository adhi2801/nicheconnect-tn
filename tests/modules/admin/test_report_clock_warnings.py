"""The admins are warned before a report's deadline, and when it passes (item 51).

The warning run is called directly with the test's clock, as the scheduled
job calls it (report_clock_jobs.run_warnings).
"""

import logging
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.modules.admin import report_clock_service as service
from app.modules.admin.models.report import Report
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.notifications.models import Notification
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import create_account

NOTE = "This page copies my photos and my name, please remove it."


@pytest.fixture
def admins(db, clock) -> list[User]:
    """Two active admins and a suspended one, committed inside the test's
    outer transaction so the service's own commits keep them."""
    active = [create_account(db, "admin") for _ in range(2)]
    suspended = create_account(db, "admin")
    db.execute(
        update(Account)
        .where(Account.id == suspended.id)
        .values(suspended_at=clock.now, suspension_reason="other")
    )
    db.commit()
    return [User(a.id, "admin", clock) for a in active]


def file_report(client, db, clock, category: str = "impersonation") -> tuple[dict, User]:
    reporter = brand_user(db, clock)
    subject = creator_user(db, clock)
    subject_id = db.scalar(
        select(Creator.id).where(Creator.account_id == subject.account_id)
    )
    response = client.post(
        "/api/v1/reports",
        json={
            "subject_kind": "creator",
            "subject_id": str(subject_id),
            "category": category,
            "note": NOTE,
        },
        headers=reporter.headers,
    )
    assert response.status_code == 201, response.text
    return response.json(), reporter


def warnings_to(db, account_id) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(
                Notification.account_id == account_id,
                Notification.notification_type.in_(("report_due_soon", "report_overdue")),
            )
            .order_by(Notification.created_at, Notification.id)
        ).all()
    )


def test_a_report_due_within_thirty_minutes_warns_every_active_admin_once(
    client, db, clock, admins
):
    filed, _ = file_report(client, db, clock)  # due in 2 hours

    clock.advance(timedelta(hours=1, minutes=29))
    too_early = service.warn_admins(db, clock.now)
    clock.advance(timedelta(minutes=1))  # due in exactly 30 minutes
    warned = service.warn_admins(db, clock.now)
    clock.advance(timedelta(minutes=5))
    again = service.warn_admins(db, clock.now)

    assert too_early == service.WarningRun(due_soon=0, overdue=0)
    assert warned == service.WarningRun(due_soon=1, overdue=0)
    assert again == service.WarningRun(due_soon=0, overdue=0)
    for admin in admins:
        [told] = warnings_to(db, admin.account_id)
        assert told.notification_type == "report_due_soon"
        assert told.details == {
            "report_id": filed["id"],
            "category": "impersonation",
            "due_at": filed["due_at"],
        }
    suspended = db.scalars(
        select(Account.id).where(
            Account.role == "admin", Account.suspended_at.is_not(None)
        )
    ).all()
    assert all(warnings_to(db, admin_id) == [] for admin_id in suspended)


def test_a_report_past_its_deadline_unanswered_warns_again_once(
    client, db, clock, admins
):
    filed, _ = file_report(client, db, clock)
    clock.advance(timedelta(hours=1, minutes=35))
    service.warn_admins(db, clock.now)

    clock.advance(timedelta(minutes=25))  # exactly at the deadline: still in time
    at_deadline = service.warn_admins(db, clock.now)
    clock.advance(timedelta(minutes=5))
    late = service.warn_admins(db, clock.now)
    clock.advance(timedelta(hours=6))
    later = service.warn_admins(db, clock.now)

    assert at_deadline == service.WarningRun(due_soon=0, overdue=0)
    assert late == service.WarningRun(due_soon=0, overdue=1)
    assert later == service.WarningRun(due_soon=0, overdue=0)
    kinds = [n.notification_type for n in warnings_to(db, admins[0].account_id)]
    assert kinds == ["report_due_soon", "report_overdue"]
    row = db.get(Report, filed["id"])
    db.refresh(row)
    assert row.overdue_alerted_at == clock.now - timedelta(hours=6)


def test_a_report_found_already_late_is_warned_as_late_only(client, db, clock, admins):
    """The job was down through the 30 minutes: that moment has passed."""
    filed, _ = file_report(client, db, clock)

    clock.advance(timedelta(hours=3))
    run = service.warn_admins(db, clock.now)

    assert run == service.WarningRun(due_soon=0, overdue=1)
    assert [n.notification_type for n in warnings_to(db, admins[0].account_id)] == [
        "report_overdue"
    ]
    row = db.get(Report, filed["id"])
    db.refresh(row)
    assert row.due_soon_alerted_at == row.overdue_alerted_at == clock.now


def test_a_report_answered_in_time_is_never_warned_about(client, db, clock, admins):
    filed, _ = file_report(client, db, clock)
    clock.advance(timedelta(hours=1))
    resolved = client.post(
        f"/api/v1/admin/reports/{filed['id']}/resolve",
        json={"outcome": "actioned", "note": "Removed the copied photos."},
        headers=admins[0].headers,
    )
    assert resolved.status_code == 200, resolved.text

    clock.advance(timedelta(days=8))

    assert service.warn_admins(db, clock.now) == service.WarningRun(due_soon=0, overdue=0)
    assert warnings_to(db, admins[0].account_id) == []


def test_each_report_is_warned_about_on_its_own_clock(client, db, clock, admins):
    file_report(client, db, clock, "impersonation")  # 2 hours
    file_report(client, db, clock, "abuse")  # 36 hours
    file_report(client, db, clock, "non_payment")  # 7 days

    clock.advance(timedelta(hours=35, minutes=40))
    run = service.warn_admins(db, clock.now)

    assert run == service.WarningRun(due_soon=1, overdue=1)
    categories = sorted(
        n.details["category"] for n in warnings_to(db, admins[0].account_id)
    )
    assert categories == ["abuse", "impersonation"]


def test_a_burst_larger_than_a_batch_is_warned_about_in_one_run(
    client, db, clock, admins, monkeypatch
):
    monkeypatch.setattr(service, "BATCH", 2)
    for _ in range(5):
        file_report(client, db, clock)

    clock.advance(timedelta(hours=1, minutes=45))
    run = service.warn_admins(db, clock.now)

    assert run == service.WarningRun(due_soon=5, overdue=0)
    assert len(warnings_to(db, admins[1].account_id)) == 5


def test_a_run_always_ends_and_leaves_the_rest_to_the_next(
    client, db, clock, admins, monkeypatch
):
    monkeypatch.setattr(service, "BATCH", 1)
    monkeypatch.setattr(service, "MAX_BATCHES", 2)
    for _ in range(3):
        file_report(client, db, clock)
    clock.advance(timedelta(hours=1, minutes=45))

    first = service.warn_admins(db, clock.now)
    clock.advance(timedelta(minutes=5))
    second = service.warn_admins(db, clock.now)

    assert first == service.WarningRun(due_soon=2, overdue=0)
    assert second == service.WarningRun(due_soon=1, overdue=0)


def test_the_warning_reaches_error_tracking_and_names_nobody(
    client, db, clock, admins, caplog
):
    filed, reporter = file_report(client, db, clock)
    clock.advance(timedelta(hours=1, minutes=40))

    with caplog.at_level(logging.ERROR, logger=service.logger.name):
        service.warn_admins(db, clock.now)

    [record] = caplog.records
    assert record.levelno == logging.ERROR  # what error tracking sends (D-074)
    message = record.getMessage()
    assert message == (
        f"report.due_soon report_id={filed['id']} category=impersonation "
        f"due_at={filed['due_at']}"
    )
    assert "photos" not in message
    assert str(reporter.account_id) not in message
    assert filed["subject_id"] not in message


def test_late_and_due_soon_are_told_apart_by_error_tracking(
    client, db, clock, admins, caplog
):
    """Sentry groups by the template, so each stage needs its own (D-074)."""
    file_report(client, db, clock)
    clock.advance(timedelta(hours=1, minutes=40))
    with caplog.at_level(logging.ERROR, logger=service.logger.name):
        service.warn_admins(db, clock.now)
        clock.advance(timedelta(hours=1))
        service.warn_admins(db, clock.now)

    templates = [record.msg for record in caplog.records]
    assert len(templates) == 2
    assert templates[0].startswith("report.due_soon ")
    assert templates[1].startswith("report.overdue ")


@pytest.mark.parametrize("warning", ["report_due_soon", "report_overdue"])
def test_the_admins_cannot_mute_either_warning(client, db, admins, warning):
    response = client.put(
        "/api/v1/me/notification-preferences",
        json={
            "quiet_from": None,
            "quiet_until": None,
            "digest": "off",
            "digest_hour": 9,
            "muted_types": [warning],
        },
        headers=admins[0].headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "urgent_type_not_mutable"
