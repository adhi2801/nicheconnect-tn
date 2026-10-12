"""No phone number reaches Sentry, however it is written (D-074; the gap found by D-090).

The same generator that found the gap in the contact-detail flag (D-090):
every common way of writing an Indian mobile, inside any sentence.
"""

from hypothesis import given

from app.core.error_tracking import redact
from tests.core.test_text_flags_properties import words, written_mobiles


@given(before=words, number=written_mobiles(), after=words)
def test_a_mobile_written_any_common_way_never_reaches_an_error_report(
    before, number, after
):
    digits = "".join(ch for ch in number if ch.isdigit())[-10:]
    scrubbed = redact(f"{before} {number} {after}")

    assert digits not in "".join(ch for ch in scrubbed if ch.isdigit())
