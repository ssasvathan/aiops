"""Stage 2 peak-classification helpers."""

import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Sequence

from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.evidence import EvidenceRow
from aiops_triage_pipeline.models.peak import (
    PeakClassification,
    PeakProfile,
    PeakScope,
    PeakStageOutput,
    PeakWindowContext,
)

DEFAULT_PEAK_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "config/policies/peak-policy-v1.yaml"
)
DEFAULT_REDIS_TTL_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "config/policies/redis-ttl-policy-v1.yaml"
)
_TOPIC_MESSAGES_METRIC_KEY = "topic_messages_in_per_sec"


def load_peak_policy(path: Path = DEFAULT_PEAK_POLICY_PATH) -> PeakPolicyV1:
    """Load and validate peak-policy-v1."""
    return load_policy_yaml(path, PeakPolicyV1)


def load_redis_ttl_policy(path: Path = DEFAULT_REDIS_TTL_POLICY_PATH) -> RedisTtlPolicyV1:
    """Load and validate redis-ttl-policy-v1."""
    return load_policy_yaml(path, RedisTtlPolicyV1)


def collect_peak_stage_output(
    *,
    rows: Sequence[EvidenceRow],
    historical_windows_by_scope: Mapping[PeakScope, Sequence[float]],
    peak_policy: PeakPolicyV1 | None = None,
    evaluation_time: datetime | None = None,
) -> PeakStageOutput:
    """Build Stage 2 peak classifications for normalized topic scopes."""
    logger = get_logger("pipeline.stages.peak")
    policy = peak_policy or load_peak_policy()
    effective_time = evaluation_time or datetime.now(tz=UTC)

    current_values_by_scope: dict[PeakScope, list[float]] = defaultdict(list)
    known_scopes: set[PeakScope] = set(historical_windows_by_scope.keys())
    for row in rows:
        topic_scope = _to_topic_scope(row.scope)
        if topic_scope is None:
            logger.warning(
                "peak_scope_normalization_failed",
                event_type="peak.scope_normalization_warning",
                scope=row.scope,
            )
            continue

        known_scopes.add(topic_scope)
        if row.metric_key != _TOPIC_MESSAGES_METRIC_KEY:
            continue
        if not math.isfinite(row.value):
            logger.warning(
                "peak_current_value_non_finite",
                event_type="peak.current_value_warning",
                scope=topic_scope,
                metric_key=row.metric_key,
            )
            continue
        current_values_by_scope[topic_scope].append(row.value)

    profiles_by_scope: dict[PeakScope, PeakProfile] = {}
    classifications_by_scope: dict[PeakScope, PeakClassification] = {}
    peak_context_by_scope: dict[PeakScope, PeakWindowContext] = {}
    for scope in sorted(known_scopes):
        history_values = historical_windows_by_scope.get(scope, ())
        profile = _build_peak_profile(
            scope=scope,
            history_values=history_values,
            policy=policy,
            evaluation_time=effective_time,
        )
        if profile is not None:
            profiles_by_scope[scope] = profile

        # Conservative aggregation: use the maximum observed value for the current interval.
        # A brief spike during the window should still trigger PEAK/NEAR_PEAK classification.
        current_value = max(current_values_by_scope.get(scope, ()), default=None)
        classification = _classify_scope(scope=scope, current_value=current_value, profile=profile)
        classifications_by_scope[scope] = classification
        peak_context_by_scope[scope] = PeakWindowContext(
            classification=classification.state,
            is_peak_window=classification.is_peak_window,
            is_near_peak_window=classification.is_near_peak_window,
            confidence=classification.confidence,
            reason_codes=classification.reason_codes,
        )

    return PeakStageOutput(
        profiles_by_scope=profiles_by_scope,
        classifications_by_scope=classifications_by_scope,
        peak_context_by_scope=peak_context_by_scope,
    )


def _to_topic_scope(scope: tuple[str, ...]) -> PeakScope | None:
    if len(scope) == 3:
        return (scope[0], scope[1], scope[2])
    if len(scope) == 4:
        return (scope[0], scope[1], scope[3])
    return None


def _build_peak_profile(
    *,
    scope: PeakScope,
    history_values: Sequence[float],
    policy: PeakPolicyV1,
    evaluation_time: datetime,
) -> PeakProfile | None:
    finite_values = sorted(value for value in history_values if math.isfinite(value))
    if not finite_values:
        return None

    # Policy naming convention: peak_percentile (default 90) is the lower bound for the
    # near-peak zone; near_peak_percentile (default 95) is the lower bound for the peak zone.
    # Result: near_peak_threshold_value < peak_threshold_value (near-peak is the softer state).
    return PeakProfile(
        scope=scope,
        source_metric=policy.metric,
        peak_threshold_value=_nearest_rank_percentile(
            finite_values, percentile=policy.defaults.near_peak_percentile
        ),
        near_peak_threshold_value=_nearest_rank_percentile(
            finite_values, percentile=policy.defaults.peak_percentile
        ),
        history_samples_count=len(finite_values),
        has_sufficient_history=len(finite_values) >= policy.defaults.min_baseline_windows,
        recompute_frequency=policy.recompute_frequency,
        computed_at=evaluation_time,
    )


def _classify_scope(
    *,
    scope: PeakScope,
    current_value: float | None,
    profile: PeakProfile | None,
) -> PeakClassification:
    if current_value is None:
        return PeakClassification(
            scope=profile.scope if profile else scope,
            state="UNKNOWN",
            current_value=None,
            confidence=0.0,
            reason_codes=("MISSING_REQUIRED_SERIES",),
            is_peak_window=False,
            is_near_peak_window=False,
            peak_threshold_value=profile.peak_threshold_value if profile else None,
            near_peak_threshold_value=profile.near_peak_threshold_value if profile else None,
        )
    if profile is None:
        return PeakClassification(
            scope=scope,
            state="UNKNOWN",
            current_value=current_value,
            confidence=0.2,
            reason_codes=("INSUFFICIENT_HISTORY",),
            is_peak_window=False,
            is_near_peak_window=False,
            peak_threshold_value=None,
            near_peak_threshold_value=None,
        )

    state = "OFF_PEAK"
    is_peak_window = False
    is_near_peak_window = False
    if current_value >= profile.peak_threshold_value:
        state = "PEAK"
        is_peak_window = True
        is_near_peak_window = True
    elif current_value >= profile.near_peak_threshold_value:
        state = "NEAR_PEAK"
        is_near_peak_window = True

    reason_codes = ["CLASSIFIED_FROM_BASELINE"]
    confidence = 1.0
    if not profile.has_sufficient_history:
        reason_codes.append("INSUFFICIENT_HISTORY")
        confidence = 0.5

    return PeakClassification(
        scope=profile.scope,
        state=state,
        current_value=current_value,
        confidence=confidence,
        reason_codes=tuple(reason_codes),
        is_peak_window=is_peak_window,
        is_near_peak_window=is_near_peak_window,
        peak_threshold_value=profile.peak_threshold_value,
        near_peak_threshold_value=profile.near_peak_threshold_value,
    )


def _nearest_rank_percentile(values: Sequence[float], *, percentile: int) -> float:
    rank = max(1, math.ceil((percentile / 100) * len(values)))
    return values[rank - 1]
