"""Shared helpers for scheduler rhythm proposals."""

from __future__ import annotations

from datetime import date, datetime, timedelta

# TODO(policy.yaml): move logical day cutoff to scheduler policy.
LOGICAL_DAY_CUTOFF_HOUR = 5


def logical_day(now: datetime | None = None, cutoff_hour: int = LOGICAL_DAY_CUTOFF_HOUR) -> date:
    """Return the scheduler's logical day; pre-cutoff early morning belongs to yesterday."""
    current = now or datetime.now()
    day = current.date()
    if current.hour < cutoff_hour:
        return day - timedelta(days=1)
    return day
