"""The rules of backend.md section 1 that the layer contract cannot see (D-099).

`lint-imports` checks which module imports which. These check what a file of
each kind may import at all: a router never queries the database itself, and
a service never knows about HTTP. Three routers had drifted into querying
directly before this test existed.
"""

import ast
from pathlib import Path

import pytest

MODULES = Path(__file__).resolve().parents[1] / "app" / "modules"
# What a query looks like when it is written in a router.
QUERY_BUILDERS = {"select", "insert", "update", "delete", "text"}


def files(suffix: str) -> list[Path]:
    return sorted(p for p in MODULES.rglob(f"*{suffix}") if "__pycache__" not in p.parts)


def imports_of(path: Path) -> list[tuple[str, set[str]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.module or "", {alias.name for alias in node.names})
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]


def name(path: Path) -> str:
    return path.relative_to(MODULES.parent.parent).as_posix()


@pytest.mark.parametrize("router", files("router.py"), ids=name)
def test_a_router_never_builds_a_query(router):
    builders = {
        alias
        for module, aliases in imports_of(router)
        if module == "sqlalchemy" or module.startswith("sqlalchemy.")
        for alias in aliases & QUERY_BUILDERS
    }

    assert builders == set(), f"{name(router)} builds a query; move it into a service"


@pytest.mark.parametrize("service", files("service.py"), ids=name)
def test_a_service_never_imports_the_web_framework(service):
    web = [
        module
        for module, _ in imports_of(service)
        if module.split(".")[0] in {"fastapi", "starlette"}
    ]

    assert web == [], f"{name(service)} imports {web}; HTTP belongs in the router"


def test_every_module_is_a_package():
    """A folder without __init__.py is invisible to the layer contract (D-099)."""
    missing = [
        p.name
        for p in MODULES.iterdir()
        if p.is_dir() and p.name != "__pycache__" and not (p / "__init__.py").exists()
    ]

    assert (MODULES / "__init__.py").exists()
    assert missing == []
