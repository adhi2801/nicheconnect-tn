"""Strings that look alike: Unicode's confusable test (UTS #39), for names (D-118).

A scammer naming their brand "Nykaa" with its y typed as the Cyrillic
letter U+0443 looks exactly like Nykaa on a phone. Unicode publishes which
characters are confusable with which (`unicode_data/confusables.txt`, version 18.0.0 of 6 August 2026, under
the Unicode License v3 beside it) and the test that uses them: two strings
are confusable when their *skeletons* are equal (UTS #39 section 4, read 24
October 2026).

`skeleton(X)`: X in Normalization Form D, its default-ignorable characters
removed (zero-width spaces and joiners, variation selectors, Hangul fillers),
each remaining character replaced by its prototype, and the result put in
NFD again. As the standard says, a skeleton is only ever compared, never
stored or shown: it is not a normal form of anything.

Default-ignorable characters are approximated without the Unicode Character
Database, which Python does not ship: every format character (category Cf)
plus the code points listed below. They are the ones that hide inside a
name; the test on the published file catches a drift.

Mixed script: Latin letters beside Cyrillic, Greek, Armenian or Cherokee
ones are what impersonation looks like, which is why UTS #39's moderately
restrictive level (section 5.2) refuses Latin with Cyrillic or Greek. Latin
beside Tamil or Devanagari is an ordinary Indian name and is not flagged.
"""

import unicodedata
from functools import cache
from pathlib import Path

DATA = Path(__file__).parent / "unicode_data" / "confusables.txt"
UNICODE_VERSION = "18.0.0"
# What the published file hashed to when it was vendored; a test checks it.
DATA_SHA256 = "6ed3ee967c9dfdf6677d563c9985182fbc50a2efb7d6059cd57b2e2ce18f5b92"

# Default-ignorable code points that are not format characters (Cf).
_IGNORABLE_EXTRA = frozenset({0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x3164, 0xFFA0})
_IGNORABLE_RANGES = ((0x180B, 0x180F), (0xFE00, 0xFE0F), (0xE0000, 0xE0FFF))
# Scripts whose letters pass for Latin ones.
LATIN_LOOKALIKE_SCRIPTS = frozenset({"CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE"})


@cache
def _prototypes() -> dict[str, str]:
    """Each confusable character, mapped to its prototype. Read once."""
    mapping: dict[str, str] = {}
    for line in DATA.read_text(encoding="utf-8-sig").splitlines():
        data = line.split("#", 1)[0].strip()
        if not data:
            continue
        source, target, *_ = (field.strip() for field in data.split(";"))
        mapping[chr(int(source, 16))] = "".join(
            chr(int(code, 16)) for code in target.split()
        )
    return mapping


def is_default_ignorable(character: str) -> bool:
    code = ord(character)
    return (
        unicodedata.category(character) == "Cf"
        or code in _IGNORABLE_EXTRA
        or any(low <= code <= high for low, high in _IGNORABLE_RANGES)
    )


def skeleton(text: str) -> str:
    """UTS #39's skeleton of `text`: equal skeletons mean the two look alike."""
    prototypes = _prototypes()
    decomposed = unicodedata.normalize("NFD", text)
    replaced = "".join(
        prototypes.get(character, character)
        for character in decomposed
        if not is_default_ignorable(character)
    )
    return unicodedata.normalize("NFD", replaced)


def scripts_of(text: str) -> frozenset[str]:
    """The scripts of the letters in `text`, by the first word of each letter's name."""
    found = set()
    for character in text:
        if unicodedata.category(character).startswith("L"):
            name = unicodedata.name(character, "")
            if name:
                found.add(name.split(" ", 1)[0])
    return frozenset(found)


def mixes_latin_with_lookalikes(text: str) -> bool:
    """Latin letters beside Cyrillic, Greek, Armenian or Cherokee ones."""
    scripts = scripts_of(text)
    return "LATIN" in scripts and bool(scripts & LATIN_LOOKALIKE_SCRIPTS)
