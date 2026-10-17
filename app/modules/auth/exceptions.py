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


# The second check before a risky change (item 82). 401 with RFC 9470's
# error code, so a client knows to ask for a code rather than to log in
# again; it branches on `code`, as for every error.
STEP_UP_CHALLENGE = (
    'Bearer error="insufficient_user_authentication", '
    'error_description="This change needs a code sent to your phone"'
)


class StepUpRequired(DomainError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "step_up_required"
    title = "This change needs a second check"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail
            or "Ask for a code at POST /api/v1/me/step-up, then send it in the "
            "Step-Up-Code header.",
            headers={"WWW-Authenticate": STEP_UP_CHALLENGE},
        )


class StepUpCodeInvalid(DomainError):
    # One error for wrong, expired, used, missing and other-change codes, as
    # for login codes: a caller learns nothing about which.
    status_code = HTTPStatus.BAD_REQUEST
    code = "step_up_code_invalid"
    title = "That code is not valid for this change. Check it or ask for a new one"
