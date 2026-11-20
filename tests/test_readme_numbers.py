"""The README's countable numbers are the code's (D-191).

The README is the first page anyone outside the team reads, and it says
"every number here comes from a tool". On 13 November 2026 two of its
numbers had drifted since 6 November: 225 API routes where the contract held
226 operations, and 155 property-based tests where the suite held 151, a claim
larger than the truth. The two that can be counted cheaply are checked here
on every run; the test count and coverage are dated where they are written.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CONTRACT = ROOT / "docs" / "api" / "openapi.json"
METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


def stated(label: str) -> int:
    found = re.search(rf"\| \*\*([\d,]+)\*\* {label} \|", README.read_text("utf-8"))
    assert found, f"the README has lost its '{label}' row"
    return int(found.group(1).replace(",", ""))


def test_the_operations_are_the_contracts() -> None:
    paths = json.loads(CONTRACT.read_text("utf-8"))["paths"]
    operations = sum(1 for item in paths.values() for method in item if method in METHODS)

    assert operations > 200  # the contract was read at all
    assert stated("API operations") == operations


def test_the_property_based_tests_are_the_suites() -> None:
    given = sum(
        len(re.findall(r"^\s*@given\(", path.read_text("utf-8"), re.MULTILINE))
        for path in (ROOT / "tests").rglob("*.py")
    )

    assert given > 100  # the suite was read at all
    assert stated("property-based tests") == given
