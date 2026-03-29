"""ATDD support data for Story 1.1 deterministic confidence scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.models.peak import PeakStageOutput, SustainedStatus
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.gating import GateInputContext
from aiops_triage_pipeline.pipeline.stages.peak import collect_peak_stage_output, load_rulebook_policy

GateScope = tuple[str, ...]
_TOPIC_SCOPE: tuple[str, str, str] = ("prod", "cluster-a", "orders")
_SUSTAINED_KEY: tuple[str, str, str, str] = ("prod", "cluster-a", "topic:orders", "VOLUME_DROP")
_EVALUATION_TIME = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)


def _peak_policy_for_story_1_1() -> PeakPolicyV1:
    return PeakPolicyV1(
        metric="kafka_server_brokertopicmetrics_messagesinpersec",
        timezone="America/Toronto",
        recompute_frequency="weekly",
        defaults=PeakThresholdPolicy(
            peak_percentile=90,
            near_peak_percentile=95,
            bucket_minutes=15,
            min_baseline_windows=4,
        ),
    )


def _default_volume_drop_samples() -> dict[str, list[dict[str, object]]]:
    return {
        "topic_messages_in_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 180.0,
            },
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 0.4,
            },
        ],
        "total_produce_requests_per_sec": [
            {
                "labels": {"env": "prod", "cluster_name": "cluster-a", "topic": "orders"},
                "value": 220.0,
            }
        ],
        "failed_produce_requests_per_sec": [],
    }


def build_story_1_1_context(
    *,
    proposed_action: Action = Action.OBSERVE,
    diagnosis_confidence: float = 0.0,
) -> GateInputContext:
    """Build default gate-input context used by Story 1.1 acceptance tests."""
    return GateInputContext(
        stream_id="stream-orders",
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=proposed_action,
        diagnosis_confidence=diagnosis_confidence,
    )


def build_story_1_1_stage_inputs(
    *,
    sustained_value: bool | None,
    is_peak_window: bool,
    evidence_samples: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> tuple[EvidenceStageOutput, PeakStageOutput, GateScope]:
    """Construct evidence + peak outputs for Story 1.1 red-phase scenarios."""
    samples = evidence_samples or _default_volume_drop_samples()
    evidence_output = collect_evidence_stage_output(samples)

    rulebook = load_rulebook_policy()
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={_TOPIC_SCOPE: [float(x) for x in range(1, 21)]},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evaluation_time=_EVALUATION_TIME,
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        peak_policy=_peak_policy_for_story_1_1(),
        rulebook_policy=rulebook,
    )

    peak_context = peak_output.peak_context_by_scope.get(_TOPIC_SCOPE)
    if peak_context is not None and peak_context.is_peak_window != is_peak_window:
        updated_peak_context_by_scope = dict(peak_output.peak_context_by_scope)
        updated_peak_context_by_scope[_TOPIC_SCOPE] = peak_context.model_copy(
            update={"is_peak_window": is_peak_window}
        )
        peak_output = peak_output.model_copy(
            update={"peak_context_by_scope": updated_peak_context_by_scope}
        )

    sustained_by_key = dict(peak_output.sustained_by_key)
    if sustained_value is None:
        sustained_by_key.pop(_SUSTAINED_KEY, None)
    else:
        sustained_by_key[_SUSTAINED_KEY] = SustainedStatus(
            identity_key=_SUSTAINED_KEY,
            is_sustained=sustained_value,
            consecutive_anomalous_buckets=(
                rulebook.sustained_intervals_required
                if sustained_value
                else max(rulebook.sustained_intervals_required - 1, 0)
            ),
            required_buckets=rulebook.sustained_intervals_required,
            last_evaluated_at=_EVALUATION_TIME,
            reason_codes=("STORY_1_1_TEST_STATUS",),
        )
    peak_output = peak_output.model_copy(update={"sustained_by_key": sustained_by_key})

    return evidence_output, peak_output, _TOPIC_SCOPE
