"""Domain errors for the auth module (mapped to Problem Details by app/core/errors.py)."""

import math
from datetime import datetime, timedelta
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


# Changing the phone number (item 80, D-108).


class PhoneChangeWaiting(DomainError):
    # Login with a number another account is waiting to move onto. Only
    # someone who typed the right code for the number gets here, and the
    # change was asked for with a code from it, so nobody else learns of it.
    status_code = HTTPStatus.CONFLICT
    code = "phone_change_waiting"
    title = "This number is waiting to replace the number on an account"

    def __init__(self) -> None:
        super().__init__(
            "Log in with that account's current number until the change is "
            "made, or cancel the change from that account."
        )


class PhoneUnchanged(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "phone_unchanged"
    title = "That is already your number"


class PhoneInUse(DomainError):
    # Said only after the new number's code was right: its holder may know.
    status_code = HTTPStatus.CONFLICT
    code = "phone_in_use"
    title = "That number is already on an account, or waiting to move onto one"


class PhoneChangeTakingEffect(DomainError):
    # The 72 hours are over and the job makes the change within a minute;
    # it can no longer be cancelled or replaced.
    status_code = HTTPStatus.CONFLICT
    code = "phone_change_taking_effect"
    title = "Your phone number change is being made"

    def __init__(self) -> None:
        super().__init__(
            "Its 72 hours are over, so it can no longer be cancelled or "
            "replaced. It is finished within a minute; then log in with the "
            "new number.",
            headers={"Retry-After": "60"},
        )


class LoginTooRecent(DomainError):
    # A change a SIM swapper would want, asked for from a login younger than
    # a week (D-109): their login is always new. Retry-After says when.
    status_code = HTTPStatus.FORBIDDEN
    code = "login_too_recent"
    title = "This change needs an older login"

    def __init__(
        self, allowed_from: datetime, now: datetime, age: timedelta = timedelta(days=7)
    ) -> None:
        super().__init__(
            f"For your safety, a login must be {age.days} days old before it "
            "can make this change. It is allowed from "
            f"{allowed_from.isoformat().replace('+00:00', 'Z')}, or now from a "
            "device you have been logged in on for longer.",
            headers={
                "Retry-After": str(
                    max(1, math.ceil((allowed_from - now).total_seconds()))
                )
            },
        )


# Passkeys (item 79, D-113).


class PasskeysNotOpen(DomainError):
    # Off until the name and the domain exist (item 4): a passkey is bound to
    # its domain, and one made for a stand-in would never work on the real one.
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "passkeys_unavailable"
    title = "Passkeys are not available yet"


class PasskeyInvalid(DomainError):
    # One error for a wrong, expired, used or foreign challenge, an unknown
    # key, a bad signature or a counter gone backwards: a caller learns
    # nothing about which.
    status_code = HTTPStatus.BAD_REQUEST
    code = "passkey_invalid"
    title = "That passkey could not be checked. Try again"


class PasskeyNotFound(DomainError):
    # Also someone else's passkey: 404, never 403.
    status_code = HTTPStatus.NOT_FOUND
    code = "passkey_not_found"
    title = "That passkey is not one of yours"


class TooManyPasskeys(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "too_many_passkeys"
    title = "You have the most passkeys an account may hold; remove one first"


class PasskeyOnly(DomainError):
    # A phone code was right, but this account signs in only with a passkey
    # (D-113). Only someone holding the number learns it; the code stays
    # usable, so it can start a reset at once.
    status_code = HTTPStatus.FORBIDDEN
    code = "passkey_only"
    title = "This account signs in with a passkey"

    def __init__(self) -> None:
        super().__init__(
            "Sign in with your passkey. If you lost every passkey, the same code "
            "can start a reset at POST /api/v1/auth/passkey-reset, which takes 7 days."
        )


class NoPasskeyToReset(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "no_passkey_to_reset"
    title = "This number's account has no passkey to reset"


class PasskeyNeededFirst(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "passkey_needed_first"
    title = "Add a passkey before turning on passkey-only sign-in"
