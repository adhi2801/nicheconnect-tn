"""The campaign report's spreadsheet rules, without a database (item 47, D-088)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.campaigns.report_csv import (
    BYTE_ORDER_MARK,
    FORMULA_STARTS,
    rupees,
    safe_cell,
)


@pytest.mark.parametrize(
    ("paise", "shown"),
    [(800_000, "8000.00"), (150_050, "1500.50"), (5, "0.05"), (0, "0.00"), (None, "")],
)
def test_money_is_rupees_with_two_decimals_from_whole_paise(paise, shown):
    assert rupees(paise) == shown


@pytest.mark.parametrize(
    "typed",
    [
        '=HYPERLINK("https://evil.example","Open")',
        "+91 cmd|' /C calc'!A0",
        "-2+3",
        "@SUM(A1:A9)",
        "\t=1+1",
        "\r=1+1",
    ],
)
def test_a_cell_a_spreadsheet_would_run_is_written_as_text(typed):
    assert safe_cell(typed) == f"'{typed}"


@pytest.mark.parametrize(
    "typed",
    [
        "Priya Eats",
        "https://www.instagram.com/reel/abc123/",
        "3 reels - 1 story",  # a dash inside is harmless
        "பிரியா",
        "",
    ],
)
def test_ordinary_text_is_left_exactly_as_typed(typed):
    assert safe_cell(typed) == typed


def test_the_byte_order_mark_is_the_one_excel_reads_as_utf8():
    assert BYTE_ORDER_MARK.encode("utf-8") == b"\xef\xbb\xbf"


# --- for any input (D-090) ---------------------------------------------------------------


@given(st.integers(min_value=0, max_value=10**15))
def test_any_amount_reads_back_as_exactly_the_same_paise(paise):
    whole, fraction = rupees(paise).split(".")

    assert len(fraction) == 2
    assert int(whole) * 100 + int(fraction) == paise


@given(st.text(max_size=50))
def test_no_cell_can_start_a_formula(typed):
    cell = safe_cell(typed)

    assert not cell.startswith(FORMULA_STARTS)
    assert cell in (typed, f"'{typed}")
