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


class NotAPaymentParty(DomainError):
    status_code = HTTPStatus.FORBIDDEN
    code = "not_a_payment_party"
    title = "Only brand and creator accounts have payments"


# --- the UPI pay link (D-085) ---------------------------------------------------------


class UpiNotOpenYet(DomainError):
    # The notice a creator must read first comes from the validation pack
    # (constraint 6). Until it exists, nobody can give a UPI ID.
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "upi_not_open_yet"
    title = "Adding a UPI ID is not open yet"


class UpiNoticeChanged(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "upi_notice_changed"
    title = "The notice has changed since you read it; read the new one and try again"
