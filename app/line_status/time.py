from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def today_in_london() -> date:
    return datetime.now(LONDON).date()


def london_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    local_start = datetime.combine(day, time.min, tzinfo=LONDON)
    local_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LONDON)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)
