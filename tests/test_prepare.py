"""The release step's wiring (item 97, D-100): what runs, in which order, with what.

CI runs the real thing against a fresh database before the tests ("Prepare
the release as production does"), and tests/modules/test_app_role.py proves
the login it makes. These pin the order and the arguments, which a rename
could break without either noticing until a deploy.
"""

from pydantic import SecretStr

from app.db import prepare
from app.db.roles import APP_WRITER


def recorded(monkeypatch, password: str | None) -> list[tuple]:
    calls: list[tuple] = []
    monkeypatch.setattr(
        prepare, "upgrade", lambda config, rev: calls.append(("upgrade", rev))
    )
    monkeypatch.setattr(
        prepare.DBOS,
        "migrate",
        lambda url, *, schema, application_role: calls.append(
            ("dbos", schema, application_role)
        ),
    )
    monkeypatch.setattr(
        prepare, "ensure_app_login", lambda connection, pw: calls.append(("login", pw))
    )
    monkeypatch.setattr(
        prepare.settings,
        "app_database_password",
        SecretStr(password) if password else None,
    )
    prepare.prepare()
    return calls


def test_migrations_then_dbos_then_the_login(monkeypatch):
    password = "a" * 40

    assert recorded(monkeypatch, password) == [
        ("upgrade", "head"),
        ("dbos", "dbos", APP_WRITER),
        ("login", password),
    ]


def test_without_a_password_no_login_is_touched(monkeypatch):
    """A laptop: the app keeps connecting as the owner."""
    assert [call[0] for call in recorded(monkeypatch, None)] == ["upgrade", "dbos"]


def test_alembic_is_found_wherever_it_starts():
    config = prepare.alembic_config()

    assert config.get_main_option("script_location").endswith("alembic")
