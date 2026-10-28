"""The check that the test database is migrated before any test runs."""

from tests import migration_check


def test_a_current_database_has_no_problem():
    assert migration_check.problem({"abc"}, {"abc"}) is None


def test_a_database_behind_says_where_it_is_and_the_fix():
    found = migration_check.problem({"old1"}, {"new2"})

    assert found is not None
    assert "old1" in found and "new2" in found
    assert found.endswith("Run: uv run alembic upgrade head")


def test_a_database_never_migrated_says_so():
    found = migration_check.problem(set(), {"new2"})

    assert found is not None
    assert "no migration at all" in found


def test_the_expected_head_is_the_repository_s_own():
    heads = migration_check.expected_heads()

    assert len(heads) == 1  # one migration chain, never forked (CLAUDE.md section 1)


def test_this_database_is_current():
    from app.db.session import engine

    assert migration_check.check(engine) is None
