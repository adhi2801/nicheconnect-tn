"""Domain errors for disputes."""

from http import HTTPStatus

from app.core.errors import DomainError


class DisputeNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "dispute_not_found"
    title = "There is no dispute on this payment"


class DisputeAlreadyOpen(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "dispute_already_open"
    title = "This payment already has a dispute"


class DisputeAlreadyClosed(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "dispute_already_closed"
    title = "This dispute has already been closed"


class NotADisputeParty(DomainError):
    status_code = HTTPStatus.FORBIDDEN
    code = "not_a_dispute_party"
    title = "Only the two sides of this deal can use this dispute"


class UnknownDisputeOutcome(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "unknown_dispute_outcome"
    title = "That is not an outcome we record"
