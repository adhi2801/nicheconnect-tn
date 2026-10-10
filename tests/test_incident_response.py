"""The incident plan can rotate every secret the app actually has.

A plan that forgets a secret fails on the worst day it could. On 10 October
2026 the Valkey password was found missing from the rotation table, and the
steps given for the generated keys would have had OpenTofu write the leaked
value back. These tests read the secrets from where they are defined, so a new
one cannot be added without its rotation step.
"""

import re
from pathlib import Path

from pydantic import SecretStr

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "INCIDENT_RESPONSE.md"
INFRA = ROOT / "infra" / "modules" / "app"


def rotation_section() -> str:
    text = PLAN.read_text(encoding="utf-8")
    return text[text.index("## 3. Rotating each secret") : text.index("## 4.")]


def secrets_given_to_tasks() -> set[str]:
    """Every name in the task definition's `secrets` block (compute.tf)."""
    compute = (INFRA / "compute.tf").read_text(encoding="utf-8")
    block = compute[compute.index("secrets = concat(") : compute.index("network = {")]
    return set(re.findall(r'"([A-Z][A-Z0-9_]+)"', block))


def generated_passwords() -> set[str]:
    """Every random_password OpenTofu makes, by its resource name."""
    names: set[str] = set()
    for path in INFRA.glob("*.tf"):
        text = path.read_text(encoding="utf-8")
        names.update(re.findall(r'resource "random_password" "([a-z_]+)"', text))
    return names


def secret_settings() -> set[str]:
    """Settings typed as secrets, by the environment variable that sets them."""
    return {
        name.upper()
        for name, field in Settings.model_fields.items()
        if SecretStr in (field.annotation, *getattr(field.annotation, "__args__", ()))
    }


def test_the_sources_are_read():
    # If the parsing breaks, the checks below would pass on nothing.
    assert {"DATABASE_URL", "REDIS_URL", "SECRET_KEY", "MSG91_AUTH_KEY"} <= (
        secrets_given_to_tasks()
    )
    assert {"secret_key", "otp_hash_key", "database", "cache"} <= generated_passwords()
    assert {"SECRET_KEY", "OTP_HASH_KEY", "ANTHROPIC_API_KEY"} <= secret_settings()


def test_every_secret_given_to_the_app_has_a_rotation_step():
    section = rotation_section()

    missing = sorted(
        name
        for name in secrets_given_to_tasks() | secret_settings()
        if f"`{name}`" not in section
    )

    assert missing == [], f"Not in INCIDENT_RESPONSE.md section 3: {missing}"


def test_every_generated_password_is_rotated_through_opentofu():
    # Changed in the console, the next `tofu apply` writes the leaked value back.
    section = rotation_section()

    missing = sorted(
        name
        for name in generated_passwords()
        if f"-replace=module.app.random_password.{name}`" not in section
    )

    assert missing == [], f"No `tofu apply -replace` step for: {missing}"
