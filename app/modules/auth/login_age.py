"""How old a login must be before a change a SIM swapper would want (D-109).

A code sent to the phone does not stop a SIM swap: the code goes to whoever
holds the number. What a SIM swapper never has is an old login: theirs is
made the day they take the number. So, as Google blocks sensitive actions
from a device signed in for less than 7 days, changing the phone number and
replacing a UPI ID already in effect need a login at least
ESTABLISHED_LOGIN old. Anything else, a first UPI ID included, does not.

The login's age comes from the access token's `auth_time`, kept through
every refresh (`service.logged_in_at`), so a stolen access token cannot
claim to be older than the login it came from.
"""

from datetime import datetime, timedelta

from app.modules.auth.exceptions import LoginTooRecent

# Google's period for sensitive actions from a new device (read 18 October
# 2026), and TRAI's 7 days before a swapped SIM's number may be ported.
ESTABLISHED_LOGIN = timedelta(days=7)
# Moving the account without a code from its current number (D-110): the
# login itself is then the only proof, so it must be much older.
LOST_NUMBER_LOGIN = timedelta(days=30)


def allowed_from(
    authenticated_at: datetime | None,
    now: datetime,
    age: timedelta = ESTABLISHED_LOGIN,
) -> datetime:
    """When a login proven at `authenticated_at` may make such a change.

    A token with no login time counts as a login made at `now`.
    """
    return (now if authenticated_at is None else authenticated_at) + age


def ensure_established(
    authenticated_at: datetime | None,
    now: datetime,
    age: timedelta = ESTABLISHED_LOGIN,
) -> None:
    """Raise LoginTooRecent unless the login is at least `age` old."""
    allowed = allowed_from(authenticated_at, now, age)
    if now < allowed:
        raise LoginTooRecent(allowed, now, age)
