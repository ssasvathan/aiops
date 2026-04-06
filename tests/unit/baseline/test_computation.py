"""Unit tests for baseline/computation.py.

Story 1.1: Baseline Constants & Time Bucket Derivation
AC 2: Wednesday UTC 14:00 → (2, 14)
AC 3: Non-UTC datetime is converted to UTC before bucket derivation
AC 4: dow is always 0–6, hour is always 0–23; function is sole conversion source

Story 2.1: MAD Computation Engine
AC 1–6: compute_modified_z_score() — modified z-score, deviation classification, direction,
         magnitude/baseline/current result, sparse data skip, zero-MAD edge case
"""

from datetime import datetime, timedelta, timezone

import pytest

from aiops_triage_pipeline.baseline.computation import (
    MADResult,
    compute_modified_z_score,
    time_to_bucket,
)
from aiops_triage_pipeline.baseline.constants import MAD_CONSISTENCY_CONSTANT, MAD_THRESHOLD

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


# ---------------------------------------------------------------------------
# compute_modified_z_score — AC 1–6 (Story 2.1)
# ---------------------------------------------------------------------------


def test_compute_mad_normal_deviation_above() -> None:
    """[P0] AC1, AC2, AC3: High deviation above baseline detected correctly."""
    # GIVEN: 5 historical values and a current value well above the median
    historical = [10.0, 11.0, 10.0, 10.5, 10.5]
    current = 50.0  # well above median (~10.5)

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, current)

    # THEN: deviation detected as HIGH with magnitude exceeding threshold
    assert result is not None
    assert result.is_deviation is True
    assert result.deviation_direction == "HIGH"
    assert result.deviation_magnitude > MAD_THRESHOLD


def test_compute_mad_normal_deviation_below() -> None:
    """[P0] AC1, AC2, AC3: Low deviation below baseline detected correctly."""
    # GIVEN: 5 historical values and a current value well below the median
    historical = [10.0, 11.0, 10.0, 10.5, 10.5]
    current = -20.0  # well below median (~10.5)

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, current)

    # THEN: deviation detected as LOW with negative magnitude exceeding threshold
    assert result is not None
    assert result.is_deviation is True
    assert result.deviation_direction == "LOW"
    assert result.deviation_magnitude < -MAD_THRESHOLD


def test_compute_mad_no_deviation() -> None:
    """[P0] AC1, AC2: No deviation when current is close to the median."""
    # GIVEN: 5 historical values with spread (MAD > 0) and a current value near the median
    historical = [9.0, 10.0, 11.0, 12.0, 13.0]  # median=11.0, MAD=2.0
    current = 11.2  # within normal range — z-score well below MAD_THRESHOLD

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, current)

    # THEN: no deviation reported
    assert result is not None
    assert result.is_deviation is False


def test_compute_mad_sparse_data_skip() -> None:
    """[P0] AC5 (FR6, NFR-R3): Returns None when fewer than MIN_BUCKET_SAMPLES values."""
    # GIVEN: only 2 historical values (less than MIN_BUCKET_SAMPLES = 3)
    historical = [10.0, 11.0]

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, 50.0)

    # THEN: computation is skipped, None returned
    assert result is None


def test_compute_mad_exactly_min_samples() -> None:
    """[P1] AC5: Exactly MIN_BUCKET_SAMPLES values — computation proceeds, not skipped."""
    # GIVEN: exactly MIN_BUCKET_SAMPLES (3) historical values
    historical = [10.0, 11.0, 12.0]  # exactly 3 = MIN_BUCKET_SAMPLES

    # WHEN: compute_modified_z_score() is called with a current far above median
    result = compute_modified_z_score(historical, 50.0)

    # THEN: a result is returned (computation was not skipped)
    assert result is not None


def test_compute_mad_zero_mad() -> None:
    """[P0] AC6: All identical historical values → MAD=0 → returns None (no ZeroDivisionError)."""
    # GIVEN: 5 identical historical values (MAD = 0)
    historical = [10.0, 10.0, 10.0, 10.0, 10.0]

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, 20.0)

    # THEN: None returned — no deviation possible when all history is identical
    assert result is None


def test_compute_mad_boundary_threshold_is_deviation() -> None:
    """[P1] AC2: z-score exactly == MAD_THRESHOLD is deviating (>= boundary inclusive)."""
    # GIVEN: historical=[0,1,2,3,4] → median=2, MAD=1
    # sigma_hat = MAD / MAD_CONSISTENCY_CONSTANT = 1 / 0.6745
    # target current so z = (current - 2) / (1/0.6745) == MAD_THRESHOLD (4.0)
    # → current = 2 + MAD_THRESHOLD * (1/MAD_CONSISTENCY_CONSTANT)
    historical = [0.0, 1.0, 2.0, 3.0, 4.0]
    sigma_hat = 1.0 / MAD_CONSISTENCY_CONSTANT
    current = 2.0 + MAD_THRESHOLD * sigma_hat  # z exactly == 4.0

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, current)

    # THEN: boundary value is classified as deviating
    assert result is not None
    assert result.is_deviation is True
    assert abs(result.deviation_magnitude - MAD_THRESHOLD) < 1e-9


def test_compute_mad_returns_correct_baseline_and_current() -> None:
    """[P1] AC4: baseline_value equals the median of historical; current_value equals the input."""
    # GIVEN: historical values with a known median (12.0) and a specific current
    historical = [8.0, 10.0, 12.0, 14.0, 16.0]  # sorted: median = 12.0
    current = 50.0

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, current)

    # THEN: result carries the correct baseline (median) and current value
    assert result is not None
    assert result.baseline_value == 12.0
    assert result.current_value == current


def test_compute_mad_magnitude_signed_positive_for_high() -> None:
    """[P1] AC4: deviation_magnitude is positive (unsigned sign) when direction is HIGH."""
    # GIVEN: historical values and a current far above the median
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]  # median = 10.0
    current = 50.0  # above median

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, current)

    # THEN: magnitude is positive for HIGH direction
    assert result is not None
    assert result.deviation_direction == "HIGH"
    assert result.deviation_magnitude > 0


def test_compute_mad_magnitude_signed_negative_for_low() -> None:
    """[P1] AC4: deviation_magnitude is negative when direction is LOW."""
    # GIVEN: historical values and a current far below the median
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]  # median = 10.0
    current = -50.0  # well below median

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, current)

    # THEN: magnitude is negative for LOW direction
    assert result is not None
    assert result.deviation_direction == "LOW"
    assert result.deviation_magnitude < 0


# ---------------------------------------------------------------------------
# MADResult dataclass integrity — frozen immutability and type assertions
# ---------------------------------------------------------------------------


def test_mad_result_is_frozen_dataclass() -> None:
    """[P1] MADResult is frozen — mutation must raise FrozenInstanceError."""
    # GIVEN: a valid MADResult from computation
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]
    result = compute_modified_z_score(historical, 50.0)
    assert result is not None
    assert isinstance(result, MADResult)

    # WHEN/THEN: attempting to mutate any field raises an error
    with pytest.raises(Exception):  # FrozenInstanceError (dataclasses.FrozenInstanceError)
        result.is_deviation = False  # type: ignore[misc]


def test_mad_result_type_assertions() -> None:
    """[P1] MADResult fields carry correct types (not just truthy values)."""
    # GIVEN: a valid MADResult
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]
    result = compute_modified_z_score(historical, 50.0)
    assert result is not None

    # THEN: is_deviation is strictly bool (not int/truthy), fields are float
    assert isinstance(result.is_deviation, bool)
    assert isinstance(result.deviation_magnitude, float)
    assert isinstance(result.baseline_value, float)
    assert isinstance(result.current_value, float)
    assert result.deviation_direction in ("HIGH", "LOW")


# ---------------------------------------------------------------------------
# Non-finite input guard — NaN and Inf protection (Task 1.2 isfinite guard)
# ---------------------------------------------------------------------------


def test_compute_mad_nan_current_value_returns_none() -> None:
    """[P1] NaN as current_value must return None — non-finite inputs cannot produce valid z-scores.
    """
    # GIVEN: valid historical values but NaN as current observation
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]

    # WHEN: compute_modified_z_score() is called with NaN
    result = compute_modified_z_score(historical, float("nan"))

    # THEN: None returned — NaN cannot produce a meaningful z-score
    assert result is None


def test_compute_mad_inf_current_value_returns_none() -> None:
    """[P1] Inf as current_value must return None — non-finite values corrupt deviation magnitude.
    """
    # GIVEN: valid historical values but Inf as current observation
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]

    # WHEN: compute_modified_z_score() is called with Inf
    result = compute_modified_z_score(historical, float("inf"))

    # THEN: None returned — Inf cannot produce a bounded z-score
    assert result is None


def test_compute_mad_nan_in_historical_returns_none() -> None:
    """[P1] NaN in historical_values must return None — NaN corrupts median/MAD computation."""
    # GIVEN: historical values containing NaN
    historical = [8.0, 9.0, float("nan"), 11.0, 12.0]

    # WHEN: compute_modified_z_score() is called
    result = compute_modified_z_score(historical, 10.0)

    # THEN: None returned — NaN in baseline data cannot produce a reliable median
    assert result is None
