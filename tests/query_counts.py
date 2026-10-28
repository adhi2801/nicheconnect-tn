"""Counting the SQL a request runs, for the no-query-per-row tests.

`docs/standards/testing.md` section 1: every list has a test proving a long
page costs the same queries as a short one. Each such test asks for the list
twice, with few rows and then many, and compares the counts.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event

from app.db.session import engine


@contextmanager
def count_queries() -> Iterator[list[str]]:
    """Collect every SQL statement run inside the block."""
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def queries_for(client, url: str, headers: dict, params: dict | None = None) -> int:
    """How many statements one successful GET runs."""
    with count_queries() as statements:
        response = client.get(url, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return len(statements)
