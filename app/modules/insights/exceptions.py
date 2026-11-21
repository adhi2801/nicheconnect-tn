"""Domain errors for the anonymous market figures (D-099)."""

from http import HTTPStatus

from app.core.errors import DomainError


class RateReportNotFound(DomainError):
    # An unpublished report reads exactly like one never built, so a quarter
    # waiting for an admin cannot be told from one with nothing in it.
    status_code = HTTPStatus.NOT_FOUND
    code = "rate_report_not_found"
    title = "There is no published rate report for that quarter"


class RateReportWithdrawn(DomainError):
    status_code = HTTPStatus.GONE
    code = "rate_report_withdrawn"
    title = "This rate report was withdrawn"


class RateReportNotBuilt(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "rate_report_not_built"
    title = "No rate report has been built for that quarter"


class RateReportAlreadyPublished(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "rate_report_already_published"
    title = "This rate report is already published"


class RateReportNotPublished(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "rate_report_not_published"
    title = "Only a published rate report can be withdrawn"


class RateReportAlreadyWithdrawn(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "rate_report_already_withdrawn"
    title = "This rate report was already withdrawn"


class RateReportNotWithdrawn(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "rate_report_not_withdrawn"
    title = "Only a quarter whose newest report was withdrawn can be built again"


class RateReportMethodUnchanged(DomainError):
    # A correction is a new method version: the same rules over the same
    # quarter would say what the withdrawn report said, from today's cards.
    status_code = HTTPStatus.CONFLICT
    code = "rate_report_method_unchanged"
    title = "A corrected report needs a newer method version than the one withdrawn"
