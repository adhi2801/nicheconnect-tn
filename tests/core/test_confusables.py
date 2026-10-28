"""Unicode's confusable test, as `app/core/confusables.py` applies it (D-118)."""

import hashlib

import pytest

from app.core import confusables
from app.core.confusables import (
    DATA,
    DATA_SHA256,
    is_default_ignorable,
    mixes_latin_with_lookalikes,
    skeleton,
)

CYRILLIC_A = chr(0x0430)
CYRILLIC_U = chr(0x0443)
CYRILLIC_I = chr(0x0456)
GREEK_OMICRON = chr(0x03BF)
ZERO_WIDTH_SPACE = chr(0x200B)
ZERO_WIDTH_JOINER = chr(0x200D)
VARIATION_SELECTOR = chr(0xFE0F)
TAMIL_A = chr(0x0B85)


def test_the_data_is_unicodes_file_as_published():
    """Byte for byte what unicode.org published for 18.0.0; .gitattributes keeps it so."""
    assert hashlib.sha256(DATA.read_bytes()).hexdigest() == DATA_SHA256
    head = DATA.read_text(encoding="utf-8-sig")[:400]
    assert f"Version: {confusables.UNICODE_VERSION}" in head


def test_the_mapping_is_read_whole():
    """A guard: on an empty mapping every test below would pass by accident."""
    assert len(confusables._prototypes()) > 6000


@pytest.mark.parametrize(
    ("look_alike", "plain"),
    [
        ("N" + CYRILLIC_U + "kaa", "Nykaa"),
        ("p" + CYRILLIC_A + "ypal", "paypal"),
        ("Mamaearth", "Mamaearth"),
        ("g" + GREEK_OMICRON + "ogle", "google"),
        ("rn", "m"),
        ("Ny" + ZERO_WIDTH_SPACE + "kaa", "Nykaa"),
        ("Nyk" + ZERO_WIDTH_JOINER + "aa" + VARIATION_SELECTOR, "Nykaa"),
        # The example UTS #39's implementers use: Fraktur, script and
        # double-struck letters, and a y with a loop.
        (
            "".join(chr(c) for c in (0x1D52D, 0x1D4B6, 0x1EFF, 0x1D561, 0x1D552, 0x2113)),
            "paypal",
        ),
    ],
)
def test_look_alikes_share_a_skeleton(look_alike, plain):
    assert skeleton(look_alike) == skeleton(plain)


@pytest.mark.parametrize(
    ("one", "other"), [("Nykaa", "Nykka"), ("Plum", "Plus"), ("boat", "boot")]
)
def test_different_names_keep_different_skeletons(one, other):
    assert skeleton(one) != skeleton(other)


@pytest.mark.parametrize(
    "character",
    [ZERO_WIDTH_SPACE, ZERO_WIDTH_JOINER, VARIATION_SELECTOR, chr(0x034F), chr(0x3164)],
)
def test_invisible_characters_are_ignorable(character):
    assert is_default_ignorable(character)


@pytest.mark.parametrize("character", ["a", " ", TAMIL_A, "1"])
def test_visible_characters_are_not(character):
    assert not is_default_ignorable(character)


@pytest.mark.parametrize(
    ("name", "mixed"),
    [
        ("N" + CYRILLIC_U + "kaa", True),
        ("Mamaearth" + CYRILLIC_I, True),
        ("g" + GREEK_OMICRON + "ogle", True),
        ("Nykaa", False),
        # Latin beside Tamil is an ordinary Indian name, not an impersonation.
        ("Amma " + TAMIL_A, False),
        (CYRILLIC_A + CYRILLIC_U, False),
    ],
)
def test_latin_mixed_with_look_alike_scripts_is_told_apart(name, mixed):
    assert mixes_latin_with_lookalikes(name) is mixed
