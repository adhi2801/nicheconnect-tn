"""Contact details are flagged however they are written (item 60, D-090).

The examples in test_text_flags.py are the shapes people were seen to use.
These try every common way of writing an Indian mobile number inside any
ordinary sentence, because someone moving a deal off the record will space
the digits however the last warning taught them to.
"""

from hypothesis import given
from hypothesis import strategies as st

from app.core.text_flags import flags_in

words = st.text(
    alphabet=st.characters(categories=["Lu", "Ll"], max_codepoint=0x24F) | st.just(" "),
    max_size=30,
)
gaps = st.sampled_from(["", "", "", " ", "-", "."])


@st.composite
def written_mobiles(draw) -> str:
    """A real mobile number, with a prefix and a separator in any gap."""
    digits = draw(st.from_regex(r"\A[6-9][0-9]{9}\Z"))
    prefix = draw(st.sampled_from(["", "+91 ", "+91-", "+91", "91 ", "0"]))
    return prefix + "".join(
        digit + (draw(gaps) if i < 9 else "") for i, digit in enumerate(digits)
    )


def contact(text: str) -> list[str]:
    return flags_in(text, money=False, contact=True)


@given(before=words, number=written_mobiles(), after=words)
def test_a_mobile_written_any_common_way_is_flagged(before, number, after):
    assert "phone_number" in contact(f"{before} {number} {after}")


@given(
    local=st.from_regex(r"\A[a-z][a-z0-9._]{0,15}[a-z0-9]\Z"),
    domain=st.from_regex(r"\A[a-z][a-z0-9-]{1,15}[a-z0-9]\Z"),
    tld=st.sampled_from(["com", "in", "co.in", "org"]),
    before=words,
)
def test_an_email_inside_any_sentence_is_flagged(local, domain, tld, before):
    assert "email" in contact(f"{before} {local}@{domain}.{tld} thanks")


@given(words)
def test_words_alone_never_raise_a_contact_flag(text):
    assert not {"phone_number", "email", "upi_id"} & set(contact(text))
