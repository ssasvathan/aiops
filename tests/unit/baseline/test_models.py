"""Unit tests for baseline/models.py — TDD RED PHASE.

Story 2.2: BASELINE_DEVIATION Finding Model
AC coverage:
  AC1 — BaselineDeviationContext: frozen Pydantic model, fields, Literal validation, tuple
  AC2 — BaselineDeviationStageOutput: frozen Pydantic model, fields, empty findings
  AC3 — AnomalyFinding extended: BASELINE_DEVIATION family + baseline_context field
  AC4 — AnomalyFinding with baseline_context populated: severity, is_primary, replay context
  AC5 — Backward compatibility: existing families construct without baseline_context (None)
  AC6 — All serialization round-trips and immutability verified

These tests FAIL until Task 1 and Task 2 are implemented:
  - src/aiops_triage_pipeline/baseline/models.py (replace placeholder stub)
  - src/aiops_triage_pipeline/models/anomaly.py (additive extension)
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.baseline.models import (
    BaselineDeviationContext,
    BaselineDeviationStageOutput,
)
from aiops_triage_pipeline.models.anomaly import AnomalyFinding

# ---------------------------------------------------------------------------
# Test fixtures / shared data helpers (module-level, no imports inside tests)
# ---------------------------------------------------------------------------

_VALID_CONTEXT_KWARGS = {
    "metric_key": "consumer_group_lag",
    "deviation_direction": "HIGH",
    "deviation_magnitude": 5.2,
    "baseline_value": 100.0,
    "current_value": 180.0,
    "time_bucket": (2, 14),
}

_VALID_ANOMALY_FINDING_KWARGS = {
    "finding_id": "f-baseline-001",
    "anomaly_family": "BASELINE_DEVIATION",
    "scope": ("prod", "kafka-prod-east", "orders.completed"),
    "severity": "LOW",
    "reason_codes": ("BASELINE_DEVIATION_HIGH",),
    "evidence_required": ("consumer_group_lag",),
    "is_primary": False,
}

_EVAL_TIME = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# AC1: BaselineDeviationContext — field correctness
# ---------------------------------------------------------------------------


def test_baseline_deviation_context_fields() -> None:
    """[P0] AC1: BaselineDeviationContext instantiates with all required fields."""
    ctx = BaselineDeviationContext(**_VALID_CONTEXT_KWARGS)

    assert ctx.metric_key == "consumer_group_lag"
    assert ctx.deviation_direction == "HIGH"
    assert ctx.deviation_magnitude == 5.2
    assert ctx.baseline_value == 100.0
    assert ctx.current_value == 180.0
    assert ctx.time_bucket == (2, 14)


def test_baseline_deviation_context_low_direction() -> None:
    """[P0] AC1: BaselineDeviationContext accepts 'LOW' as deviation_direction."""
    ctx = BaselineDeviationContext(
        metric_key="topic_messages_in_per_sec",
        deviation_direction="LOW",
        deviation_magnitude=-6.1,
        baseline_value=500.0,
        current_value=10.0,
        time_bucket=(1, 9),
    )

    assert ctx.deviation_direction == "LOW"
    assert ctx.deviation_magnitude == -6.1


# ---------------------------------------------------------------------------
# AC1: BaselineDeviationContext — frozen immutability
# ---------------------------------------------------------------------------


def test_baseline_deviation_context_is_frozen() -> None:
    """[P0] AC1: BaselineDeviationContext is immutable (frozen=True).

    Frozen Pydantic v2 models raise ValidationError on attribute assignment.
    """
    ctx = BaselineDeviationContext(**_VALID_CONTEXT_KWARGS)

    with pytest.raises(Exception):  # ValidationError (Pydantic v2 frozen model)
        ctx.metric_key = "modified"  # type: ignore[misc]


def test_baseline_deviation_context_frozen_blocks_direction_mutation() -> None:
    """[P1] AC1: Frozen model blocks mutation of any field, not just metric_key."""
    ctx = BaselineDeviationContext(**_VALID_CONTEXT_KWARGS)

    with pytest.raises(Exception):
        ctx.deviation_direction = "LOW"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC1: BaselineDeviationContext — serialization round-trip
# ---------------------------------------------------------------------------


def test_baseline_deviation_context_serialization_round_trip() -> None:
    """[P0] AC1: model_dump() → model_validate() round-trip preserves all fields."""
    ctx = BaselineDeviationContext(
        metric_key="topic_messages_in_per_sec",
        deviation_direction="LOW",
        deviation_magnitude=-6.1,
        baseline_value=500.0,
        current_value=10.0,
        time_bucket=(1, 9),
    )

    dumped = ctx.model_dump()
    restored = BaselineDeviationContext.model_validate(dumped)

    assert restored == ctx
    assert restored.metric_key == ctx.metric_key
    assert restored.deviation_direction == ctx.deviation_direction
    assert restored.deviation_magnitude == ctx.deviation_magnitude
    assert restored.baseline_value == ctx.baseline_value
    assert restored.current_value == ctx.current_value
    assert restored.time_bucket == ctx.time_bucket


# ---------------------------------------------------------------------------
# AC1: BaselineDeviationContext — field validation
# ---------------------------------------------------------------------------


def test_baseline_deviation_context_invalid_direction() -> None:
    """[P0] AC1: Non-Literal deviation_direction raises ValidationError."""
    with pytest.raises(ValidationError):
        BaselineDeviationContext(
            metric_key="consumer_group_lag",
            deviation_direction="MEDIUM",  # invalid — only "HIGH" or "LOW" accepted
            deviation_magnitude=5.0,
            baseline_value=100.0,
            current_value=200.0,
            time_bucket=(0, 10),
        )


def test_baseline_deviation_context_invalid_direction_empty_string() -> None:
    """[P1] AC1: Empty string for deviation_direction raises ValidationError."""
    with pytest.raises(ValidationError):
        BaselineDeviationContext(
            metric_key="consumer_group_lag",
            deviation_direction="",  # type: ignore[arg-type]  # invalid
            deviation_magnitude=5.0,
            baseline_value=100.0,
            current_value=200.0,
            time_bucket=(0, 10),
        )


def test_baseline_deviation_context_time_bucket_is_tuple() -> None:
    """[P0] AC1: time_bucket field is a tuple[int, int] — not a list."""
    ctx = BaselineDeviationContext(**_VALID_CONTEXT_KWARGS)

    assert isinstance(ctx.time_bucket, tuple), (
        f"time_bucket must be tuple, got {type(ctx.time_bucket)}"
    )
    assert len(ctx.time_bucket) == 2
    dow, hour = ctx.time_bucket
    assert isinstance(dow, int), f"time_bucket[0] (dow) must be int, got {type(dow)}"
    assert isinstance(hour, int), f"time_bucket[1] (hour) must be int, got {type(hour)}"


# ---------------------------------------------------------------------------
# AC2: BaselineDeviationStageOutput — field correctness
# ---------------------------------------------------------------------------


def test_baseline_deviation_stage_output_fields() -> None:
    """[P0] AC2: BaselineDeviationStageOutput instantiates with all required fields."""
    ctx = BaselineDeviationContext(**_VALID_CONTEXT_KWARGS)
    finding_with_ctx = AnomalyFinding(
        **{**_VALID_ANOMALY_FINDING_KWARGS, "baseline_context": ctx}
    )

    output = BaselineDeviationStageOutput(
        findings=(finding_with_ctx,),
        scopes_evaluated=10,
        deviations_detected=1,
        deviations_suppressed_single_metric=2,
        deviations_suppressed_dedup=0,
        evaluation_time=_EVAL_TIME,
    )

    assert len(output.findings) == 1
    assert output.scopes_evaluated == 10
    assert output.deviations_detected == 1
    assert output.deviations_suppressed_single_metric == 2
    assert output.deviations_suppressed_dedup == 0
    assert output.evaluation_time == _EVAL_TIME


def test_baseline_deviation_stage_output_empty_findings() -> None:
    """[P0] AC2: Zero findings — valid construction (empty tuple)."""
    output = BaselineDeviationStageOutput(
        findings=(),
        scopes_evaluated=5,
        deviations_detected=0,
        deviations_suppressed_single_metric=0,
        deviations_suppressed_dedup=0,
        evaluation_time=_EVAL_TIME,
    )

    assert output.findings == ()
    assert output.deviations_detected == 0
    assert output.scopes_evaluated == 5


# ---------------------------------------------------------------------------
# AC2: BaselineDeviationStageOutput — frozen immutability
# ---------------------------------------------------------------------------


def test_baseline_deviation_stage_output_is_frozen() -> None:
    """[P0] AC2: BaselineDeviationStageOutput is immutable (frozen=True)."""
    output = BaselineDeviationStageOutput(
        findings=(),
        scopes_evaluated=5,
        deviations_detected=0,
        deviations_suppressed_single_metric=0,
        deviations_suppressed_dedup=0,
        evaluation_time=_EVAL_TIME,
    )

    with pytest.raises(Exception):  # ValidationError (Pydantic v2 frozen model)
        output.scopes_evaluated = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC2: BaselineDeviationStageOutput — serialization round-trip
# ---------------------------------------------------------------------------


def test_baseline_deviation_stage_output_serialization_round_trip() -> None:
    """[P0] AC2: model_dump() → model_validate() round-trip preserves all fields."""
    output = BaselineDeviationStageOutput(
        findings=(),
        scopes_evaluated=7,
        deviations_detected=3,
        deviations_suppressed_single_metric=1,
        deviations_suppressed_dedup=0,
        evaluation_time=_EVAL_TIME,
    )

    dumped = output.model_dump()
    restored = BaselineDeviationStageOutput.model_validate(dumped)

    assert restored.scopes_evaluated == output.scopes_evaluated
    assert restored.deviations_detected == output.deviations_detected
    assert (
        restored.deviations_suppressed_single_metric
        == output.deviations_suppressed_single_metric
    )
    assert restored.deviations_suppressed_dedup == output.deviations_suppressed_dedup
    assert restored.evaluation_time == output.evaluation_time
    assert restored.findings == output.findings


def test_baseline_deviation_stage_output_serialization_round_trip_with_findings() -> None:
    """[P1] AC2, AC6: model_dump() → model_validate() round-trip with populated findings.

    Verifies the nested AnomalyFinding → BaselineDeviationContext serialization path,
    which requires AnomalyFinding.model_rebuild() (called on baseline.models import).
    """
    ctx = BaselineDeviationContext(**_VALID_CONTEXT_KWARGS)
    finding = AnomalyFinding(**{**_VALID_ANOMALY_FINDING_KWARGS, "baseline_context": ctx})
    output = BaselineDeviationStageOutput(
        findings=(finding,),
        scopes_evaluated=5,
        deviations_detected=1,
        deviations_suppressed_single_metric=0,
        deviations_suppressed_dedup=0,
        evaluation_time=_EVAL_TIME,
    )

    dumped = output.model_dump()
    restored = BaselineDeviationStageOutput.model_validate(dumped)

    assert len(restored.findings) == 1
    restored_finding = restored.findings[0]
    assert restored_finding.anomaly_family == "BASELINE_DEVIATION"
    assert restored_finding.baseline_context is not None
    assert restored_finding.baseline_context.metric_key == ctx.metric_key
    assert restored_finding.baseline_context.deviation_direction == ctx.deviation_direction
    assert restored_finding.baseline_context.time_bucket == ctx.time_bucket
    assert isinstance(restored_finding.baseline_context, BaselineDeviationContext)


# ---------------------------------------------------------------------------
# AC3: AnomalyFinding — BASELINE_DEVIATION family accepted
# ---------------------------------------------------------------------------


def test_anomaly_finding_baseline_deviation_family_accepted() -> None:
    """[P0] AC3: 'BASELINE_DEVIATION' is a valid anomaly_family Literal."""
    finding = AnomalyFinding(**_VALID_ANOMALY_FINDING_KWARGS)

    assert finding.anomaly_family == "BASELINE_DEVIATION"


def test_anomaly_finding_baseline_deviation_family_invalid_raises() -> None:
    """[P1] AC3: Invalid anomaly_family still raises ValidationError (regression guard)."""
    with pytest.raises(ValidationError):
        AnomalyFinding(
            finding_id="f-bad",
            anomaly_family="NONEXISTENT_FAMILY",  # type: ignore[arg-type]
            scope=("prod", "cluster-1"),
            severity="LOW",
            reason_codes=("SOME_CODE",),
            evidence_required=("some_evidence",),
        )


# ---------------------------------------------------------------------------
# AC3 + AC4: AnomalyFinding — baseline_context field populated
# ---------------------------------------------------------------------------


def test_anomaly_finding_with_baseline_context() -> None:
    """[P0] AC3, AC4: AnomalyFinding with anomaly_family='BASELINE_DEVIATION'
    and baseline_context populated carries all replay context (NFR-A2).
    """
    ctx = BaselineDeviationContext(
        metric_key="consumer_group_lag",
        deviation_direction="HIGH",
        deviation_magnitude=5.2,
        baseline_value=100.0,
        current_value=180.0,
        time_bucket=(2, 14),
    )

    finding = AnomalyFinding(
        finding_id="f-baseline-replay-001",
        anomaly_family="BASELINE_DEVIATION",
        scope=("prod", "kafka-prod-east", "orders.completed"),
        severity="LOW",       # FR16: severity=LOW for BASELINE_DEVIATION
        reason_codes=("BASELINE_DEVIATION_HIGH",),
        evidence_required=("consumer_group_lag",),
        is_primary=False,     # FR16: is_primary=False for BASELINE_DEVIATION
        baseline_context=ctx,
    )

    assert finding.baseline_context is not None
    assert finding.baseline_context.metric_key == "consumer_group_lag"
    assert finding.baseline_context.deviation_direction == "HIGH"
    assert finding.baseline_context.deviation_magnitude == 5.2
    assert finding.baseline_context.baseline_value == 100.0
    assert finding.baseline_context.current_value == 180.0
    assert finding.baseline_context.time_bucket == (2, 14)
    assert finding.severity == "LOW"
    assert finding.is_primary is False


def test_anomaly_finding_baseline_context_provides_full_replay_context() -> None:
    """[P1] AC4: NFR-A2 — all replay context fields present on the finding."""
    ctx = BaselineDeviationContext(
        metric_key="topic_messages_in_per_sec",
        deviation_direction="LOW",
        deviation_magnitude=-7.3,
        baseline_value=800.0,
        current_value=50.0,
        time_bucket=(0, 8),
    )

    finding = AnomalyFinding(
        finding_id="f-replay-002",
        anomaly_family="BASELINE_DEVIATION",
        scope=("prod", "kafka-prod-east", "checkout.events"),
        severity="LOW",
        reason_codes=("BASELINE_DEVIATION_LOW",),
        evidence_required=("topic_messages_in_per_sec",),
        is_primary=False,
        baseline_context=ctx,
    )

    # NFR-A2: verify every replay field is accessible via baseline_context
    bc = finding.baseline_context
    assert bc is not None
    assert bc.metric_key == "topic_messages_in_per_sec"
    assert bc.deviation_direction == "LOW"
    assert bc.deviation_magnitude == -7.3
    assert bc.baseline_value == 800.0
    assert bc.current_value == 50.0
    assert bc.time_bucket == (0, 8)


# ---------------------------------------------------------------------------
# AC5: Backward compatibility — existing families unaffected
# ---------------------------------------------------------------------------


def test_anomaly_finding_baseline_context_defaults_none() -> None:
    """[P0] AC5: Existing families construct without baseline_context; field defaults to None."""
    finding = AnomalyFinding(
        finding_id="f-existing-001",
        anomaly_family="CONSUMER_LAG",
        scope=("prod", "cluster-1", "group-a", "topic-a"),
        severity="HIGH",
        reason_codes=("LAG_BUILDUP_DETECTED",),
        evidence_required=("consumer_group_lag",),
        is_primary=True,
    )

    assert finding.baseline_context is None


def test_anomaly_finding_existing_families_unchanged() -> None:
    """[P0] AC5: All three pre-existing anomaly families construct normally (no regressions)."""
    families_kwargs = [
        {
            "finding_id": "f-consumer-lag",
            "anomaly_family": "CONSUMER_LAG",
            "scope": ("prod", "cluster-1", "group-a", "topic-a"),
            "severity": "HIGH",
            "reason_codes": ("LAG_BUILDUP_DETECTED",),
            "evidence_required": ("consumer_group_lag",),
        },
        {
            "finding_id": "f-volume-drop",
            "anomaly_family": "VOLUME_DROP",
            "scope": ("prod", "cluster-1", "topic-a"),
            "severity": "MEDIUM",
            "reason_codes": ("VOLUME_DROP_DETECTED",),
            "evidence_required": ("topic_messages_in_per_sec",),
        },
        {
            "finding_id": "f-throughput-proxy",
            "anomaly_family": "THROUGHPUT_CONSTRAINED_PROXY",
            "scope": ("prod", "cluster-1", "group-a"),
            "severity": "LOW",
            "reason_codes": ("THROUGHPUT_CONSTRAINED",),
            "evidence_required": ("consumer_group_lag",),
        },
    ]

    for kwargs in families_kwargs:
        finding = AnomalyFinding(**kwargs)  # type: ignore[arg-type]
        assert finding.anomaly_family == kwargs["anomaly_family"]
        assert finding.baseline_context is None, (
            f"baseline_context must default to None for {kwargs['anomaly_family']}"
        )


def test_anomaly_finding_explicit_none_baseline_context() -> None:
    """[P1] AC5: Explicitly setting baseline_context=None works for existing families."""
    finding = AnomalyFinding(
        finding_id="f-volume-none",
        anomaly_family="VOLUME_DROP",
        scope=("prod", "cluster-1", "topic-a"),
        severity="MEDIUM",
        reason_codes=("VOLUME_DROP_DETECTED",),
        evidence_required=("topic_messages_in_per_sec",),
        baseline_context=None,
    )

    assert finding.baseline_context is None


# ---------------------------------------------------------------------------
# AC6: AnomalyFinding round-trip serialization with baseline_context
# ---------------------------------------------------------------------------


def test_anomaly_finding_with_baseline_context_serialization_round_trip() -> None:
    """[P0] AC6: AnomalyFinding model_dump() → model_validate() round-trip with
    baseline_context populated preserves all nested fields.

    This validates the AnomalyFinding.model_rebuild() pattern in baseline/models.py:
    model_validate() from a dict (e.g. deserialized from Redis/JSON) must correctly
    reconstruct the nested BaselineDeviationContext instance.
    """
    ctx = BaselineDeviationContext(**_VALID_CONTEXT_KWARGS)
    finding = AnomalyFinding(**{**_VALID_ANOMALY_FINDING_KWARGS, "baseline_context": ctx})

    dumped = finding.model_dump()
    restored = AnomalyFinding.model_validate(dumped)

    assert restored == finding
    assert restored.anomaly_family == "BASELINE_DEVIATION"
    assert restored.baseline_context is not None
    assert isinstance(restored.baseline_context, BaselineDeviationContext)
    assert restored.baseline_context.metric_key == ctx.metric_key
    assert restored.baseline_context.deviation_direction == ctx.deviation_direction
    assert restored.baseline_context.deviation_magnitude == ctx.deviation_magnitude
    assert restored.baseline_context.baseline_value == ctx.baseline_value
    assert restored.baseline_context.current_value == ctx.current_value
    assert restored.baseline_context.time_bucket == ctx.time_bucket
    assert isinstance(restored.baseline_context.time_bucket, tuple)
