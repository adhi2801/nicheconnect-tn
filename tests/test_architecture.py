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


def request_bodies() -> dict[type, str]:
    """Every request body model the API accepts, with a route taking it.

    Routers are nested inside included-router objects in this FastAPI, so
    the endpoints are flattened the way the error handlers do it.
    """
    from fastapi.routing import APIRoute

    from app.core.errors import _leaf_routes
    from app.main import app

    found: dict[type, str] = {}
    for route in _leaf_routes(app.routes):
        if isinstance(route, APIRoute) and route.body_field is not None:
            model = route.body_field.field_info.annotation
            # Raw bodies are parsed by hand, not mapped onto fields: Meta's
            # form callbacks (D-134), whose one field is read and verified.
            if isinstance(model, type) and model is not bytes:
                found[model] = f"{sorted(route.methods)[0]} {route.path}"
    return found


def test_the_request_bodies_are_found():
    """Guards the test below: with no bodies found it would pass, checking
    nothing, which is what its first version did."""
    assert len(request_bodies()) >= 30


def test_every_request_body_refuses_unknown_fields():
    """backend.md section 4: unknown fields are refused, which blocks mass
    assignment (OWASP API3:2023). Enforced here since D-099's docs pass."""
    open_bodies = [
        f"{model.__name__} ({where})"
        for model, where in request_bodies().items()
        if model.model_config.get("extra") != "forbid"
    ]

    assert open_bodies == []


def test_settings_are_read_only_through_config():
    """backend.md section 8: no os.getenv or os.environ outside app/core/config.py."""
    offenders = [
        path.relative_to(MODULES.parent.parent).as_posix()
        for path in (MODULES.parent).rglob("*.py")
        if "__pycache__" not in path.parts
        and path.name != "config.py"
        and (
            "os.getenv" in path.read_text(encoding="utf-8")
            or "os.environ" in path.read_text(encoding="utf-8")
        )
    ]

    assert offenders == []
