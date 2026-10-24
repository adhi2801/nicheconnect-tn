"""What holds for every device label an app could send (D-114).

The API and the database each judge a label. If the API ever accepted one
the database refuses, a login would end in a server error; these try
thousands of labels, control characters and every kind of space among them.
"""

import uuid
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import engine
from app.modules.auth.schemas import DeviceIn
from tests.factories import unique_test_phone

NOW = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)
CONTROL = st.sampled_from(
    [chr(c) for c in (*range(0x01, 0x20), *range(0x7F, 0xA0), 0x2028, 0x2029)]
)


def accepted_by_the_api(label: str) -> str | None:
    try:
        return DeviceIn(platform="android", label=label).label
    except ValidationError:
        return None


def accepted_by_the_database(label: str) -> bool:
    """Write the label with raw SQL inside a transaction that is always undone."""
    with engine.connect() as connection, connection.begin() as transaction:
        account_id = connection.execute(
            text("INSERT INTO account (phone, role) VALUES (:p, 'creator') RETURNING id"),
            {"p": unique_test_phone()},
        ).scalar_one()
        try:
            with connection.begin_nested():
                connection.execute(
                    text(
                        "INSERT INTO auth_session (account_id, family_id, token_hash,"
                        " expires_at, client_platform, client_label)"
                        " VALUES (:a, :f, :t, :e, 'android', :l)"
                    ),
                    {
                        "a": account_id,
                        "f": uuid.uuid4(),
                        "t": uuid.uuid4().hex * 2,
                        "e": NOW + timedelta(days=30),
                        "l": label,
                    },
                )
            return True
        except IntegrityError:
            return False
        finally:
            transaction.rollback()


@given(st.text(max_size=80))
def test_every_label_the_api_accepts_the_database_accepts(label):
    kept = accepted_by_the_api(label)
    if kept is not None:
        assert accepted_by_the_database(kept), repr(kept)


@given(
    before=st.text(max_size=20),
    control=CONTROL,
    after=st.text(max_size=20),
)
def test_a_control_character_anywhere_inside_is_refused(before, control, after):
    label = f"x{before}{control}{after}x"

    assert accepted_by_the_api(label) is None


@given(st.text(min_size=1, max_size=60).filter(lambda s: s.strip() == s and s.strip()))
def test_a_kept_label_is_the_label_trimmed(label):
    kept = accepted_by_the_api(f"  {label}  ")

    assert kept is None or kept == label
