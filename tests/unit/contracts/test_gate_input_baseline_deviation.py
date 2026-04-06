"""Unit tests for Story 2.4 AC 3: GateInputV1.anomaly_family extension and gating helpers.

Tests are written against EXPECTED behaviour (TDD RED PHASE).
They will fail with ValidationError or ValueError until the implementation exists.

Coverage:
  - GateInputV1 accepts anomaly_family="BASELINE_DEVIATION" (AC 3)
  - _anomaly_family_from_gate_finding_name handles "baseline_deviation" (AC 3)
  - _anomaly_family_from_gate_finding_name is case-insensitive for "BASELINE_DEVIATION" (AC 3)
  - _sustained_identity_key handles "BASELINE_DEVIATION" anomaly family (AC 3)
"""

import pytest

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.pipeline.stages.gating import (
    _anomaly_family_from_gate_finding_name,
    _sustained_identity_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_baseline_deviation_gate_input(**overrides) -> GateInputV1:
    """Build a minimal GateInputV1 with anomaly_family='BASELINE_DEVIATION'."""
    defaults = dict(
        env=Environment.PROD,
        cluster_id="kafka-prod",
        stream_id="stream-orders",
        topic="orders.completed",
        topic_role="SHARED_TOPIC",
        anomaly_family="BASELINE_DEVIATION",
        criticality_tier=CriticalityTier.TIER_1,
        proposed_action=Action.NOTIFY,
        diagnosis_confidence=0.75,
        sustained=False,
        findings=(
            Finding(
                finding_id="bd-001",
                name="baseline_deviation",
                is_anomalous=True,
                evidence_required=("consumer_group_lag", "topic_messages_in_per_sec"),
                is_primary=True,
                severity="MEDIUM",
                reason_codes=("consumer_group_lag", "topic_messages_in_per_sec"),
            ),
        ),
        evidence_status_map={
            "consumer_group_lag": EvidenceStatus.PRESENT,
            "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
        },
        action_fingerprint="prod/kafka-prod/stream-orders/SHARED_TOPIC/orders.completed/BASELINE_DEVIATION/TIER_1",
    )
    defaults.update(overrides)
    return GateInputV1(**defaults)


# ---------------------------------------------------------------------------
# AC 3: GateInputV1.anomaly_family = "BASELINE_DEVIATION"
# ---------------------------------------------------------------------------


def test_gate_input_v1_accepts_baseline_deviation_family() -> None:
    """AC 3: GateInputV1 with anomaly_family='BASELINE_DEVIATION' must not raise ValidationError.

    This test will fail until GateInputV1.anomaly_family Literal is extended in
    contracts/gate_input.py (line ~95) to include 'BASELINE_DEVIATION'.
    """
    gate_input = _make_baseline_deviation_gate_input()
    assert gate_input.anomaly_family == "BASELINE_DEVIATION"


def test_gate_input_v1_baseline_deviation_preserves_all_existing_families() -> None:
    """AC 3: Adding 'BASELINE_DEVIATION' to GateInputV1.anomaly_family Literal must not break
    existing consumers. Verify all three original families still validate successfully."""
    for family in ("CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"):
        gate_input = _make_baseline_deviation_gate_input(
            anomaly_family=family,
            action_fingerprint=f"prod/kafka-prod/stream-orders/SHARED_TOPIC/orders.completed/{family}/TIER_1",
        )
        assert gate_input.anomaly_family == family


def test_gate_input_v1_rejects_unknown_family() -> None:
    """AC 3: Unknown anomaly families must still raise ValidationError (no regression)."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        _make_baseline_deviation_gate_input(
            anomaly_family="UNKNOWN_FAMILY",
            action_fingerprint="prod/kafka-prod/stream-orders/SHARED_TOPIC/orders.completed/UNKNOWN_FAMILY/TIER_1",
        )


# ---------------------------------------------------------------------------
# AC 3: _anomaly_family_from_gate_finding_name
# ---------------------------------------------------------------------------


def test_anomaly_family_from_gate_finding_name_handles_baseline_deviation() -> None:
    """AC 3: _anomaly_family_from_gate_finding_name('baseline_deviation') returns
    'BASELINE_DEVIATION'.

    Finding.name is set to finding.anomaly_family.lower() in _to_gate_finding(),
    so 'baseline_deviation' (lowercase) must be handled.

    This test will fail until _anomaly_family_from_gate_finding_name is updated in
    pipeline/stages/gating.py to add the BASELINE_DEVIATION branch.
    """
    result = _anomaly_family_from_gate_finding_name("baseline_deviation")
    assert result == "BASELINE_DEVIATION"


def test_anomaly_family_from_gate_finding_name_case_insensitive() -> None:
    """AC 3: _anomaly_family_from_gate_finding_name is case-insensitive via .strip().upper()
    so both 'BASELINE_DEVIATION' and 'baseline_deviation' must return 'BASELINE_DEVIATION'."""
    assert _anomaly_family_from_gate_finding_name("BASELINE_DEVIATION") == "BASELINE_DEVIATION"
    assert _anomaly_family_from_gate_finding_name("Baseline_Deviation") == "BASELINE_DEVIATION"
    assert _anomaly_family_from_gate_finding_name("  baseline_deviation  ") == "BASELINE_DEVIATION"


def test_anomaly_family_from_gate_finding_name_existing_families_unchanged() -> None:
    """AC 3: Existing family mappings must not be broken by the additive BASELINE_DEVIATION
    extension (regression guard)."""
    assert _anomaly_family_from_gate_finding_name("consumer_lag") == "CONSUMER_LAG"
    assert _anomaly_family_from_gate_finding_name("volume_drop") == "VOLUME_DROP"
    assert (
        _anomaly_family_from_gate_finding_name("throughput_constrained_proxy")
        == "THROUGHPUT_CONSTRAINED_PROXY"
    )


def test_anomaly_family_from_gate_finding_name_raises_for_unknown() -> None:
    """AC 3: _anomaly_family_from_gate_finding_name raises ValueError for truly unknown names
    (existing behaviour must be preserved)."""
    with pytest.raises(ValueError, match="Unsupported finding name"):
        _anomaly_family_from_gate_finding_name("completely_unknown_anomaly")


# ---------------------------------------------------------------------------
# AC 3: _sustained_identity_key handles BASELINE_DEVIATION
# ---------------------------------------------------------------------------


def test_sustained_identity_key_handles_baseline_deviation_three_element_scope() -> None:
    """AC 3: _sustained_identity_key(scope=3-tuple, anomaly_family='BASELINE_DEVIATION')
    returns a valid 4-tuple identity key.

    This test will fail until the Literal type annotation for anomaly_family in
    _sustained_identity_key is extended to include 'BASELINE_DEVIATION'.
    At runtime the function body already handles the value dynamically.
    """
    scope = ("prod", "kafka-prod", "orders.completed")
    result = _sustained_identity_key(scope=scope, anomaly_family="BASELINE_DEVIATION")

    assert isinstance(result, tuple)
    assert len(result) == 4
    assert result[0] == "prod"
    assert result[1] == "kafka-prod"
    assert result[2] == "topic:orders.completed"
    assert result[3] == "BASELINE_DEVIATION"


def test_sustained_identity_key_handles_baseline_deviation_four_element_scope() -> None:
    """AC 3: _sustained_identity_key handles 4-element scopes (group scope shape)
    with BASELINE_DEVIATION anomaly family."""
    scope = ("prod", "kafka-prod", "my-consumer-group", "orders.completed")
    result = _sustained_identity_key(scope=scope, anomaly_family="BASELINE_DEVIATION")

    assert isinstance(result, tuple)
    assert len(result) == 4
    assert result[2] == "group:my-consumer-group"
    assert result[3] == "BASELINE_DEVIATION"


def test_sustained_identity_key_existing_families_still_work() -> None:
    """AC 3: Extending the Literal annotation must not break existing anomaly families
    in _sustained_identity_key (regression guard)."""
    scope = ("prod", "kafka-prod", "orders.completed")
    for family in ("CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"):
        result = _sustained_identity_key(scope=scope, anomaly_family=family)  # type: ignore[arg-type]
        assert result[3] == family
