"""The committed copy of the API contract, and the command that refreshes it.

`docs/api/openapi.json` is the contract the frontend will build against
(backend.md section 2: "OpenAPI is the contract"). tests/test_api_contract.py
fails whenever the running app's contract differs from it, so every change
to the API shows up in a pull request as a diff in this one file, where a
reviewer can see it, instead of passing unnoticed.

When a change is intended, refresh the copy and commit it with the change:

    venv\\Scripts\\python.exe -m tests.openapi_snapshot
"""

import json
from pathlib import Path
from typing import Any

SNAPSHOT = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.json"


def render(spec: dict[str, Any]) -> str:
    """Stable text: sorted keys and fixed indentation, so diffs are minimal."""
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def current() -> dict[str, Any]:
    from app.main import app

    spec: dict[str, Any] = app.openapi()
    return spec


def committed() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return loaded


if __name__ == "__main__":
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(render(current()), encoding="utf-8", newline="\n")
    print(f"Wrote {SNAPSHOT}")
