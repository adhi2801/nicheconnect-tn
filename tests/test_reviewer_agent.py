"""The independent reviewer's brief keeps its rules (D-139, D-193).

The brief in `.claude/agents/fault-finder.md` is what makes every review
equally strong. These tests fail if it loses a binding standard, gains a
tool that edits files, or stops saying it is not the other founder's review.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / ".claude" / "agents" / "fault-finder.md"
STANDARDS = sorted((ROOT / "docs" / "standards").glob("*.md"))
EDITING_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def _front_matter() -> dict[str, str]:
    """Return the agent file's front matter as a name-to-value mapping."""
    text = AGENT.read_text(encoding="utf-8")
    _, block, _ = text.split("---", 2)
    pairs = (line.split(":", 1) for line in block.strip().splitlines())
    return {key.strip(): value.strip() for key, value in pairs}


def test_the_agent_has_a_name_and_description() -> None:
    meta = _front_matter()
    assert meta["name"] == "fault-finder"
    assert "D-139" in meta["description"]


def test_the_agent_cannot_edit_files() -> None:
    tools = {tool.strip() for tool in _front_matter()["tools"].split(",")}
    assert tools, "the agent must list its tools, or it inherits every one"
    assert not tools & EDITING_TOOLS


def test_there_are_standards_to_check() -> None:
    assert len(STANDARDS) >= 8


@pytest.mark.parametrize("standard", STANDARDS, ids=lambda path: path.name)
def test_the_agent_reads_every_binding_standard(standard: Path) -> None:
    body = AGENT.read_text(encoding="utf-8")
    assert f"docs/standards/{standard.name}" in body


@pytest.mark.parametrize(
    "rule",
    [
        "Read only.",
        "Never claim what you did not do.",
        "CLAUDE.md` section 2",
        "never counts as theirs",
    ],
)
def test_the_agent_keeps_its_rules(rule: str) -> None:
    assert rule in AGENT.read_text(encoding="utf-8")
