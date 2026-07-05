from datetime import UTC, datetime


def utc_seconds_isoformat(value: datetime) -> str:
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
