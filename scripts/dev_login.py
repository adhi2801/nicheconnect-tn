"""Print an access token for a local account, so a developer can use the API.

Locally, login codes are kept in the server's memory and never logged, so a
person cannot log in through the API on a laptop (docs/DECISION_LOCAL_LOGIN.md,
option A, D-059). This mints a token directly, with the same function the
login endpoint uses. Nothing in the running app changes.

    venv\\Scripts\\python.exe scripts\\dev_login.py +919000000001

It refuses to run unless ENVIRONMENT=local, and refuses a number outside the
seed script's fake range unless --any-phone is given, so it is not casually
pointed at a real person's account.
"""

import argparse
import pathlib
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime

# Run as `python scripts/dev_login.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.schemas import normalize_indian_mobile
from app.modules.auth.tokens import create_access_token

# The seed script's fake numbers (scripts/seed_dev_data.py, PHONE_PREFIX).
SAMPLE_PHONE_PREFIX = "+9190000"


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("phone", help="The account's mobile number, e.g. +919000000001")
    parser.add_argument(
        "--any-phone",
        action="store_true",
        help="Allow a number outside the seed script's fake range",
    )
    args = parser.parse_args(argv)

    if settings.environment != "local":
        print(
            f"Refusing to run: ENVIRONMENT is '{settings.environment}', not 'local'.",
            file=sys.stderr,
        )
        return 1

    try:
        phone = normalize_indian_mobile(args.phone)
    except ValueError:
        print("That is not an Indian mobile number.", file=sys.stderr)
        return 1
    if not phone.startswith(SAMPLE_PHONE_PREFIX) and not args.any_phone:
        print(
            f"Refusing: {phone} is not one of the seed script's sample numbers "
            f"({SAMPLE_PHONE_PREFIX}...). Pass --any-phone if you mean it.",
            file=sys.stderr,
        )
        return 1

    with session_factory() as db:
        account = db.scalars(select(Account).where(Account.phone == phone)).first()
        if account is None:
            print(
                "No account has that number. Run scripts/seed_dev_data.py first, "
                "or check the number.",
                file=sys.stderr,
            )
            return 1
        moment = now or datetime.now(UTC)
        token, expires_at = create_access_token(account.id, account.role, moment)
        role = account.role

    print(token)
    print(
        f"\nRole: {role}. Expires at {expires_at:%H:%M} UTC "
        f"({settings.access_token_expire_minutes} minutes). Use it as:\n"
        f"  Authorization: Bearer <the token above>",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
