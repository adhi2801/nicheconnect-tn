"""Whether a brand's name looks like a protected brand's (item 75, D-118). Pure rules.

The pay-to-collab scam starts with a believable fake brand (trust-and-safety.md
section 2): "Nykaa Collabs", "Nykaa" with its y typed as the Cyrillic letter U+0443, "Mamaearth Official
India". Three steps, in order:

1. **Look-alike characters** become their Unicode prototypes (UTS #39's
   skeleton, `app/core/confusables.py`), after case folding, so "NYKAA",
   "nykaa" and that Cyrillic spelling read the same.
2. **Filler words** that scammers add to a borrowed name are dropped:
   "official", "india", "collabs", "team", "pvt ltd" and the like.
3. **One slip** is still the same name: words within one edit (Damerau's
   distance: a letter added, dropped, changed, or two swapped) of a protected
   name of at least 5 letters match it, so "Nykka", "Nyka" and "Zomatto" are
   caught; a shorter protected name ("Plum") must match exactly, since one
   slip from it lands on ordinary words.

A protected name matched as a **word** matches anywhere in the name
("Nykaa Beauty Partners"); one matched **exactly** ("Plum", "boAt", also
everyday words) only when the whole name is it.

A brand never resembles a name whose domain it has itself verified (item 74):
that is the brand. And Latin letters mixed with Cyrillic or Greek ones are
flagged on their own, protected name or not.

What this says is a fact about two names, never a verdict on a business
(legal.md section 3.12): "looks like Nykaa; this account has not verified
nykaa.com".
"""

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from app.core.confusables import mixes_latin_with_lookalikes, skeleton

PROTECTED_LIST = Path(__file__).parent / "protected_brands.json"
FILLER_WORDS = frozenset(
    {
        "official",
        "officials",
        "india",
        "indian",
        "collab",
        "collabs",
        "collaboration",
        "collaborations",
        "partner",
        "partners",
        "team",
        "support",
        "care",
        "pvt",
        "private",
        "ltd",
        "limited",
        "llp",
        "inc",
        "co",
        "company",
        "brand",
        "brands",
        "store",
        "shop",
        "online",
        "global",
        "hq",
        "the",
    }
)
# Below this, one slip lands on ordinary words ("plum" and "plus").
MIN_LETTERS_FOR_A_SLIP = 5
_WORD = re.compile(r"[^\W_]+")

MatchKind = Literal["word", "exact"]


@dataclass(frozen=True)
class ProtectedName:
    """A name another brand may not borrow, and the domain that proves the real one."""

    name: str
    domain: str
    match: MatchKind = "word"


@dataclass(frozen=True)
class NameFlag:
    """What a creator is told about a brand's name. Facts, never a verdict."""

    resembles: ProtectedName | None
    mixed_script: bool


@cache
def curated() -> tuple[ProtectedName, ...]:
    """The hand-curated list, read once."""
    data = json.loads(PROTECTED_LIST.read_text(encoding="utf-8"))
    return tuple(
        ProtectedName(name=entry["name"], domain=entry["domain"], match=entry["match"])
        for entry in data["brands"]
    )


def _comparable(text: str) -> str:
    """Case folded, look-alike characters made one: the form every comparison uses."""
    return skeleton(text.casefold()).casefold()


@cache
def _filler_forms() -> frozenset[str]:
    """The filler words in the same form, since the skeleton changes some ("m" reads "rn")."""
    return frozenset(_comparable(word) for word in FILLER_WORDS)


def words(name: str) -> tuple[str, ...]:
    """The name's words, look-alike characters made one, case folded, filler dropped."""
    fillers = _filler_forms()
    return tuple(w for w in _WORD.findall(_comparable(name)) if w not in fillers)


def slip_distance(a: str, b: str) -> int:
    """Damerau's distance (optimal string alignment): edits from `a` to `b`."""
    previous_previous: list[int] = []
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if i > 1 and j > 1 and char_a == b[j - 2] and a[i - 2] == char_b:
                current[j] = min(current[j], previous_previous[j - 2] + 1)
        previous_previous, previous = previous, current
    return previous[len(b)]


def _same(candidate: str, protected: str) -> bool:
    if candidate == protected:
        return True
    return (
        len(protected) >= MIN_LETTERS_FOR_A_SLIP
        and slip_distance(candidate, protected) <= 1
    )


def resembles(name: str, protected: ProtectedName) -> bool:
    """Whether `name` reads as `protected`'s name, whole or, for a word match, inside."""
    mine, theirs = words(name), words(protected.name)
    if not mine or not theirs:
        return False
    if _same("".join(mine), "".join(theirs)):
        return True
    if protected.match == "exact":
        return False
    size = len(theirs)
    return any(
        _same("".join(mine[start : start + size]), "".join(theirs))
        for start in range(len(mine) - size + 1)
    )


def covers(verified_domain: str | None, protected_domain: str) -> bool:
    """Whether a verified domain is the protected one, or one of its subdomains."""
    if verified_domain is None:
        return False
    verified, wanted = verified_domain.lower(), protected_domain.lower()
    return verified == wanted or verified.endswith("." + wanted)


def flag_for(
    name: str, verified_domain: str | None, protected: Iterable[ProtectedName]
) -> NameFlag | None:
    """What to tell a creator about this name, or None when there is nothing to say."""
    resembled = next(
        (
            entry
            for entry in protected
            if not covers(verified_domain, entry.domain) and resembles(name, entry)
        ),
        None,
    )
    mixed = mixes_latin_with_lookalikes(name)
    if resembled is None and not mixed:
        return None
    return NameFlag(resembles=resembled, mixed_script=mixed)


def protected_names(
    verified_on_platform: Sequence[tuple[str, str]],
) -> tuple[ProtectedName, ...]:
    """The curated list, then every brand here with a verified domain (item 74)."""
    return curated() + tuple(
        ProtectedName(name=name, domain=domain) for name, domain in verified_on_platform
    )
