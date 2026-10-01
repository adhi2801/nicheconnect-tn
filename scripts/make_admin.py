"""Create an admin account, or suspend or restore one. The only way either happens.

Admins are never created by login and there is no API to promote anyone
(D-061). A founder runs this against the database, with access to it:

    venv\\Scripts\\python.exe scripts\\make_admin.py +919876543210
    venv\\Scripts\\python.exe scripts\\make_admin.py +919876543210 --suspend abuse
    venv\\Scripts\\python.exe scripts\\make_admin.py +919876543210 --restore

Outside ENVIRONMENT=local it also needs --yes, so a mistyped command aimed at
the live database cannot make somebody an admin. A phone that already belongs
to a brand or creator is refused: an admin is a separate identity, never a
user with extra powers.
"""

import argparse
import pathlib
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.auth.models.account import REPORT_CATEGORIES, Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.schemas import normalize_indian_mobile


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("phone", help="The admin's mobile number")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--suspend", choices=REPORT_CATEGORIES, help="Suspend this admin")
    action.add_argument(
        "--restore", action="store_true", help="Lift this admin's suspension"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Required outside ENVIRONMENT=local"
    )
    args = parser.parse_args(argv)

    if settings.environment != "local" and not args.yes:
        print(
            f"ENVIRONMENT is '{settings.environment}'. Add --yes if you mean to "
            "change admins there.",
            file=sys.stderr,
        )
        return 1
    try:
        phone = normalize_indian_mobile(args.phone)
    except ValueError:
        print("That is not an Indian mobile number.", file=sys.stderr)
        return 1
    moment = now or datetime.now(UTC)

    with session_factory() as db:
        account = db.scalars(select(Account).where(Account.phone == phone)).first()

        if args.suspend or args.restore:
            if account is None or account.role != "admin":
                print("No admin account has that number.", file=sys.stderr)
                return 1
            if args.suspend:
                account.suspended_at = moment
                account.suspension_reason = args.suspend
                # Ends every session at once, as an admin's suspension does.
                db.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.account_id == account.id,
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=moment, updated_at=moment)
                )
                message = f"Suspended admin {account.id} ({args.suspend})."
            else:
                account.suspended_at = None
                account.suspension_reason = None
                message = f"Restored admin {account.id}."
            db.commit()
            print(message)
            return 0

        if account is not None:
            if account.role == "admin":
                print(f"Already an admin: {account.id}.")
                return 0
            print(
                f"That number is a {account.role} account. An admin must be a "
                "separate identity; use another number.",
                file=sys.stderr,
            )
            return 1
        account = Account(phone=phone, role="admin")
        db.add(account)
        db.commit()
        print(f"Created admin {account.id}. They log in with a code, as role 'admin'.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
