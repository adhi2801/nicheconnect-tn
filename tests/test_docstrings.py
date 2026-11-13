"""Every module and every public service function says what it does (D-192).

`docs/standards/backend.md` section 10: "Every module and every public service
function has a docstring: what it does, why it is built this way, and what it
raises." Until 13 November 2026 that rule was review only, and 20 modules and
over 30 public service functions had none. This makes it a check.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def modules() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if p.stat().st_size > 0)


def is_service(path: Path) -> bool:
    return path.name == "service.py" or path.name.endswith("_service.py")


def test_the_code_is_read() -> None:
    files = modules()
    assert len(files) > 300
    assert sum(is_service(p) for p in files) > 40


def test_every_module_has_a_docstring() -> None:
    missing = [
        p.relative_to(APP.parent).as_posix()
        for p in modules()
        if p.name != "__init__.py"
        and ast.get_docstring(ast.parse(p.read_text("utf-8"))) is None
    ]
    assert missing == [], "Modules without a docstring:\n" + "\n".join(missing)


def test_every_public_service_function_has_a_docstring() -> None:
    missing = []
    for path in filter(is_service, modules()):
        tree = ast.parse(path.read_text("utf-8"))
        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and not node.name.startswith("_")
                and ast.get_docstring(node) is None
            ):
                missing.append(
                    f"{path.relative_to(APP.parent).as_posix()}:{node.lineno} {node.name}"
                )
    assert missing == [], "Public service functions without a docstring:\n" + "\n".join(
        missing
    )
