"""Domain errors for payment records."""

from http import HTTPStatus

from app.core.errors import DomainError


class PaymentRecordExists(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "payment_record_exists"
    title = "This deal memo already has a payment record"


class PaymentRecordNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "payment_record_not_found"
    title = "No payment record for this deal memo"


class PaymentAlreadyMarkedPaid(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "payment_already_marked_paid"
    title = "This payment is already marked as sent"


class PaymentAlreadyConfirmed(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "payment_already_confirmed"
    title = "This payment is already confirmed as received"


class PaymentNotMarkedPaid(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "payment_not_marked_paid"
    title = "The brand has not marked this payment as sent yet"


class UnknownPaymentMethod(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "unknown_payment_method"
    title = "That is not a payment method we record"


class InvalidPaymentReference(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "invalid_payment_reference"
    title = "That payment reference does not look usable"


class BarterMemoHasNoPayment(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "barter_memo_has_no_payment"
    title = "A barter deal has no payment to record"
