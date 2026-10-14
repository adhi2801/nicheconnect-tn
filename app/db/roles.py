"""The app's own database login, which can read and write rows and nothing more (item 97, D-100).

Until 14 October 2026 the app connected as the table owner (the RDS master
user), and the owner of a table can `ALTER TABLE ... DISABLE TRIGGER`, so the
app's own credentials could switch off the deal record's seals (D-057).

Two roles now:

- `app_writer`, a group role without a login, made and granted by migration
  0dbcaacb1030: row reads and writes on every table, only reads and inserts
  on the sealed ones, no TRUNCATE, no ownership, no CREATE. Tables made by
  later migrations get the same rights by default.
- `nicheconnect_app`, the login the running app uses, a member of
  `app_writer`. Made, or its password changed, by `ensure_app_login`, which
  the release step runs as the owner (`app/db/prepare.py`).

The password is sent as a SCRAM-SHA-256 verifier computed here, never as
plain text, so a server that logs statements records only a value that
cannot log in (PostgreSQL's documentation on CREATE ROLE warns of exactly
this).
"""

import base64
import hashlib
import hmac
import re
import secrets

from sqlalchemy import Connection, text

from app.core.config import APP_DATABASE_PASSWORD

APP_WRITER = "app_writer"
APP_LOGIN = "nicheconnect_app"
# PostgreSQL's own default (scram_iterations).
SCRAM_ITERATIONS = 4096
# Letters and digits only (APP_DATABASE_PASSWORD): SASLprep leaves them
# unchanged, so the verifier computed here is the one the server computes at
# login. Infra generates 64.
VERIFIER = re.compile(
    r"SCRAM-SHA-256\$\d+:[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+"
)


class UnsafeAppPassword(ValueError):
    """The password is too short, or holds characters SASLprep would change."""


def scram_verifier(password: str, *, salt: bytes | None = None) -> str:
    """The SCRAM-SHA-256 verifier PostgreSQL stores for this password (RFC 7677)."""
    if not APP_DATABASE_PASSWORD.fullmatch(password):
        raise UnsafeAppPassword(
            "the app's database password must be 32 to 128 letters and digits"
        )
    salt = salt if salt is not None else secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, SCRAM_ITERATIONS)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    def b64(raw: bytes) -> str:
        return base64.b64encode(raw).decode()

    return (
        f"SCRAM-SHA-256${SCRAM_ITERATIONS}:{b64(salt)}"
        f"${b64(stored_key)}:{b64(server_key)}"
    )


def ensure_app_login(
    connection: Connection, password: str, *, login: str = APP_LOGIN
) -> None:
    """Make the app's login, or change its password, as a member of app_writer.

    Run as the owner, after the migrations (which make app_writer). Safe to
    run on every release: it also rotates the password to whatever the
    secret now holds. The caller commits.
    """
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", login):
        raise ValueError(f"not a plain role name: {login!r}")
    verifier = scram_verifier(password)
    # Utility statements take no bound parameters; the verifier is checked
    # to hold only base64 characters before it is written into one.
    if not VERIFIER.fullmatch(verifier):  # pragma: no cover - built just above
        raise ValueError("unexpected verifier shape")
    exists = connection.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :login"), {"login": login}
    ).first()
    attributes = (
        "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
        f"PASSWORD '{verifier}'"
    )
    verb = "ALTER" if exists else "CREATE"
    # exec_driver_sql, not text(): text() reads ":name" as a placeholder, and a
    # verifier holds ":" followed by base64 (caught by tests/modules/test_app_role.py).
    connection.exec_driver_sql(f"{verb} ROLE {login} WITH {attributes}")
    connection.execute(text(f"GRANT {APP_WRITER} TO {login}"))
