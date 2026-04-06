"""Baseline deviation domain models — Story 2.2.

Implements:
- BaselineDeviationContext: per-metric deviation context for BASELINE_DEVIATION findings.
- BaselineDeviationStageOutput: output of the baseline deviation pipeline stage.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from aiops_triage_pipeline.models.anomaly import AnomalyFinding


class BaselineDeviationContext(BaseModel, frozen=True):
    """Per-metric deviation context carried in BASELINE_DEVIATION findings.

    Provides full offline replay context per NFR-A2: every emitted finding
    includes metric_key, deviation_direction, deviation_magnitude, baseline_value,
    current_value, and time_bucket.

    Note: No cross-field validator enforces that deviation_magnitude sign matches
    deviation_direction (e.g. negative magnitude with "HIGH" direction). Consistency
    is enforced at the construction site in the baseline deviation stage (Story 2.3),
    where deviation_direction and deviation_magnitude are derived from the same MAD
    computation result (MADResult). This model is kept simple and data-only.
    """

    metric_key: str
    deviation_direction: Literal["HIGH", "LOW"]
    deviation_magnitude: float  # Modified z-score (signed; negative = LOW)
    baseline_value: float  # Median of the historical bucket
    current_value: float  # The observed value being evaluated
    time_bucket: tuple[int, int]  # (dow, hour) bucket — output of time_to_bucket()


class BaselineDeviationStageOutput(BaseModel, frozen=True):
    """Output of the baseline deviation stage for one pipeline cycle.

    Follows the existing stage output pattern (PeakStageOutput, etc.): frozen
    Pydantic model with findings tuple and summary counters. Per-scope breakdowns
    belong in OTLP counters and DEBUG-level structured logs, not in this model.
    """

    findings: tuple[AnomalyFinding, ...]
    scopes_evaluated: int
    deviations_detected: int
    deviations_suppressed_single_metric: int
    deviations_suppressed_dedup: int
    evaluation_time: datetime


# Pydantic v2: AnomalyFinding references BaselineDeviationContext via a TYPE_CHECKING guard
# in models/anomaly.py (to avoid circular imports at runtime). The field annotation is left
# as a ForwardRef until model_rebuild() is called. Once BaselineDeviationContext is defined
# above, we rebuild AnomalyFinding so Pydantic can resolve the forward reference and support
# model_validate() from dicts (e.g. deserialized from Redis/JSON) that contain a nested
# baseline_context payload.
AnomalyFinding.model_rebuild()
