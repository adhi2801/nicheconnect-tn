"""The release step: the one thing that runs as the database owner (item 97, D-100).

Run by the migration task before each deploy (`python -m app.db.prepare`),
with DATABASE_URL set to the owner and APP_DATABASE_PASSWORD to the app
login's password. In order:

1. the Alembic migrations, which also keep app_writer's rights in step;
2. DBOS's own schema (D-060), granting app_writer what DBOS needs in it, so
   the app never has to create a schema at start;
3. the app's login, made or given the password the secret holds now.

Without APP_DATABASE_PASSWORD (a laptop), step 3 is skipped and the app keeps
connecting as the owner, as it always has locally.
"""

from pathlib import Path

from alembic.command import upgrade
from alembic.config import Config
from dbos import DBOS

from app.core.config import settings
from app.core.jobs import DBOS_SCHEMA
from app.db.roles import APP_WRITER, ensure_app_login
from app.db.session import engine

ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def prepare() -> None:
    upgrade(alembic_config(), "head")
    DBOS.migrate(settings.database_url, schema=DBOS_SCHEMA, application_role=APP_WRITER)
    if settings.app_database_password is not None:
        with engine.begin() as connection:
            ensure_app_login(
                connection, settings.app_database_password.get_secret_value()
            )


if __name__ == "__main__":  # pragma: no cover - the migration task's entry point
    prepare()
