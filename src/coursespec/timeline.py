"""상대 일수(day)를 실제 시각으로 바꾼다."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DAY_START = time(0, 0)
DAY_END = time(23, 59)


class Timeline:
    def __init__(self, start: date, tz: str) -> None:
        self.start = start
        self.tz = ZoneInfo(tz)

    def at(self, day: int, end_of_day: bool = False) -> datetime:
        d = self.start + timedelta(days=day - 1)
        return datetime.combine(d, DAY_END if end_of_day else DAY_START, self.tz)

    def unix(self, day: int | None, end_of_day: bool = False) -> int | None:
        return None if day is None else int(self.at(day, end_of_day).timestamp())

    def iso(self, day: int | None, end_of_day: bool = False) -> str | None:
        return None if day is None else self.at(day, end_of_day).isoformat()
