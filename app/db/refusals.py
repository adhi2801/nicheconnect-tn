"""Reading which rule the database refused a write under.

A unique index or a constraint often holds a line a service also checks first,
because two callers can pass the check at once. Turning the database's refusal
into the check's own answer is right only for the constraint that answer is
about: any other refusal is a different fault and must surface as one.
"""

from sqlalchemy.exc import IntegrityError


def constraint_name(exc: IntegrityError) -> str | None:
    """The name of the constraint a database refusal names, if it names one."""
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name if isinstance(name, str) else None
