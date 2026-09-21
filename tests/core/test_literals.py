"""The import-time guard that keeps API Literals and database allow-lists equal."""

import subprocess
import sys
from typing import Literal

import pytest

from app.core.literals import LiteralOutOfStep, ensure_same_values

Colour = Literal["red", "green"]


def test_matching_values_pass_whatever_the_order():
    ensure_same_values("Colour", Colour, ("green", "red"))


def test_a_value_only_in_the_allow_list_is_named():
    with pytest.raises(LiteralOutOfStep) as error:
        ensure_same_values("Colour", Colour, ("red", "green", "blue"))

    assert "Colour" in str(error.value)
    assert "only in the allow-list ['blue']" in str(error.value)


def test_a_value_only_in_the_literal_is_named():
    with pytest.raises(LiteralOutOfStep) as error:
        ensure_same_values("Colour", Colour, ("red",))

    assert "only in the Literal ['green']" in str(error.value)


def test_it_is_a_runtime_error_so_startup_fails_loudly():
    assert issubclass(LiteralOutOfStep, RuntimeError)


def test_the_guard_survives_python_optimised_mode():
    # The reason this is not an assert: under -O, asserts are removed.
    script = (
        "from typing import Literal\n"
        "from app.core.literals import LiteralOutOfStep, ensure_same_values\n"
        "try:\n"
        "    ensure_same_values('X', Literal['a'], ('b',))\n"
        "except LiteralOutOfStep:\n"
        "    print('caught')\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-O", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "caught"
