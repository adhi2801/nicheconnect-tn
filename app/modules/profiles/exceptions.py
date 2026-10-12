"""Domain errors for profiles, rate cards and availability (D-099)."""

from http import HTTPStatus

from app.core.errors import DomainError


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


class MustBeAnAdult(DomainError):
    # Adults only (D-086): a contract with a minor is void in India, and a
    # minor's data needs verified parental consent (legal.md section 3.10).
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "must_be_18_or_over"
    title = "You must be 18 or over to use this service"


class InvalidAvailability(DomainError):
    # A "booked until" in the past would say nothing, and one more than a
    # year ahead is almost certainly a typo for this year (D-083).
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "invalid_availability"
    title = "That date cannot be your booked-until date"
