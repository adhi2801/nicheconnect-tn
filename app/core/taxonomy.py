"""Shared domain vocabulary used by more than one module.

Creator profiles and campaigns must agree on niches, so the lists live here
rather than in either module's models (backend.md section 1).

Each list is written once, as a `Literal` the API validates against, and the
tuple the database CHECK constraints are built from is read out of it. One
source means the two cannot drift.
"""

from typing import Final, Literal, get_args

Niche = Literal[
    "food",
    "fashion",
    "beauty",
    "tech",
    "travel",
    "fitness",
    "education",
    "entertainment",
    "finance",
    "lifestyle",
]
NICHES: tuple[Niche, ...] = get_args(Niche)

# Tamil ("ta") is added by a decision, together with the migration that widens
# the check constraints (D-005).
Language = Literal["en"]
LANGUAGES: tuple[Language, ...] = get_args(Language)

MAX_NICHES = 5
CURRENCY: Final = "INR"


def sql_text_array(values: tuple[str, ...]) -> str:
    """A SQL text[] literal from fixed, code-defined values (never user input)."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"ARRAY[{quoted}]::text[]"
