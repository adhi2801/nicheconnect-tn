"""Publishing and withdrawing the quarterly city rate report, for the admins (item 84, D-200).

The rules are `insights.rate_report_service`'s; this adds what only an admin
does, and the admin log: every publish and withdrawal is written there in
the same transaction, with the quarter and, for a withdrawal, the reason,
so "who published this figure?" always has an answer (D-061).
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.admin.admin_service import log_action
from app.modules.auth.models.account import Account
from app.modules.insights import rate_report_service
from app.modules.insights.rate_report_models import CityRateReport


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
