"""Stage 2 peak-classification helpers."""

import math
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence

from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts.enums import EvidenceStatus
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.health.metrics import record_pipeline_sustained_compute
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.anomaly import AnomalyFinding
from aiops_triage_pipeline.models.evidence import EvidenceRow
from aiops_triage_pipeline.models.peak import (
    PeakClassification,
    PeakProfile,
    PeakScope,
    PeakStageOutput,
    PeakWindowContext,
    SustainedIdentityKey,
    SustainedStatus,
    SustainedWindowState,
)

DEFAULT_PEAK_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "config/policies/peak-policy-v1.yaml"
)
DEFAULT_REDIS_TTL_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "config/policies/redis-ttl-policy-v1.yaml"
)
DEFAULT_RULEBOOK_POLICY_PATH = (
    Path(__file__).resolve().parents[4] / "config/policies/rulebook-v1.yaml"
)
_TOPIC_MESSAGES_METRIC_KEY = "topic_messages_in_per_sec"
_REQUIRED_METRICS_BY_ANOMALY_FAMILY: dict[str, tuple[str, ...]] = {
    "CONSUMER_LAG": ("consumer_group_lag", "consumer_group_offset"),
    "VOLUME_DROP": ("topic_messages_in_per_sec", "total_produce_requests_per_sec"),
    "THROUGHPUT_CONSTRAINED_PROXY": (
        "topic_messages_in_per_sec",
        "total_produce_requests_per_sec",
        "failed_produce_requests_per_sec",
    ),
}


def load_peak_policy(path: Path = DEFAULT_PEAK_POLICY_PATH) -> PeakPolicyV1:
    """Load and validate peak-policy-v1."""
    return load_policy_yaml(path, PeakPolicyV1)


def load_redis_ttl_policy(path: Path = DEFAULT_REDIS_TTL_POLICY_PATH) -> RedisTtlPolicyV1:
    """Load and validate redis-ttl-policy-v1."""
    return load_policy_yaml(path, RedisTtlPolicyV1)


def load_rulebook_policy(path: Path = DEFAULT_RULEBOOK_POLICY_PATH) -> RulebookV1:
    """Load and validate rulebook-v1 policy."""
    return load_policy_yaml(path, RulebookV1)


def collect_peak_stage_output(
    *,
    rows: Sequence[EvidenceRow],
    historical_windows_by_scope: Mapping[PeakScope, Sequence[float]],
    cached_profiles_by_scope: Mapping[PeakScope, PeakProfile] | None = None,
    evidence_status_map_by_scope: (
        Mapping[tuple[str, ...], Mapping[str, EvidenceStatus]] | None
    ) = None,
    anomaly_findings: Sequence[AnomalyFinding] = (),
    prior_sustained_window_state_by_key: (
        Mapping[SustainedIdentityKey, SustainedWindowState] | None
    ) = None,
    peak_policy: PeakPolicyV1 | None = None,
    rulebook_policy: RulebookV1 | None = None,
    evaluation_time: datetime | None = None,
    sustained_parallel_min_keys: int = 64,
    sustained_parallel_workers: int = 4,
    sustained_parallel_chunk_size: int = 32,
) -> PeakStageOutput:
    """Build Stage 2 peak classifications for normalized topic scopes."""
    logger = get_logger("pipeline.stages.peak")
    policy = peak_policy or load_peak_policy()
    rulebook = rulebook_policy or load_rulebook_policy()
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
        profile = cached_profiles_by_scope.get(scope) if cached_profiles_by_scope else None
        if profile is not None:
            rejection_reason = _cached_profile_rejection_reason(
                profile=profile,
                policy=policy,
                evaluation_time=effective_time,
            )
            if rejection_reason is not None:
                logger.warning(
                    "peak_cached_profile_rejected",
                    event_type="peak.cached_profile_warning",
                    scope=scope,
                    reason=rejection_reason,
                    computed_at=profile.computed_at.isoformat(),
                    evaluation_time=effective_time.isoformat(),
                    recompute_frequency=profile.recompute_frequency,
                )
                profile = None
        if profile is None:
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
        required_series_status = _required_metric_status_for_peak_scope(
            scope=scope,
            evidence_status_map_by_scope=evidence_status_map_by_scope,
        )
        classification = _classify_scope(
            scope=scope,
            current_value=current_value,
            profile=profile,
            required_series_status=required_series_status,
        )
        classifications_by_scope[scope] = classification
        peak_context_by_scope[scope] = PeakWindowContext(
            classification=classification.state,
            is_peak_window=classification.is_peak_window,
            is_near_peak_window=classification.is_near_peak_window,
            confidence=classification.confidence,
            reason_codes=classification.reason_codes,
        )

    sustained_by_key = compute_sustained_status_by_key(
        anomaly_findings=anomaly_findings,
        prior_window_state_by_key=prior_sustained_window_state_by_key or {},
        required_buckets=rulebook.sustained_intervals_required,
        evaluation_interval_minutes=rulebook.evaluation_interval_minutes,
        evaluation_time=effective_time,
        evidence_status_map_by_scope=evidence_status_map_by_scope,
        logger=logger,
        sustained_parallel_min_keys=sustained_parallel_min_keys,
        sustained_parallel_workers=sustained_parallel_workers,
        sustained_parallel_chunk_size=sustained_parallel_chunk_size,
    )

    return PeakStageOutput(
        profiles_by_scope=profiles_by_scope,
        classifications_by_scope=classifications_by_scope,
        peak_context_by_scope=peak_context_by_scope,
        evidence_status_map_by_scope=evidence_status_map_by_scope or {},
        sustained_by_key=sustained_by_key,
    )


def build_sustained_window_state_by_key(
    sustained_by_key: Mapping[SustainedIdentityKey, SustainedStatus],
) -> dict[SustainedIdentityKey, SustainedWindowState]:
    """Convert sustained status output into persistable streak state."""
    return {
        key: SustainedWindowState(
            identity_key=status.identity_key,
            consecutive_anomalous_buckets=status.consecutive_anomalous_buckets,
            last_evaluated_at=status.last_evaluated_at,
        )
        for key, status in sorted(sustained_by_key.items())
    }


def build_sustained_identity_keys(
    anomaly_findings: Sequence[AnomalyFinding],
) -> list[SustainedIdentityKey]:
    """Derive deterministic sustained identity keys from anomaly findings."""
    logger = get_logger("pipeline.stages.peak")
    keys: set[SustainedIdentityKey] = set()
    for finding in anomaly_findings:
        key = _to_sustained_identity_key(finding=finding, logger=logger)
        if key is not None:
            keys.add(key)
    return sorted(keys)


def compute_sustained_status_by_key(
    *,
    anomaly_findings: Sequence[AnomalyFinding],
    prior_window_state_by_key: Mapping[SustainedIdentityKey, SustainedWindowState],
    required_buckets: int,
    evaluation_interval_minutes: int,
    evaluation_time: datetime,
    evidence_status_map_by_scope: Mapping[tuple[str, ...], Mapping[str, EvidenceStatus]] | None,
    logger,
    sustained_parallel_min_keys: int = 64,
    sustained_parallel_workers: int = 4,
    sustained_parallel_chunk_size: int = 32,
) -> dict[SustainedIdentityKey, SustainedStatus]:
    """Compute sustained streak state per (env, cluster, topic/group, anomaly_family)."""
    started_at = time.perf_counter()
    current_anomalous_keys: set[SustainedIdentityKey] = set()
    for finding in anomaly_findings:
        key = _to_sustained_identity_key(finding=finding, logger=logger)
        if key is not None:
            current_anomalous_keys.add(key)

    keys_to_evaluate = sorted(set(prior_window_state_by_key.keys()) | current_anomalous_keys)
    insufficient_evidence_by_key: set[SustainedIdentityKey] = set()
    for key in keys_to_evaluate:
        if _has_insufficient_evidence_for_sustained_key(
            key=key,
            evidence_status_map_by_scope=evidence_status_map_by_scope,
        ):
            insufficient_evidence_by_key.add(key)

    sustained_by_key: dict[SustainedIdentityKey, SustainedStatus] = {}
    execution_mode = "serial"
    should_parallelize = (
        len(keys_to_evaluate) >= sustained_parallel_min_keys
        and sustained_parallel_workers > 1
        and sustained_parallel_chunk_size > 0
    )
    if should_parallelize:
        execution_mode = "parallel"
        chunks = [
            keys_to_evaluate[idx : idx + sustained_parallel_chunk_size]
            for idx in range(0, len(keys_to_evaluate), sustained_parallel_chunk_size)
        ]
        try:
            with ThreadPoolExecutor(max_workers=sustained_parallel_workers) as executor:
                futures = [
                    executor.submit(
                        _compute_sustained_status_chunk,
                        chunk,
                        prior_window_state_by_key,
                        insufficient_evidence_by_key,
                        current_anomalous_keys,
                        required_buckets,
                        evaluation_interval_minutes,
                        evaluation_time,
                    )
                    for chunk in chunks
                ]
                # Preserve deterministic insertion ordering by consuming futures in chunk order.
                for future in futures:
                    for key, status in future.result():
                        sustained_by_key[key] = status
        except Exception:
            execution_mode = "parallel_fallback"
            logger.warning(
                "sustained_parallel_fallback_to_serial",
                event_type="peak.sustained_parallel_warning",
                key_count=len(keys_to_evaluate),
                workers=sustained_parallel_workers,
                chunk_size=sustained_parallel_chunk_size,
                exc_info=True,
            )
            sustained_by_key = _compute_sustained_status_serial(
                keys_to_evaluate=keys_to_evaluate,
                prior_window_state_by_key=prior_window_state_by_key,
                insufficient_evidence_by_key=insufficient_evidence_by_key,
                current_anomalous_keys=current_anomalous_keys,
                required_buckets=required_buckets,
                evaluation_interval_minutes=evaluation_interval_minutes,
                evaluation_time=evaluation_time,
            )
    else:
        if len(keys_to_evaluate) >= sustained_parallel_min_keys and sustained_parallel_workers <= 1:
            logger.warning(
                "sustained_parallel_disabled_by_config",
                event_type="peak.sustained_parallel_warning",
                key_count=len(keys_to_evaluate),
                workers=sustained_parallel_workers,
            )
        sustained_by_key = _compute_sustained_status_serial(
            keys_to_evaluate=keys_to_evaluate,
            prior_window_state_by_key=prior_window_state_by_key,
            insufficient_evidence_by_key=insufficient_evidence_by_key,
            current_anomalous_keys=current_anomalous_keys,
            required_buckets=required_buckets,
            evaluation_interval_minutes=evaluation_interval_minutes,
            evaluation_time=evaluation_time,
        )
    elapsed_seconds = time.perf_counter() - started_at
    record_pipeline_sustained_compute(
        seconds=elapsed_seconds,
        key_count=len(keys_to_evaluate),
        mode=execution_mode,
    )
    return sustained_by_key


def _compute_sustained_status_serial(
    *,
    keys_to_evaluate: Sequence[SustainedIdentityKey],
    prior_window_state_by_key: Mapping[SustainedIdentityKey, SustainedWindowState],
    insufficient_evidence_by_key: set[SustainedIdentityKey],
    current_anomalous_keys: set[SustainedIdentityKey],
    required_buckets: int,
    evaluation_interval_minutes: int,
    evaluation_time: datetime,
) -> dict[SustainedIdentityKey, SustainedStatus]:
    sustained_by_key: dict[SustainedIdentityKey, SustainedStatus] = {}
    for key in keys_to_evaluate:
        sustained_by_key[key] = _compute_sustained_status_for_key(
            key=key,
            prior_window_state_by_key=prior_window_state_by_key,
            insufficient_evidence_by_key=insufficient_evidence_by_key,
            current_anomalous_keys=current_anomalous_keys,
            required_buckets=required_buckets,
            evaluation_interval_minutes=evaluation_interval_minutes,
            evaluation_time=evaluation_time,
        )
    return sustained_by_key


def _compute_sustained_status_chunk(
    keys: Sequence[SustainedIdentityKey],
    prior_window_state_by_key: Mapping[SustainedIdentityKey, SustainedWindowState],
    insufficient_evidence_by_key: set[SustainedIdentityKey],
    current_anomalous_keys: set[SustainedIdentityKey],
    required_buckets: int,
    evaluation_interval_minutes: int,
    evaluation_time: datetime,
) -> list[tuple[SustainedIdentityKey, SustainedStatus]]:
    return [
        (
            key,
            _compute_sustained_status_for_key(
                key=key,
                prior_window_state_by_key=prior_window_state_by_key,
                insufficient_evidence_by_key=insufficient_evidence_by_key,
                current_anomalous_keys=current_anomalous_keys,
                required_buckets=required_buckets,
                evaluation_interval_minutes=evaluation_interval_minutes,
                evaluation_time=evaluation_time,
            ),
        )
        for key in keys
    ]


def _compute_sustained_status_for_key(
    *,
    key: SustainedIdentityKey,
    prior_window_state_by_key: Mapping[SustainedIdentityKey, SustainedWindowState],
    insufficient_evidence_by_key: set[SustainedIdentityKey],
    current_anomalous_keys: set[SustainedIdentityKey],
    required_buckets: int,
    evaluation_interval_minutes: int,
    evaluation_time: datetime,
) -> SustainedStatus:
    prior_state = prior_window_state_by_key.get(key)
    evidence_insufficient = key in insufficient_evidence_by_key
    streak = _next_streak_count(
        prior_state=prior_state,
        current_key_is_anomalous=key in current_anomalous_keys,
        evidence_insufficient=evidence_insufficient,
        evaluation_time=evaluation_time,
        evaluation_interval_minutes=evaluation_interval_minutes,
    )
    is_sustained = streak >= required_buckets and not evidence_insufficient
    return SustainedStatus(
        identity_key=key,
        is_sustained=is_sustained,
        consecutive_anomalous_buckets=streak,
        required_buckets=required_buckets,
        last_evaluated_at=evaluation_time,
        reason_codes=_reason_codes(
            prior_state=prior_state,
            streak=streak,
            is_sustained=is_sustained,
            is_anomalous=key in current_anomalous_keys,
            evidence_insufficient=evidence_insufficient,
            evaluation_time=evaluation_time,
            evaluation_interval_minutes=evaluation_interval_minutes,
        ),
    )


def _required_metric_status_for_peak_scope(
    *,
    scope: PeakScope,
    evidence_status_map_by_scope: Mapping[tuple[str, ...], Mapping[str, EvidenceStatus]] | None,
) -> EvidenceStatus | None:
    if evidence_status_map_by_scope is None:
        return None
    scope_status_map = evidence_status_map_by_scope.get(scope)
    if scope_status_map is None:
        return EvidenceStatus.UNKNOWN
    return scope_status_map.get(_TOPIC_MESSAGES_METRIC_KEY, EvidenceStatus.UNKNOWN)


def _has_insufficient_evidence_for_sustained_key(
    *,
    key: SustainedIdentityKey,
    evidence_status_map_by_scope: Mapping[tuple[str, ...], Mapping[str, EvidenceStatus]] | None,
) -> bool:
    if evidence_status_map_by_scope is None:
        return False

    required_metrics = _REQUIRED_METRICS_BY_ANOMALY_FAMILY.get(key[3])
    if required_metrics is None:
        return False

    candidate_scope_status_maps = _candidate_scope_status_maps_for_sustained_key(
        key=key,
        evidence_status_map_by_scope=evidence_status_map_by_scope,
    )
    if not candidate_scope_status_maps:
        return True

    for scope_status_map in candidate_scope_status_maps:
        if all(
            scope_status_map.get(required_metric, EvidenceStatus.UNKNOWN)
            == EvidenceStatus.PRESENT
            for required_metric in required_metrics
        ):
            return False

    return True


def _candidate_scope_status_maps_for_sustained_key(
    *,
    key: SustainedIdentityKey,
    evidence_status_map_by_scope: Mapping[tuple[str, ...], Mapping[str, EvidenceStatus]],
) -> list[Mapping[str, EvidenceStatus]]:
    env, cluster_id, topic_or_group, _ = key
    if topic_or_group.startswith("topic:"):
        topic = topic_or_group.split("topic:", maxsplit=1)[1]
        status_map = evidence_status_map_by_scope.get((env, cluster_id, topic))
        return [status_map] if status_map is not None else []

    if topic_or_group.startswith("group:"):
        group = topic_or_group.split("group:", maxsplit=1)[1]
        return [
            status_map
            for scope, status_map in evidence_status_map_by_scope.items()
            if len(scope) == 4 and scope[0] == env and scope[1] == cluster_id and scope[2] == group
        ]

    return []


def _to_sustained_identity_key(
    *,
    finding: AnomalyFinding,
    logger,
) -> SustainedIdentityKey | None:
    scope = finding.scope
    if len(scope) == 3:
        topic_or_group = f"topic:{scope[2]}"
        return (scope[0], scope[1], topic_or_group, finding.anomaly_family)
    if len(scope) == 4:
        topic_or_group = f"group:{scope[2]}"
        return (scope[0], scope[1], topic_or_group, finding.anomaly_family)
    logger.warning(
        "sustained_scope_normalization_failed",
        event_type="peak.sustained_scope_normalization_warning",
        scope=scope,
        anomaly_family=finding.anomaly_family,
    )
    return None


def _next_streak_count(
    *,
    prior_state: SustainedWindowState | None,
    current_key_is_anomalous: bool,
    evidence_insufficient: bool,
    evaluation_time: datetime,
    evaluation_interval_minutes: int,
) -> int:
    if evidence_insufficient:
        if prior_state is None:
            return 0
        if not _is_consecutive_interval(
            previous_evaluation=prior_state.last_evaluated_at,
            current_evaluation=evaluation_time,
            evaluation_interval_minutes=evaluation_interval_minutes,
        ):
            return 0
        return prior_state.consecutive_anomalous_buckets
    if not current_key_is_anomalous:
        return 0
    if prior_state is None:
        return 1
    if _is_consecutive_interval(
        previous_evaluation=prior_state.last_evaluated_at,
        current_evaluation=evaluation_time,
        evaluation_interval_minutes=evaluation_interval_minutes,
    ):
        return prior_state.consecutive_anomalous_buckets + 1
    return 1


def _reason_codes(
    *,
    prior_state: SustainedWindowState | None,
    streak: int,
    is_sustained: bool,
    is_anomalous: bool,
    evidence_insufficient: bool,
    evaluation_time: datetime,
    evaluation_interval_minutes: int,
) -> tuple[str, ...]:
    if evidence_insufficient:
        if prior_state is None:
            base = ("INSUFFICIENT_EVIDENCE",)
        elif _is_consecutive_interval(
            previous_evaluation=prior_state.last_evaluated_at,
            current_evaluation=evaluation_time,
            evaluation_interval_minutes=evaluation_interval_minutes,
        ):
            if prior_state.consecutive_anomalous_buckets > 0:
                base = ("INSUFFICIENT_EVIDENCE", "STREAK_HELD")
            else:
                base = ("INSUFFICIENT_EVIDENCE", "STREAK_INACTIVE")
        else:
            base = ("INSUFFICIENT_EVIDENCE", "STREAK_RESET_GAP")
    elif not is_anomalous:
        if prior_state is not None and prior_state.consecutive_anomalous_buckets > 0:
            base = ("NON_ANOMALOUS_INTERVAL", "STREAK_RESET")
        else:
            base = ("NON_ANOMALOUS_INTERVAL",)
    elif prior_state is None:
        base = ("ANOMALOUS_INTERVAL", "STREAK_STARTED")
    elif _is_consecutive_interval(
        previous_evaluation=prior_state.last_evaluated_at,
        current_evaluation=evaluation_time,
        evaluation_interval_minutes=evaluation_interval_minutes,
    ):
        # Consecutive interval: continue streak, or re-start if prior streak was at zero.
        if prior_state.consecutive_anomalous_buckets == 0:
            base = ("ANOMALOUS_INTERVAL", "STREAK_STARTED")
        else:
            base = ("ANOMALOUS_INTERVAL", "STREAK_CONTINUES")
    else:
        base = ("ANOMALOUS_INTERVAL", "STREAK_RESET_GAP")

    if evidence_insufficient:
        return (*base, "SUSTAINED_UNCERTAIN")
    if is_sustained:
        return (*base, "SUSTAINED_THRESHOLD_MET")
    if streak == 0:
        return (*base, "SUSTAINED_INACTIVE")
    return (*base, "SUSTAINED_THRESHOLD_NOT_MET")


def _is_consecutive_interval(
    *,
    previous_evaluation: datetime,
    current_evaluation: datetime,
    evaluation_interval_minutes: int,
) -> bool:
    if evaluation_interval_minutes <= 0:
        raise ValueError(
            f"evaluation_interval_minutes must be a positive integer, "
            f"got {evaluation_interval_minutes}"
        )
    interval_seconds = evaluation_interval_minutes * 60
    previous_bucket = int(previous_evaluation.astimezone(UTC).timestamp()) // interval_seconds
    current_bucket = int(current_evaluation.astimezone(UTC).timestamp()) // interval_seconds
    return current_bucket - previous_bucket == 1


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


def _cached_profile_rejection_reason(
    *,
    profile: PeakProfile,
    policy: PeakPolicyV1,
    evaluation_time: datetime,
) -> str | None:
    if profile.source_metric != policy.metric:
        return "source_metric_mismatch"
    if profile.recompute_frequency != policy.recompute_frequency:
        return "recompute_frequency_mismatch"
    if not math.isfinite(profile.peak_threshold_value) or not math.isfinite(
        profile.near_peak_threshold_value
    ):
        return "non_finite_threshold"
    if profile.near_peak_threshold_value > profile.peak_threshold_value:
        return "threshold_order_invalid"
    if profile.computed_at.tzinfo is None:
        return "computed_at_missing_timezone"

    age = evaluation_time.astimezone(UTC) - profile.computed_at.astimezone(UTC)
    if age > _recompute_interval(profile.recompute_frequency):
        return "stale_profile"
    return None


def _recompute_interval(recompute_frequency: str) -> timedelta:
    if recompute_frequency == "daily":
        return timedelta(days=1)
    if recompute_frequency == "weekly":
        return timedelta(days=7)
    return timedelta(days=30)


def _classify_scope(
    *,
    scope: PeakScope,
    current_value: float | None,
    profile: PeakProfile | None,
    required_series_status: EvidenceStatus | None = None,
) -> PeakClassification:
    if current_value is None:
        if required_series_status == EvidenceStatus.UNKNOWN:
            reason_codes = ("REQUIRED_EVIDENCE_UNKNOWN",)
        elif required_series_status == EvidenceStatus.ABSENT:
            reason_codes = ("REQUIRED_EVIDENCE_ABSENT",)
        elif required_series_status == EvidenceStatus.STALE:
            reason_codes = ("REQUIRED_EVIDENCE_STALE",)
        else:
            reason_codes = ("MISSING_REQUIRED_SERIES",)
        return PeakClassification(
            scope=profile.scope if profile else scope,
            state="UNKNOWN",
            current_value=None,
            confidence=0.0,
            reason_codes=reason_codes,
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
