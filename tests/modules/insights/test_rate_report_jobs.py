"""The daily build of the rate report, without DBOS (item 84, D-200).

DBOS's schedule and workflow are tested with the other jobs, in
`tests/core/test_jobs.py`; this is what one run does.
"""

import logging
from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.modules.insights import rate_report_jobs as jobs
from app.modules.insights import rate_report_service as service

# Q3 2026 closed at midnight ending 30 September in Tamil Nadu; these are
# 06:00 there, two and three days on.
TWO_DAYS_ON = datetime(2026, 10, 3, 0, 30, tzinfo=UTC)
THREE_DAYS_ON = datetime(2026, 10, 4, 0, 30, tzinfo=UTC)
# A retry, later the same morning than its schedule.
RETRIED_AT = datetime(2026, 10, 3, 0, 41, 7, tzinfo=UTC)


@pytest.mark.parametrize("switched_on", [False, True])
def test_a_run_builds_the_last_closed_quarter_with_the_setting(monkeypatch, switched_on):
    asked = []

    def build_due(db, now, *, built_at, agreed_fees):
        asked.append((now, built_at, agreed_fees))
        return service.BuildRun(quarter="2026-Q3", built=True)

    monkeypatch.setattr(service, "build_due", build_due)
    monkeypatch.setattr(settings, "rate_report_agreed_fees", switched_on)

    run = jobs.run_build(TWO_DAYS_ON, clock=lambda: RETRIED_AT)

    assert run == service.BuildRun(quarter="2026-Q3", built=True)
    # The schedule decides the quarter; the clock says when it was built.
    assert asked == [(TWO_DAYS_ON, RETRIED_AT, switched_on)]


def test_a_run_reads_the_real_clock_by_default(monkeypatch):
    asked = []

    def build_due(db, now, *, built_at, agreed_fees):
        asked.append(built_at)
        return service.BuildRun(quarter="2026-Q3", built=False)

    monkeypatch.setattr(service, "build_due", build_due)
    before = datetime.now(UTC)

    jobs.run_build(TWO_DAYS_ON)

    [built_at] = asked
    assert before <= built_at <= datetime.now(UTC)


def failing(monkeypatch) -> None:
    def build_due(db, now, *, built_at, agreed_fees):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(service, "build_due", build_due)


@pytest.mark.parametrize("scheduled_at", [TWO_DAYS_ON, THREE_DAYS_ON])
def test_a_failed_try_is_raised_for_a_retry_and_never_an_error(
    monkeypatch, caplog, scheduled_at
):
    """Whether a report is overdue is the run's check, said once a run; a
    try failing, retried up to three times, is a warning each time."""
    failing(monkeypatch)

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError):
        jobs.run_build(scheduled_at)

    assert "rate_report.run_failed error=RuntimeError" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def checked(monkeypatch, found: service.Health) -> list[datetime]:
    asked: list[datetime] = []

    def health(db, now):
        asked.append(now)
        return found

    monkeypatch.setattr(service, "health", health)
    return asked


def test_the_check_logs_overdue_quarters_in_one_error(monkeypatch, caplog):
    asked = checked(
        monkeypatch, service.Health(overdue=["2026-Q2", "2026-Q3"], unpublished=[])
    )

    with caplog.at_level(logging.ERROR):
        jobs.run_check(THREE_DAYS_ON)

    assert asked == [THREE_DAYS_ON]
    assert [record.getMessage() for record in caplog.records] == [
        "rate_report.overdue quarters=2026-Q2,2026-Q3"
    ]


def test_the_check_logs_reports_waiting_to_be_published(monkeypatch, caplog):
    checked(monkeypatch, service.Health(overdue=[], unpublished=["2026-Q2"]))

    with caplog.at_level(logging.ERROR):
        jobs.run_check(THREE_DAYS_ON)

    assert [record.getMessage() for record in caplog.records] == [
        "rate_report.unpublished quarters=2026-Q2 days=14"
    ]


def test_a_healthy_check_logs_no_error(monkeypatch, caplog):
    checked(monkeypatch, service.Health(overdue=[], unpublished=[]))

    with caplog.at_level(logging.ERROR):
        jobs.run_check(THREE_DAYS_ON)

    assert caplog.records == []
