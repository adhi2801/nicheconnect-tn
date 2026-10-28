"""Payment references, for any input (D-090)."""

from hypothesis import given
from hypothesis import strategies as st

from app.modules.payment_status.exceptions import InvalidPaymentReference
from app.modules.payment_status.models import REFERENCE_MAX_LENGTH
from app.modules.payment_status.service import REFERENCE_MIN_LENGTH, clean_reference


@given(st.text(max_size=60))
def test_a_reference_is_tidied_within_its_limits_or_refused(reference):
    try:
        tidied = clean_reference(reference)
    except InvalidPaymentReference:
        return
    assert REFERENCE_MIN_LENGTH <= len(tidied) <= REFERENCE_MAX_LENGTH
    assert tidied == tidied.strip()
    assert "  " not in tidied


@given(st.text(max_size=60))
def test_tidying_twice_changes_nothing(reference):
    try:
        tidied = clean_reference(reference)
    except InvalidPaymentReference:
        return
    assert clean_reference(tidied) == tidied
