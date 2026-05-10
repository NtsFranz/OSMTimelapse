"""Date range utilities for generating time steps."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator


def generate_dates(
    start: date,
    end: date,
    interval: str = "monthly",
) -> Iterator[date]:
    """Generate a sequence of dates between start and end at the given interval.

    Args:
        start: First date in the range (inclusive).
        end: Last date in the range (inclusive).
        interval: One of 'daily', 'weekly', 'monthly', 'quarterly', 'yearly'.

    Yields:
        Dates at each time step.
    """
    current = start
    while current <= end:
        yield current
        current = _advance(current, interval)


def _advance(d: date, interval: str) -> date:
    """Advance a date by one interval step."""
    if interval == "daily":
        return d + timedelta(days=1)
    elif interval == "weekly":
        return d + timedelta(weeks=1)
    elif interval == "monthly":
        return _add_months(d, 1)
    elif interval == "quarterly":
        return _add_months(d, 3)
    elif interval == "yearly":
        return _add_months(d, 12)
    else:
        raise ValueError(f"Unknown interval: {interval!r}")


def _add_months(d: date, months: int) -> date:
    """Add months to a date, clamping to end of month if needed."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    # Clamp day to valid range for the target month
    import calendar

    max_day = calendar.monthrange(year, month)[1]
    day = min(d.day, max_day)
    return date(year, month, day)


def format_iso(d: date) -> str:
    """Format a date as an ISO 8601 timestamp for osmium."""
    return d.isoformat() + "T00:00:00Z"
