"""Reading, publishing, withdrawing and building again the quarterly city
rate report, for the admins (item 84, D-200, D-201).

The rules are `insights.rate_report_service`'s; this adds what only an admin
does, and the admin log: every read, publish, withdrawal and rebuild is
written there in the same transaction, with the quarter and, for a
withdrawal, the reason, so "who published this figure, and who looked at it
first?" always has an answer (D-061). A read is logged as account reads are
(`view_account`), as `view_rate_report`, but asks no reason: a report holds
no one's personal data.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.admin.admin_service import log_action
from app.modules.auth.models.account import Account
from app.modules.insights import rate_report_service
from app.modules.insights.rate_report_models import CityRateReport


def read(
    db: Session,
    admin: Account,
    quarter: str,
    now: datetime,
    method_version: int | None = None,
) -> CityRateReport:
    """A report in any state, body included, logged as read. Commits.

    Raises RateReportNotBuilt.
    """
    report = rate_report_service.read_any(db, quarter, method_version)
    log_action(
        db,
        admin,
        "view_rate_report",
        now,
        note=f"Read the {quarter} report, method version {report.method_version}.",
    )
    db.commit()
    return report


def rebuild(db: Session, admin: Account, quarter: str, now: datetime) -> CityRateReport:
    """Build a withdrawn quarter again under the current method, and log it.
    Commits. Raises RateReportNotBuilt, RateReportNotWithdrawn and
    RateReportMethodUnchanged."""
    report = rate_report_service.rebuild(
        db, quarter, now, agreed_fees=settings.rate_report_agreed_fees
    )
    log_action(
        db,
        admin,
        "rebuild_rate_report",
        now,
        note=(
            f"Built the {quarter} report again, method version "
            f"{report.method_version}, to replace the withdrawn one."
        ),
    )
    db.commit()
    return report


def publish(db: Session, admin: Account, quarter: str, now: datetime) -> CityRateReport:
    """Publish a built report and log it. Commits.

    Raises RateReportNotBuilt and RateReportAlreadyPublished.
    """
    report = rate_report_service.publish(db, admin.id, quarter, now)
    log_action(
        db, admin, "publish_rate_report", now, note=f"Published the {quarter} report."
    )
    db.commit()
    return report


def withdraw(
    db: Session, admin: Account, quarter: str, reason: str, now: datetime
) -> CityRateReport:
    """Withdraw a published report and log it, with its reason. Commits.

    Raises RateReportNotBuilt, RateReportNotPublished and
    RateReportAlreadyWithdrawn.
    """
    report = rate_report_service.withdraw(db, quarter, reason, now)
    log_action(
        db,
        admin,
        "withdraw_rate_report",
        now,
        note=f"Withdrew the {quarter} report: {reason}",
    )
    db.commit()
    return report
