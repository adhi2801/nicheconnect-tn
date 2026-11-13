"""The backend's finish line counts what its tables say (D-191).

`docs/BACKEND_COMPLETE.md` is how the founders see how far the backend is
from complete, and its numbers were typed by hand: on 13 November 2026 it said
64 items built where its tables marked 63, and nine built items were named
under no capability, so "11 of 32 audited" could not say which built work no
audit had read. These tests make the file's own claims checkable:

- every built or partly built item is named in exactly one capability's name
  in section 2a, so auditing every capability audits everything built;
- every item a capability names exists in the tables;
- the counts in section 2 are the tables' counts.
"""

import re
from pathlib import Path

FINISH_LINE = Path(__file__).resolve().parents[1] / "docs" / "BACKEND_COMPLETE.md"

ITEM_ROW = re.compile(r"^\| *(\d+[a-z]?) *\|(.*)$", re.MULTILINE)
CAPABILITY_ROW = re.compile(r"^\| *C(\d+) *\|([^|]*)\|([^|]*)\|(.*)$", re.MULTILINE)
# "(item 81)", "(items 5, 5a, 58)", "items 24, 25 and 27": the numbers a name owns.
NAMED_ITEMS = re.compile(r"\bitems? (\d+[a-z]?(?:(?:, | and )\d+[a-z]?)*)")
BUILT = re.compile(r"\*\*Built\b")
PARTLY_BUILT = re.compile(r"\*\*(?:Piece|Step) \d+ built\b")
COUNTS = re.compile(
    r"(\d+) items listed: (\d+) built, (\d+) partly built, (\d+) open\. "
    r"Capabilities audited: (\d+) of (\d+)\."
)


def text() -> str:
    return FINISH_LINE.read_text(encoding="utf-8")


def items() -> dict[str, str]:
    """Every item row in the tables, by its number, with its status."""
    found: dict[str, str] = {}
    for number, rest in ITEM_ROW.findall(text()):
        assert number not in found, f"item {number} is listed twice"
        if BUILT.search(rest):
            found[number] = "built"
        elif PARTLY_BUILT.search(rest):
            found[number] = "partly built"
        else:
            found[number] = "open"
    return found


def capabilities() -> dict[str, tuple[list[str], str]]:
    """Each capability's number: the items its name owns, and its audit cell."""
    found: dict[str, tuple[list[str], str]] = {}
    for number, name, _benchmark, audit in CAPABILITY_ROW.findall(text()):
        owned = [
            item
            for listed in NAMED_ITEMS.findall(name)
            for item in re.split(r", | and ", listed)
        ]
        found[number] = (owned, audit.strip())
    return found


def test_the_tables_are_read() -> None:
    # A parser that finds nothing would pass every check below.
    statuses = items()
    assert len(statuses) > 140
    assert list(statuses.values()).count("built") > 60
    assert len(capabilities()) > 30


def test_every_built_item_belongs_to_exactly_one_capability() -> None:
    owners: dict[str, list[str]] = {}
    for capability, (owned, _audit) in capabilities().items():
        for item in owned:
            owners.setdefault(item, []).append(f"C{capability}")

    built = [n for n, status in items().items() if status != "open"]
    unowned = [n for n in built if n not in owners]
    shared = {n: c for n, c in owners.items() if len(c) > 1}

    assert unowned == [], f"Built items no capability names: {unowned}"
    assert shared == {}, f"Items named by more than one capability: {shared}"


def test_every_item_a_capability_names_exists() -> None:
    listed = items()
    missing = [
        f"C{capability}: item {item}"
        for capability, (owned, _audit) in capabilities().items()
        for item in owned
        if item not in listed
    ]
    assert missing == [], f"Capabilities name items not in the tables: {missing}"


def test_the_counts_in_section_2_are_the_tables_counts() -> None:
    found = COUNTS.search(text())
    assert found, "section 2 has lost its counted line"
    listed, built, partly, open_, audited, capability_count = map(int, found.groups())

    statuses = list(items().values())
    audits = [audit for _owned, audit in capabilities().values()]
    assert (listed, built, partly, open_) == (
        len(statuses),
        statuses.count("built"),
        statuses.count("partly built"),
        statuses.count("open"),
    )
    assert (audited, capability_count) == (
        sum(audit.startswith("**Audited") for audit in audits),
        len(audits),
    )


def test_section_2a_states_the_same_audited_count() -> None:
    audited = sum(a.startswith("**Audited") for _o, a in capabilities().values())
    assert f"**Audited so far: {audited} of {len(capabilities())}**" in text()
