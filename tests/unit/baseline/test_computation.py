"""Unit tests for baseline/computation.py.

Story 1.1: Baseline Constants & Time Bucket Derivation
AC 2: Wednesday UTC 14:00 → (2, 14)
AC 3: Non-UTC datetime is converted to UTC before bucket derivation
AC 4: dow is always 0–6, hour is always 0–23; function is sole conversion source
"""

from datetime import datetime, timedelta, timezone

from aiops_triage_pipeline.baseline.computation import time_to_bucket

# ---------------------------------------------------------------------------
# AC 2: UTC datetime → correct (dow, hour) bucket
# ---------------------------------------------------------------------------


def test_time_to_bucket_wednesday_14_utc() -> None:
    """[P1] Given Wednesday 14:00 UTC, time_to_bucket returns (2, 14).

    Jan 7 2026 is a Wednesday. weekday() == 2 for Wednesday.
    """
    # GIVEN: a UTC datetime for Wednesday at 14:00
    dt = datetime(2026, 1, 7, 14, 0, 0, tzinfo=timezone.utc)

    # WHEN: time_to_bucket() is called
    result = time_to_bucket(dt)

    # THEN: returns (2, 14) — Wednesday (weekday()==2), hour 14
    assert result == (2, 14)


def test_time_to_bucket_monday_midnight_utc() -> None:
    """[P1] Given Monday 00:00 UTC, time_to_bucket returns (0, 0).

    Jan 5 2026 is a Monday. weekday() == 0. Midnight == hour 0.
    """
    dt = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
    assert time_to_bucket(dt) == (0, 0)


def test_time_to_bucket_saturday_23_utc() -> None:
    """[P1] Given Saturday 23:00 UTC, time_to_bucket returns (5, 23).

    Jan 10 2026 is a Saturday. weekday() == 5. End-of-day hour == 23.
    """
    dt = datetime(2026, 1, 10, 23, 0, 0, tzinfo=timezone.utc)
    assert time_to_bucket(dt) == (5, 23)


def test_time_to_bucket_sunday_midnight_utc() -> None:
    """[P1] Given Sunday 00:00 UTC (midnight), time_to_bucket returns (6, 0).

    Jan 11 2026 is a Sunday. weekday() == 6. Midnight == hour 0.
    """
    dt = datetime(2026, 1, 11, 0, 0, 0, tzinfo=timezone.utc)
    assert time_to_bucket(dt) == (6, 0)


# ---------------------------------------------------------------------------
# AC 3: Non-UTC datetimes are normalized to UTC before bucket derivation
# ---------------------------------------------------------------------------


def test_time_to_bucket_non_utc_converts_to_utc() -> None:
    """[P1] Given UTC+5 datetime at local Wednesday 19:00, returns (2, 14).

    UTC+5, local Wednesday 19:00 == UTC Wednesday 14:00.
    time_to_bucket must call .astimezone(timezone.utc) before extracting fields.
    """
    # GIVEN: a non-UTC datetime (UTC+5), local Wednesday 19:00
    utc_plus_5 = timezone(timedelta(hours=5))
    dt = datetime(2026, 1, 7, 19, 0, 0, tzinfo=utc_plus_5)

    # WHEN: time_to_bucket() is called
    result = time_to_bucket(dt)

    # THEN: returns (2, 14) — UTC-normalized Wednesday 14:00
    assert result == (2, 14)


def test_time_to_bucket_timezone_boundary_thursday_to_wednesday_utc() -> None:
    """[P1] Given UTC+5 Thursday 01:00 local → UTC Wednesday 20:00, returns (2, 20).

    Jan 8 2026 is a Thursday. In UTC+5, Thursday local 01:00 == UTC Wednesday 20:00.
    This tests a timezone day-boundary crossing.
    """
    # GIVEN: UTC+5 datetime, local Thursday Jan 8 at 01:00
    utc_plus_5 = timezone(timedelta(hours=5))
    dt = datetime(2026, 1, 8, 1, 0, 0, tzinfo=utc_plus_5)

    # WHEN: time_to_bucket() is called
    result = time_to_bucket(dt)

    # THEN: UTC-normalized to Wednesday 20:00 → (2, 20)
    assert result == (2, 20)


def test_time_to_bucket_negative_offset_advances_day() -> None:
    """[P1] Given UTC-5 Sunday 22:00 local → UTC Monday 03:00, returns (0, 3).

    Jan 11 2026 is a Sunday. UTC-5, Sunday 22:00 == UTC Monday Jan 12 03:00.
    Tests a timezone boundary crossing that advances the day-of-week.
    """
    # GIVEN: UTC-5 datetime, local Sunday Jan 11 at 22:00
    utc_minus_5 = timezone(timedelta(hours=-5))
    dt = datetime(2026, 1, 11, 22, 0, 0, tzinfo=utc_minus_5)

    # WHEN: time_to_bucket() is called
    result = time_to_bucket(dt)

    # THEN: UTC-normalized to Monday 03:00 → (0, 3)
    assert result == (0, 3)


# ---------------------------------------------------------------------------
# AC 4: Output range guarantees — dow in 0–6, hour in 0–23
# ---------------------------------------------------------------------------


def test_time_to_bucket_dow_in_valid_range() -> None:
    """[P1] dow component of all buckets is in range 0–6 (Mon=0, Sun=6)."""
    # GIVEN: one datetime per day of the week
    # Jan 5–11 2026 spans Monday through Sunday
    week = [
        datetime(2026, 1, 5 + i, 12, 0, 0, tzinfo=timezone.utc) for i in range(7)
    ]

    for dt in week:
        dow, hour = time_to_bucket(dt)
        assert 0 <= dow <= 6, f"dow={dow} out of range for {dt}"
        assert 0 <= hour <= 23, f"hour={hour} out of range for {dt}"


def test_time_to_bucket_hour_in_valid_range() -> None:
    """[P1] hour component covers full 0–23 range for all hours in a day."""
    # GIVEN: one datetime per hour of a single day
    all_hours = [
        datetime(2026, 1, 7, h, 0, 0, tzinfo=timezone.utc) for h in range(24)
    ]

    for dt in all_hours:
        dow, hour = time_to_bucket(dt)
        assert hour == dt.hour, f"Expected hour={dt.hour}, got {hour}"
        assert 0 <= dow <= 6


def test_time_to_bucket_return_type_is_tuple_of_ints() -> None:
    """[P1] time_to_bucket returns a tuple[int, int] (not floats or strings)."""
    dt = datetime(2026, 1, 7, 14, 0, 0, tzinfo=timezone.utc)
    result = time_to_bucket(dt)

    assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
    assert len(result) == 2, f"Expected 2-tuple, got length {len(result)}"
    dow, hour = result
    assert isinstance(dow, int), f"dow should be int, got {type(dow)}"
    assert isinstance(hour, int), f"hour should be int, got {type(hour)}"


# ---------------------------------------------------------------------------
# Defensive: naive datetime raises ValueError (consistent with project patterns)
# ---------------------------------------------------------------------------


def test_time_to_bucket_raises_for_naive_datetime() -> None:
    """[P1] time_to_bucket raises ValueError for naive datetimes (no tzinfo).

    Consistent with project-wide pattern: all datetime-accepting functions reject
    naive datetimes to prevent silent local-time-to-UTC misconversions.
    """
    import pytest

    naive_dt = datetime(2026, 1, 7, 14, 0, 0)  # no tzinfo
    with pytest.raises(ValueError, match="naive datetime"):
        time_to_bucket(naive_dt)


# ---------------------------------------------------------------------------
# AC 4 (P3): weekday() convention — NOT isoweekday()
# ---------------------------------------------------------------------------


def test_time_to_bucket_uses_weekday_not_isoweekday() -> None:
    """[P2] time_to_bucket uses weekday() (Mon=0, Sun=6), not isoweekday() (Mon=1, Sun=7).

    Monday: weekday()==0, isoweekday()==1
    Sunday: weekday()==6, isoweekday()==7
    """
    # GIVEN: a Monday (Jan 5 2026)
    monday = datetime(2026, 1, 5, 10, 0, 0, tzinfo=timezone.utc)
    dow_monday, _ = time_to_bucket(monday)
    assert dow_monday == 0, f"Monday should be dow=0 (weekday), got {dow_monday}"

    # GIVEN: a Sunday (Jan 11 2026)
    sunday = datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc)
    dow_sunday, _ = time_to_bucket(sunday)
    assert dow_sunday == 6, f"Sunday should be dow=6 (weekday), got {dow_sunday}"
