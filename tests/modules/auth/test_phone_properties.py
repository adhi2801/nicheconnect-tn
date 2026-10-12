"""Indian mobile numbers, however they are typed (D-090).

Whatever a person types, the number is stored in the one form the database
accepts, or refused with a message; and normalising twice changes nothing.
"""

import re

from hypothesis import given
from hypothesis import strategies as st
from pydantic_core import PydanticCustomError

from app.modules.auth.models.account import PHONE_PATTERN
from app.modules.auth.schemas import normalize_indian_mobile

mobiles = st.from_regex(r"\A[6-9][0-9]{9}\Z")
separators = st.sampled_from(["", " ", "-", "(", ")", "  "])


@st.composite
def typed_mobiles(draw) -> tuple[str, str]:
    """A real mobile, typed with a prefix and separators anywhere."""
    digits = draw(mobiles)
    prefix = draw(st.sampled_from(["", "+91", "91", "0", "+91 ", "+91-"]))
    typed = "".join(ch + draw(separators) for ch in digits)
    return digits, prefix + typed


@given(typed_mobiles())
def test_a_mobile_typed_any_common_way_is_stored_as_e164(case):
    digits, typed = case

    assert normalize_indian_mobile(typed) == f"+91{digits}"


@given(st.text(max_size=40))
def test_anything_is_stored_in_the_databases_form_or_refused(typed):
    try:
        stored = normalize_indian_mobile(typed)
    except PydanticCustomError:
        return
    assert re.fullmatch(PHONE_PATTERN, stored)


@given(typed_mobiles())
def test_normalising_twice_changes_nothing(case):
    once = normalize_indian_mobile(case[1])

    assert normalize_indian_mobile(once) == once
