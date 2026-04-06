"""Baseline computation utilities — datetime-to-bucket derivation and MAD computation engine."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from aiops_triage_pipeline.baseline.constants import (
    MAD_CONSISTENCY_CONSTANT,
    MAD_THRESHOLD,
    MIN_BUCKET_SAMPLES,
)


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


# ---------------------------------------------------------------------------
# MAD Computation Engine — Story 2.1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MADResult:
    """Result of a successful MAD computation for a single metric observation."""

    is_deviation: bool
    deviation_direction: Literal["HIGH", "LOW"]
    deviation_magnitude: float  # raw modified z-score (signed; negative = LOW)
    baseline_value: float  # median of the historical bucket
    current_value: float  # the observation evaluated


def _median(values: Sequence[float]) -> float:
    """Compute median of a non-empty sequence using a sorted-list approach."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def compute_modified_z_score(
    historical_values: Sequence[float],
    current_value: float,
) -> MADResult | None:
    """Compute modified z-score for current_value against historical baseline bucket.

    Uses Median Absolute Deviation (MAD) as an outlier-resistant dispersion estimator.
    The modified z-score is scaled by MAD_CONSISTENCY_CONSTANT (0.6745) to make MAD
    a consistent estimator of the standard deviation under a normal distribution.

    Args:
        historical_values: Historical observations for the current (dow, hour) bucket.
                           Must contain at least MIN_BUCKET_SAMPLES values for computation.
        current_value: The current metric observation to evaluate.

    Returns:
        MADResult with is_deviation flag, direction, magnitude, baseline, and current value.
        Returns None if:
          - len(historical_values) < MIN_BUCKET_SAMPLES (sparse data guard, FR6/NFR-R3)
          - MAD == 0.0 (all values identical — zero-MAD edge case)
    """
    if len(historical_values) < MIN_BUCKET_SAMPLES:
        return None

    if not math.isfinite(current_value):
        return None  # NaN/Inf current value — cannot compute a meaningful z-score

    if not all(math.isfinite(v) for v in historical_values):
        return None  # NaN/Inf in historical data — cannot compute a reliable baseline

    median = _median(historical_values)
    absolute_deviations = [abs(v - median) for v in historical_values]
    mad = _median(absolute_deviations)

    if mad == 0.0:
        return None  # All historical values identical — cannot compute z-score

    modified_z_score = (current_value - median) / (mad / MAD_CONSISTENCY_CONSTANT)
    is_deviation = abs(modified_z_score) >= MAD_THRESHOLD
    deviation_direction: Literal["HIGH", "LOW"] = "HIGH" if current_value >= median else "LOW"

    return MADResult(
        is_deviation=is_deviation,
        deviation_direction=deviation_direction,
        deviation_magnitude=modified_z_score,
        baseline_value=median,
        current_value=current_value,
    )
