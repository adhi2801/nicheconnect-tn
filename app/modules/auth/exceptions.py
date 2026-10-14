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


class RoleNotAllowed(DomainError):
    status_code = HTTPStatus.FORBIDDEN
    code = "role_not_allowed"
    title = "This account type cannot use this feature"


class ProfileNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "profile_not_found"
    title = "You have not created your profile yet"


class OtpVerifyLimitReached(DomainError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "otp_verify_limit_reached"
    title = "Too many code attempts for this number. Please try again later"


class InvalidSearch(DomainError):
    # Filters that cannot all be true at once: answering with an empty list
    # would look like "no creators" rather than "you asked for nothing".
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "invalid_search"
    title = "Those search filters contradict each other"


class AccountSuspended(DomainError):
    # Told plainly, with the category of reason, never the admin's own note
    # (D-061). 403 rather than 401: the credentials are fine, the account is not.
    status_code = HTTPStatus.FORBIDDEN
    code = "account_suspended"
    title = "This account is suspended"

    @classmethod
    def because(cls, reason: str | None) -> AccountSuspended:
        return cls(f"Reason: {(reason or 'other').replace('_', ' ')}.")


class AdminNotFound(DomainError):
    # Every admin route answers anyone who is not an admin exactly like a
    # route that does not exist, so the admin API cannot be found by probing.
    status_code = HTTPStatus.NOT_FOUND
    code = "not_found"
    title = "Not found"


class DeviceNotFound(DomainError):
    # Also someone else's device: 404, never 403 (security.md section 2).
    status_code = HTTPStatus.NOT_FOUND
    code = "device_not_found"
    title = "That device is not registered to you"
