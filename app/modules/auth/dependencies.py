"""FastAPI dependencies for the auth module."""

from datetime import datetime, timezone


def get_now() -> datetime:
    """The current UTC time. Tests override this to control expiry and limits."""
    return datetime.now(timezone.utc)
