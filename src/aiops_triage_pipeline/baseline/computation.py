"""Baseline computation utilities — sole source of truth for datetime-to-bucket conversions."""

from datetime import datetime, timezone


def time_to_bucket(dt: datetime) -> tuple[int, int]:
    """Convert a datetime to a (day_of_week, hour) bucket using UTC-normalized time.

    Args:
        dt: A timezone-aware datetime. Naive datetimes are rejected — callers must supply
            timezone context to prevent silent local-time-to-UTC misconversions.

    Returns:
        tuple[int, int]: (dow, hour) where dow uses datetime.weekday() convention
            (Monday=0, Tuesday=1, ..., Sunday=6) and hour is 0-23.

    Raises:
        ValueError: If dt is a naive datetime (tzinfo is None).
    """
    if dt.tzinfo is None:
        raise ValueError("time_to_bucket requires a timezone-aware datetime; got naive datetime")
    utc_dt = dt.astimezone(timezone.utc)
    return (utc_dt.weekday(), utc_dt.hour)
