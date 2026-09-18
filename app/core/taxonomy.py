"""Shared domain vocabulary used by more than one module.

Creator profiles and campaigns must agree on niches, so the lists live here
rather than in either module's models (backend.md section 1).
"""

NICHES: tuple[str, ...] = (
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
)
# Tamil ("ta") is added by a decision, together with the migration that widens
# the check constraints (D-005).
LANGUAGES: tuple[str, ...] = ("en",)

MAX_NICHES = 5
CURRENCY = "INR"


def sql_text_array(values: tuple[str, ...]) -> str:
    """A SQL text[] literal from fixed, code-defined values (never user input)."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"ARRAY[{quoted}]::text[]"
