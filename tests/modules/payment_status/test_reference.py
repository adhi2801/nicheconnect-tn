"""A payment reference's exact limits (D-091).

Mutation testing found that moving either length limit by one, or turning the
character check upside down, passed every fast test.
"""

import pytest

from app.modules.payment_status.exceptions import InvalidPaymentReference
from app.modules.payment_status.models import REFERENCE_MAX_LENGTH
from app.modules.payment_status.service import REFERENCE_MIN_LENGTH, clean_reference


@pytest.mark.parametrize(
    "reference",
    [
        "a" * REFERENCE_MIN_LENGTH,
        "1" * REFERENCE_MAX_LENGTH,
        "412345678901",
        "UTR/2026-10:7#A",
    ],
)
def test_a_reference_at_or_inside_its_limits_is_kept(reference):
    assert clean_reference(reference) == reference


@pytest.mark.parametrize(
    "reference", ["a" * (REFERENCE_MIN_LENGTH - 1), "1" * (REFERENCE_MAX_LENGTH + 1)]
)
def test_one_past_either_limit_is_refused(reference):
    with pytest.raises(InvalidPaymentReference):
        clean_reference(reference)


@pytest.mark.parametrize(
    "reference", ["UTR=1234", "ref <b>99</b>", "cash; drop table", "₹ 5000"]
)
def test_characters_outside_the_allowed_set_are_refused(reference):
    with pytest.raises(InvalidPaymentReference):
        clean_reference(reference)


def test_spaces_inside_are_tidied_to_one():
    assert clean_reference("  UTR   4123  ") == "UTR 4123"
