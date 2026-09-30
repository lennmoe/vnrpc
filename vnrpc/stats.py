"""Reading-history helpers for the Library (pure functions over a game entry's
``daily`` map of ``"YYYY-MM-DD" -> seconds read that day``)."""
from __future__ import annotations

import datetime as dt
import time
from typing import Mapping


def _today(today: dt.date | None) -> dt.date:
    return today or dt.date.today()


def short_date(day: dt.date, today: dt.date | None = None) -> str:
    """``"29 Sep"``, or ``"29 Sep 2025"`` outside the current year."""
    label = f"{day.day} {day.strftime('%b')}"
    return label if day.year == _today(today).year else f"{label} {day.year}"


def daily_series(daily: Mapping[str, int] | None, days: int = 30,
                 today: dt.date | None = None) -> list[tuple[dt.date, int]]:
    """Seconds read on each of the last ``days`` days, oldest first."""
    daily = daily or {}
    end = _today(today)
    out = []
    for back in range(days - 1, -1, -1):
        day = end - dt.timedelta(days=back)
        out.append((day, int(daily.get(day.isoformat(), 0))))
    return out


def weekly_series(daily: Mapping[str, int] | None, weeks: int = 12,
                  today: dt.date | None = None) -> list[tuple[dt.date, int]]:
    """Seconds read in each of the last ``weeks`` weeks (Monday-based), oldest first."""
    daily = daily or {}
    end = _today(today)
    this_monday = end - dt.timedelta(days=end.weekday())
    first_monday = this_monday - dt.timedelta(weeks=weeks - 1)
    totals = {first_monday + dt.timedelta(weeks=i): 0 for i in range(weeks)}
    for key, seconds in daily.items():
        try:
            day = dt.date.fromisoformat(key)
        except (TypeError, ValueError):
            continue
        monday = day - dt.timedelta(days=day.weekday())
        if monday in totals and day <= end:
            totals[monday] += int(seconds)
    return sorted(totals.items())


def this_week_seconds(daily: Mapping[str, int] | None, today: dt.date | None = None) -> int:
    return weekly_series(daily, weeks=1, today=today)[0][1]


def first_day(daily: Mapping[str, int] | None) -> dt.date | None:
    days = []
    for key in daily or {}:
        try:
            days.append(dt.date.fromisoformat(key))
        except (TypeError, ValueError):
            continue
    return min(days) if days else None


def last_played_text(timestamp: int | float | None, now: float | None = None) -> str:
    """``"today"``, ``"yesterday"``, ``"3 days ago"``, else a short date; ``""`` if never."""
    if not timestamp:
        return ""
    now = time.time() if now is None else now
    day = dt.date.fromtimestamp(timestamp)
    today = dt.date.fromtimestamp(now)
    delta = (today - day).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "yesterday"
    if delta < 7:
        return f"{delta} days ago"
    return short_date(day, today)
