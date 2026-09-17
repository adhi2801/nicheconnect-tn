"""Domain errors for the auth module (mapped to Problem Details by app/core/errors.py)."""

from http import HTTPStatus

from app.core.errors import DomainError


class InvalidToken(DomainError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "invalid_token"
    title = "Your session is invalid or has expired. Please log in again"


class OtpInvalid(DomainError):
    # One error for wrong, expired, used or missing codes, so attackers learn nothing.
    status_code = HTTPStatus.BAD_REQUEST
    code = "otp_invalid"
    title = "That code is not valid. Check it or request a new one"


class OtpSendLimitReached(DomainError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "otp_send_limit_reached"
    title = "Too many codes requested for this number. Please try again later"


class RoleMismatch(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "role_mismatch"
    title = "This number is already registered with a different account type"
