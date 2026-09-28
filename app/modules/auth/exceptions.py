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


class ProfileAlreadyExists(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "profile_exists"
    title = "This account already has a profile"


class HandleTaken(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "handle_taken"
    title = "That handle is already in use. Try another one"


class EmailTaken(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "email_taken"
    title = "That email is already registered to another brand"


class OtpVerifyLimitReached(DomainError):
    status_code = HTTPStatus.TOO_MANY_REQUESTS
    code = "otp_verify_limit_reached"
    title = "Too many code attempts for this number. Please try again later"


class ChannelNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "channel_not_found"
    title = "You have not added a channel for that platform"


class PackageNotFound(DomainError):
    # 404 rather than 403 for somebody else's package: 403 would confirm the
    # id exists, which would let anyone walk the table.
    status_code = HTTPStatus.NOT_FOUND
    code = "package_not_found"
    title = "No such package"


class PackageLimitReached(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "package_limit_reached"
    title = "You have as many packages as we allow"


class ProfileUrlDoesNotMatchPlatform(DomainError):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "profile_url_platform_mismatch"
    title = "That link is not on the platform you chose"
