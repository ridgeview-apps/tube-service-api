from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from time import monotonic

from app.line_status.schemas import DailyHistoryRead

type HistoryCacheKey = tuple[str, date]


@dataclass
class _CacheEntry:
    value: DailyHistoryRead
    expires_at: float


class DailyHistoryCache:
    def __init__(
        self,
        *,
        max_entries: int = 512,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._entries: dict[HistoryCacheKey, _CacheEntry] = {}
        self._max_entries = max_entries
        self._clock = clock

    def get(self, *, line_id: str, day: date) -> DailyHistoryRead | None:
        key = (line_id, day)
        entry = self._entries.get(key)
        if entry is None:
            return None

        if entry.expires_at <= self._clock():
            del self._entries[key]
            return None

        return entry.value

    def set(
        self,
        *,
        line_id: str,
        day: date,
        value: DailyHistoryRead,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return

        self._remove_expired_entries()
        key = (line_id, day)
        if key not in self._entries and len(self._entries) >= self._max_entries:
            oldest_key = next(iter(self._entries))
            del self._entries[oldest_key]

        self._entries[key] = _CacheEntry(
            value=value,
            expires_at=self._clock() + ttl_seconds,
        )

    def clear(self) -> None:
        self._entries.clear()

    def _remove_expired_entries(self) -> None:
        current_time = self._clock()
        expired_keys = [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= current_time
        ]
        for key in expired_keys:
            del self._entries[key]


daily_history_cache = DailyHistoryCache()
