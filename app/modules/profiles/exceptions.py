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


# --- a brand's domain (item 74, D-106) ---------------------------------------------------


class DomainNotAcceptable(DomainError):
    # The detail says why, and what to claim instead.
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "domain_not_accepted"
    title = "That domain cannot be claimed"


class DomainClaimNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "domain_claim_not_found"
    title = "You have not claimed a domain"


class DomainHeldElsewhere(DomainError):
    # Public anyway: the holder's campaigns show the domain to creators.
    status_code = HTTPStatus.CONFLICT
    code = "domain_held_elsewhere"
    title = "Another brand has already verified that domain"


class DomainClaimLapsed(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "domain_claim_lapsed"
    title = "This claim lapsed when the record was gone. Claim the domain again for a new token"


class DomainClaimExpired(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "domain_claim_expired"
    title = "This token expired after 7 days. Claim the domain again for a new one"


# --- look-alike brand names (item 75, D-118) ---------------------------------------------


class BrandNameNeedsDomain(DomainError):
    # Option B: a name that looks like a protected brand's publishes nothing
    # until the brand proves it is that brand, by its domain (item 74).
    status_code = HTTPStatus.CONFLICT
    code = "brand_name_needs_domain"
    title = "Your brand name looks like another brand's. Verify your domain to publish"

    @classmethod
    def for_name(
        cls, name: str | None, domain: str | None, mixed: bool
    ) -> BrandNameNeedsDomain:
        if name is not None and domain is not None:
            return cls(
                f"Your name looks like {name}'s. Verify {domain} at "
                "POST /api/v1/brands/me/domain to publish, or ask us to review it."
            )
        return cls(
            "Your name mixes Latin letters with look-alike letters from another "
            "alphabet. Rename the brand, or ask us to review it."
        )


class ConnectionsOff(DomainError):
    # Off until Meta App Review, Google's verification and the connect
    # notice exist (D-134).
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "connections_unavailable"
    title = "Connecting Instagram and YouTube is not available yet"


class ConnectionAttemptInvalid(DomainError):
    # Unknown, expired, already used, another account's or another
    # platform's: all one answer, so a guessed state learns nothing.
    status_code = HTTPStatus.CONFLICT
    code = "connection_attempt_invalid"
    title = "That sign-in has expired or is not yours. Start connecting again"


class PlatformRefusedConnection(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "platform_refused"
    title = "The platform did not let us connect. Try again from the start"


class PlatformDown(DomainError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "platform_unavailable"
    title = "The platform is not answering. Try again in a few minutes"

    def __init__(self) -> None:
        super().__init__(headers={"Retry-After": "60"})


class ChannelAlreadyConnected(DomainError):
    # One platform account for one creator (D-134): two people cannot both
    # claim a channel. Which creator holds it is never said.
    status_code = HTTPStatus.CONFLICT
    code = "channel_already_connected"
    title = "That account is already connected to another creator on NicheConnect"


class ConnectionNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "connection_not_found"
    title = "You have no account connected on that platform"


class SignedRequestInvalid(DomainError):
    status_code = HTTPStatus.BAD_REQUEST
    code = "invalid_signed_request"
    title = "That request was not signed by Meta"


class DeletionRequestNotFound(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "deletion_request_not_found"
    title = "No deletion request has that confirmation code"
