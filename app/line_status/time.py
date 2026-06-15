from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
OPERATIONAL_DAY_START = time(hour=4)


def operational_day_for(value: datetime) -> date:
    local_value = value.astimezone(LONDON)
    if local_value.timetz().replace(tzinfo=None) < OPERATIONAL_DAY_START:
        return local_value.date() - timedelta(days=1)
    return local_value.date()


def current_operational_day() -> date:
    return operational_day_for(datetime.now(LONDON))


def operational_day_bounds_london(
    operational_date: date,
) -> tuple[datetime, datetime]:
    local_start = datetime.combine(
        operational_date,
        OPERATIONAL_DAY_START,
        tzinfo=LONDON,
    )
    local_end = datetime.combine(
        operational_date + timedelta(days=1),
        OPERATIONAL_DAY_START,
        tzinfo=LONDON,
    )
    return local_start, local_end


def operational_day_bounds_utc(operational_date: date) -> tuple[datetime, datetime]:
    local_start, local_end = operational_day_bounds_london(operational_date)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)
