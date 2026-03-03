"""Stage 2 peak-classification models."""

from datetime import datetime
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, model_validator

PeakState = Literal["PEAK", "NEAR_PEAK", "OFF_PEAK", "UNKNOWN"]
PeakScope = tuple[str, str, str]
RecomputeFrequency = Literal["daily", "weekly", "monthly"]


class PeakProfile(BaseModel, frozen=True):
    """Baseline profile for one (env, cluster_id, topic) scope."""

    scope: PeakScope
    source_metric: str
    peak_threshold_value: float
    near_peak_threshold_value: float
    history_samples_count: int
    has_sufficient_history: bool
    recompute_frequency: RecomputeFrequency
    computed_at: datetime
    history_days_target: int = 7


class PeakClassification(BaseModel, frozen=True):
    """Classification output for one (env, cluster_id, topic) scope."""

    scope: PeakScope
    state: PeakState
    current_value: float | None
    confidence: float
    reason_codes: tuple[str, ...]
    is_peak_window: bool
    is_near_peak_window: bool
    peak_threshold_value: float | None
    near_peak_threshold_value: float | None


class PeakWindowContext(BaseModel, frozen=True):
    """Downstream-friendly view for AG4/AG6 style consumers."""

    classification: PeakState
    is_peak_window: bool
    is_near_peak_window: bool
    confidence: float
    reason_codes: tuple[str, ...]


class PeakStageOutput(BaseModel, frozen=True):
    """Stage 2 output keyed by normalized scope."""

    profiles_by_scope: Mapping[PeakScope, PeakProfile]
    classifications_by_scope: Mapping[PeakScope, PeakClassification]
    peak_context_by_scope: Mapping[PeakScope, PeakWindowContext]

    @model_validator(mode="after")
    def _freeze_nested_mappings(self) -> "PeakStageOutput":
        object.__setattr__(
            self,
            "profiles_by_scope",
            MappingProxyType(dict(self.profiles_by_scope)),
        )
        object.__setattr__(
            self,
            "classifications_by_scope",
            MappingProxyType(dict(self.classifications_by_scope)),
        )
        object.__setattr__(
            self,
            "peak_context_by_scope",
            MappingProxyType(dict(self.peak_context_by_scope)),
        )
        return self
