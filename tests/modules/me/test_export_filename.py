"""The data export's file name carries the Tamil Nadu date (D-180)."""

from datetime import UTC, datetime

from app.modules.me.export_service import export_filename


def test_the_file_is_named_for_the_day_it_is_in_tamil_nadu():
    # 01:30 on the 21st in Tamil Nadu, still the 20th in UTC.
    assert export_filename(datetime(2026, 9, 20, 20, 0, tzinfo=UTC)) == (
        "nicheconnect-export-2026-09-21.json"
    )
    assert export_filename(datetime(2026, 9, 20, 18, 29, tzinfo=UTC)) == (
        "nicheconnect-export-2026-09-20.json"
    )
