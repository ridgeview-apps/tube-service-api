from datetime import UTC, date, datetime, timedelta

from app.line_status.time import (
    operational_day_bounds_london,
    operational_day_bounds_utc,
    operational_day_for,
)


def test_operational_day_changes_at_four_am_london_time() -> None:
    assert operational_day_for(datetime(2026, 6, 15, 2, 59, tzinfo=UTC)) == date(2026, 6, 14)
    assert operational_day_for(datetime(2026, 6, 15, 3, 0, tzinfo=UTC)) == date(2026, 6, 15)


def test_operational_day_bounds_are_four_am_in_london() -> None:
    start, end = operational_day_bounds_london(date(2026, 6, 15))
    start_utc, end_utc = operational_day_bounds_utc(date(2026, 6, 15))

    assert start.isoformat() == "2026-06-15T04:00:00+01:00"
    assert end.isoformat() == "2026-06-16T04:00:00+01:00"
    assert start_utc == datetime(2026, 6, 15, 3, 0, tzinfo=UTC)
    assert end_utc == datetime(2026, 6, 16, 3, 0, tzinfo=UTC)


def test_operational_days_follow_dst_transitions() -> None:
    spring_start, spring_end = operational_day_bounds_utc(date(2026, 3, 28))
    autumn_start, autumn_end = operational_day_bounds_utc(date(2026, 10, 24))

    assert spring_end - spring_start == timedelta(hours=23)
    assert autumn_end - autumn_start == timedelta(hours=25)
