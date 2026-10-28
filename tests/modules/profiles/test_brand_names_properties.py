"""What holds for every name a scammer could try (item 75, D-118).

Each property is a disguise: if a protected name is matched, the same name
dressed up any of these ways must still be matched.
"""

from hypothesis import given
from hypothesis import strategies as st

from app.modules.profiles.brand_names import FILLER_WORDS, curated, resembles

PROTECTED = st.sampled_from(curated())
FILLERS = st.lists(st.sampled_from(sorted(FILLER_WORDS)), max_size=3)
INVISIBLE = st.sampled_from(
    [chr(0x200B), chr(0x200C), chr(0x200D), chr(0xFE0F), chr(0x2060)]
)
# Latin letters and a Cyrillic or Greek letter that looks the same.
LOOK_ALIKES = {
    "a": chr(0x0430),
    "e": chr(0x0435),
    "o": chr(0x043E),
    "p": chr(0x0440),
    "c": chr(0x0441),
    "y": chr(0x0443),
    "x": chr(0x0445),
    "i": chr(0x0456),
}


@given(PROTECTED)
def test_every_protected_name_resembles_itself(entry):
    assert resembles(entry.name, entry)


@given(PROTECTED, FILLERS, FILLERS)
def test_filler_words_around_a_name_never_hide_it(entry, before, after):
    assert resembles(" ".join([*before, entry.name, *after]), entry)


@given(PROTECTED, st.sampled_from(["upper", "lower", "title", "swapcase"]))
def test_case_never_hides_a_name(entry, case):
    assert resembles(getattr(entry.name, case)(), entry)


@given(PROTECTED, INVISIBLE, st.integers(min_value=0, max_value=20))
def test_an_invisible_character_never_hides_a_name(entry, invisible, at):
    position = at % (len(entry.name) + 1)
    assert resembles(entry.name[:position] + invisible + entry.name[position:], entry)


@given(PROTECTED, st.data())
def test_a_look_alike_letter_never_hides_a_name(entry, data):
    swappable = [i for i, c in enumerate(entry.name) if c.lower() in LOOK_ALIKES]
    if not swappable:
        return
    position = data.draw(st.sampled_from(swappable))
    disguised = (
        entry.name[:position]
        + LOOK_ALIKES[entry.name[position].lower()]
        + entry.name[position + 1 :]
    )
    assert resembles(disguised, entry)
