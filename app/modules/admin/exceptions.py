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


class TakedownSubjectNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "takedown_subject_not_found"
    title = "There is no creator, brand or campaign with that id"


class TakedownNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "takedown_not_found"
    title = "No such takedown"


class AlreadyWithheld(DomainError):
    # One active takedown per item (uq_takedown_active_subject): a second
    # order against the same item is added to the admin log's note, not as
    # a second takedown.
    status_code = HTTPStatus.CONFLICT
    code = "already_withheld"
    title = "This is already withheld"


class TakedownAlreadyLifted(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "takedown_already_lifted"
    title = "This takedown has already been lifted"


class OrderTimeNotPossible(DomainError):
    # The clock runs from `received_at`, so it must be a real moment: not
    # in the future, and not more than 30 days before now (takedown_clocks).
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "order_time_not_possible"
    title = "When the order reached us must be in the last 30 days, and not in the future"


class ReportNamesAnotherItem(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "report_names_another_item"
    title = "That report is about something else"
