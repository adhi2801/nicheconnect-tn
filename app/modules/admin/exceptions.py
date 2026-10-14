"""Domain errors for the admin API and user reports (D-099)."""

from http import HTTPStatus

from app.core.errors import DomainError


class ReportSubjectNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "report_subject_not_found"
    title = "There is nothing with that id to report"


class CannotReportYourself(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "cannot_report_yourself"
    title = "You cannot report your own profile or campaign"


class AdminTargetNotAllowed(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "admin_target_not_allowed"
    title = "Admins are suspended and restored by a founder, not by another admin"


class AlreadySuspended(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "already_suspended"
    title = "This account is already suspended"


class NotSuspended(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "not_suspended"
    title = "This account is not suspended"


class ReportNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "report_not_found"
    title = "No such report"


class ReportAlreadyResolved(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "report_already_resolved"
    title = "This report has already been resolved"
