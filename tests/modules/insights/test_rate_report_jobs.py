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


@pytest.mark.parametrize("switched_on", [False, True])
def test_a_run_builds_the_last_closed_quarter_with_the_setting(monkeypatch, switched_on):
    asked = []

    def build_due(db, now, *, agreed_fees):
        asked.append((now, agreed_fees))
        return service.BuildRun(quarter="2026-Q3", built=True)

    monkeypatch.setattr(service, "build_due", build_due)
    monkeypatch.setattr(settings, "rate_report_agreed_fees", switched_on)

    run = jobs.run_build(TWO_DAYS_ON)

    assert run == service.BuildRun(quarter="2026-Q3", built=True)
    assert asked == [(TWO_DAYS_ON, switched_on)]


def failing(monkeypatch) -> None:
    def build_due(db, now, *, agreed_fees):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(service, "build_due", build_due)


def test_a_failure_soon_after_the_quarter_is_raised_for_a_retry(monkeypatch, caplog):
    failing(monkeypatch)

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        jobs.run_build(TWO_DAYS_ON)

    assert "rate_report.overdue" not in caplog.text


def test_a_quarter_three_days_closed_and_still_unbuilt_is_an_error(monkeypatch, caplog):
    failing(monkeypatch)

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        jobs.run_build(THREE_DAYS_ON)

    assert "rate_report.overdue quarter=2026-Q3" in caplog.text
