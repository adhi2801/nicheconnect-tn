"""Keep an API `Literal` type in step with the allow-list the database enforces.

Each allowed-values list exists twice: once as a tuple the database CHECK
constraint is built from, and once as a `Literal` the API validates and
documents with. If they drift, the API accepts a value the database then
refuses (a 500), or refuses one the database allows.

This check runs when the module is imported, so a drift stops the app from
starting at all. It used to be a bare `assert`, which Python removes under
`-O`: the guard would vanish in exactly the builds nobody watches.
"""

from collections.abc import Iterable
from typing import Any, get_args


class LiteralOutOfStep(RuntimeError):
    """A `Literal` and its allow-list no longer hold the same values."""


def ensure_same_values(name: str, literal: Any, allowed: Iterable[str]) -> None:
    """Raise LiteralOutOfStep unless `literal` lists exactly `allowed`.

    `name` is the Literal's name, used only in the message, which says which
    values are on which side so the fix is obvious.
    """
    declared = set(get_args(literal))
    expected = set(allowed)
    if declared == expected:
        return
    raise LiteralOutOfStep(
        f"{name} is out of step with its allow-list: "
        f"only in the Literal {sorted(declared - expected)}, "
        f"only in the allow-list {sorted(expected - declared)}"
    )
