"""Unit tests for audit.replay — reproduce_gate_decision() and build_audit_trail() (Story 7.4)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from aiops_triage_pipeline.audit.replay import build_audit_trail, reproduce_gate_decision
from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.rulebook import (
    GateCheck,
    GateEffect,
    GateEffects,
    GateSpec,
    RulebookCaps,
    RulebookDefaults,
    RulebookV1,
)
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceRow,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.pipeline.stages.gating import evaluate_rulebook_gates

# ---------------------------------------------------------------------------
# Test rulebook factory
# ---------------------------------------------------------------------------
# This rulebook is designed for pure unit reproducibility tests (dedupe_store=None):
#   - AG4 has proper min_value + equals checks so it can evaluate confidence/sustained
#   - AG5 has NO on_store_error effect → dedupe_store=None is a no-op for actions > OBSERVE
#   - AG6 has on_pass/on_fail for postmortem selection
#   - Other gates use simple pass-through effects


def _build_test_rulebook(version: int = 1) -> RulebookV1:
    """Build a deterministic test rulebook with proper AG4 checks and no AG5 on_store_error."""
    defaults = RulebookDefaults(
        missing_series_policy="UNKNOWN_NOT_ZERO",
        required_evidence_policy="PRESENT_ONLY",
        missing_confidence_policy="DOWNGRADE",
        missing_sustained_policy="DOWNGRADE",
    )
    caps = RulebookCaps(
        max_action_by_env={
            "local": "OBSERVE",
            "dev": "NOTIFY",
            "uat": "TICKET",
            "stage": "TICKET",
            "prod": "PAGE",
        },
        max_action_by_tier_in_prod={
            "TIER_0": "PAGE",
            "TIER_1": "TICKET",
            "TIER_2": "NOTIFY",
            "UNKNOWN": "NOTIFY",
        },
        paging_denied_topic_roles=("SOURCE_TOPIC",),
    )

    def _simple_gate(gate_id: str) -> GateSpec:
        return GateSpec(
            id=gate_id,
            name=f"Gate {gate_id}",
            intent="test",
            effect=GateEffects(),
            checks=(GateCheck(check_id=f"{gate_id}_CHECK", type="always_pass"),),
        )

    ag1 = GateSpec(
        id="AG1",
        name="Environment + tier caps",
        intent="test",
        effect=GateEffects(
            on_cap_applied=GateEffect(set_reason_codes=("AG1_ENV_OR_TIER_CAP",)),
        ),
        checks=(GateCheck(check_id="AG1_CHECK", type="always_pass"),),
    )

    ag2 = GateSpec(
        id="AG2",
        name="Evidence sufficiency",
        intent="test",
        effect=GateEffects(
            on_fail=GateEffect(
                cap_action_to="NOTIFY",
                set_reason_codes=("AG2_INSUFFICIENT_EVIDENCE",),
            ),
        ),
        checks=(GateCheck(check_id="AG2_CHECK", type="always_pass"),),
    )

    ag4 = GateSpec(
        id="AG4",
        name="Confidence + sustained gating",
        intent="test",
        effect=GateEffects(
            on_fail=GateEffect(cap_action_to="OBSERVE"),
        ),
        checks=(
            GateCheck(
                check_id="AG4_CONFIDENCE_MIN",
                type="min_value",
                field="diagnosis_confidence",
                min=0.6,
                reason_code_on_fail="LOW_CONFIDENCE",
            ),
            GateCheck(
                check_id="AG4_SUSTAINED_REQUIRED",
                type="equals",
                field="sustained",
                value=True,
                reason_code_on_fail="NOT_SUSTAINED",
            ),
        ),
    )

    # AG5: no on_store_error → dedupe_store=None is a no-op for non-OBSERVE actions
    ag5 = GateSpec(
        id="AG5",
        name="Storm control (dedupe)",
        intent="test",
        effect=GateEffects(),
        checks=(GateCheck(check_id="AG5_CHECK", type="dedupe_check"),),
    )

    ag6 = GateSpec(
        id="AG6",
        name="Postmortem policy selector",
        intent="test",
        effect=GateEffects(
            on_pass=GateEffect(
                set_postmortem_required=True,
                set_postmortem_reason_codes=("PM_PEAK_SUSTAINED",),
            ),
            on_fail=GateEffect(set_postmortem_required=False),
        ),
        checks=(GateCheck(check_id="AG6_CHECK", type="always_pass"),),
    )

    return RulebookV1(
        rulebook_id="test-rulebook.v1",
        version=version,
        evaluation_interval_minutes=5,
        sustained_intervals_required=5,
        defaults=defaults,
        caps=caps,
        gates=(
            _simple_gate("AG0"),
            ag1,
            ag2,
            _simple_gate("AG3"),
            ag4,
            ag5,
            ag6,
        ),
    )


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_VOLUME_DROP_FINDING = Finding(
    finding_id="f-volume-drop",
    name="VOLUME_DROP",
    is_anomalous=True,
    evidence_required=("topic_messages_in_per_sec",),
    is_primary=True,
    severity="HIGH",
    reason_codes=("VOLUME_DROP",),
)

_NO_ANOMALY_FINDING = Finding(
    finding_id="f-no-anomaly",
    name="VOLUME_DROP",
    is_anomalous=False,
    evidence_required=("topic_messages_in_per_sec",),
)


def _build_gate_input(
    *,
    env: Environment = Environment.PROD,
    topic_role: str = "SHARED_TOPIC",
    criticality_tier: CriticalityTier = CriticalityTier.TIER_0,
    proposed_action: Action = Action.PAGE,
    diagnosis_confidence: float = 0.8,
    sustained: bool = True,
    peak: bool | None = True,
    findings: tuple[Finding, ...] = (_VOLUME_DROP_FINDING,),
    evidence_status_map: dict[str, EvidenceStatus] | None = None,
) -> GateInputV1:
    if evidence_status_map is None:
        evidence_status_map = {"topic_messages_in_per_sec": EvidenceStatus.PRESENT}
    return GateInputV1(
        env=env,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role=topic_role,
        anomaly_family="VOLUME_DROP",
        criticality_tier=criticality_tier,
        proposed_action=proposed_action,
        diagnosis_confidence=diagnosis_confidence,
        sustained=sustained,
        findings=findings,
        evidence_status_map=evidence_status_map,
        action_fingerprint=(
            f"{env.value}/cluster-a/stream-orders/{topic_role}/"
            f"orders/VOLUME_DROP/{criticality_tier.value}"
        ),
        peak=peak,
    )


def _minimal_topology_context(
    *,
    topic_role: str = "SHARED_TOPIC",
    criticality_tier: CriticalityTier = CriticalityTier.TIER_0,
) -> CaseFileTopologyContext:
    return CaseFileTopologyContext(
        stream_id="stream-orders",
        topic_role=topic_role,  # type: ignore[arg-type]
        criticality_tier=criticality_tier,
        blast_radius="LOCAL_SOURCE_INGESTION",
        routing=CaseFileRoutingContext(
            lookup_level="topic_owner",
            routing_key="OWN::test",
            owning_team_id="team-test",
            owning_team_name="Test Team",
        ),
    )


def _build_minimal_casefile(
    gate_input: GateInputV1,
    action_decision: ActionDecisionV1,
    *,
    rulebook_version: str = "1",
) -> CaseFileTriageV1:
    """Assemble a minimal CaseFileTriageV1 sufficient for audit/reproducibility tests."""
    evidence_snapshot = CaseFileEvidenceSnapshot(
        rows=tuple(
            CaseFileEvidenceRow(
                metric_key=k,
                value=1.0,
                labels={},
                scope=("prod", "cluster-a", "orders"),
            )
            for k in gate_input.evidence_status_map
        ),
        evidence_status_map=dict(gate_input.evidence_status_map),
    )
    topology = _minimal_topology_context(
        topic_role=gate_input.topic_role,
        criticality_tier=gate_input.criticality_tier,
    )
    policy_versions = CaseFilePolicyVersions(
        rulebook_version=rulebook_version,
        peak_policy_version="v1",
        prometheus_metrics_contract_version="v1.0.0",
        exposure_denylist_version="v1.0.0",
        diagnosis_policy_version="v1",
    )
    return CaseFileTriageV1(
        case_id="case-audit-test-001",
        scope=("prod", "cluster-a", "orders"),
        triage_timestamp=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
        evidence_snapshot=evidence_snapshot,
        topology_context=topology,
        gate_input=gate_input,
        action_decision=action_decision,
        policy_versions=policy_versions,
        triage_hash=TRIAGE_HASH_PLACEHOLDER,
    )


# ---------------------------------------------------------------------------
# Task 2: reproduce_gate_decision() — regression suite (AC: 2, 3, 6)
# ---------------------------------------------------------------------------


def test_reproduce_gate_decision_observe_baseline() -> None:
    """OBSERVE path: low confidence, non-anomalous finding, all evidence PRESENT (AC: 2, 3)."""
    rulebook = _build_test_rulebook()
    gate_input = _build_gate_input(
        env=Environment.DEV,
        proposed_action=Action.OBSERVE,
        diagnosis_confidence=0.3,
        sustained=False,
        peak=False,
        findings=(_NO_ANOMALY_FINDING,),
        evidence_status_map={"topic_messages_in_per_sec": EvidenceStatus.PRESENT},
    )
    expected = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook, dedupe_store=None)
    assert expected.final_action == Action.OBSERVE

    casefile = _build_minimal_casefile(gate_input, expected)
    replayed = reproduce_gate_decision(casefile, rulebook)

    assert replayed.final_action == expected.final_action
    assert replayed.gate_rule_ids == expected.gate_rule_ids
    assert replayed.env_cap_applied == expected.env_cap_applied
    assert replayed.postmortem_required == expected.postmortem_required


def test_reproduce_gate_decision_notify_capped_dev() -> None:
    """NOTIFY-capped path: PAGE proposed but env=dev caps via AG1 to NOTIFY (AC: 2, 3)."""
    rulebook = _build_test_rulebook()
    gate_input = _build_gate_input(
        env=Environment.DEV,
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.8,
        sustained=True,
        peak=True,
    )
    expected = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook, dedupe_store=None)
    assert expected.final_action == Action.NOTIFY
    assert expected.env_cap_applied is True

    casefile = _build_minimal_casefile(gate_input, expected)
    replayed = reproduce_gate_decision(casefile, rulebook)

    assert replayed.final_action == expected.final_action
    assert replayed.gate_rule_ids == expected.gate_rule_ids
    assert replayed.env_cap_applied == expected.env_cap_applied
    assert replayed.postmortem_required == expected.postmortem_required


def test_reproduce_gate_decision_ag2_evidence_insufficient() -> None:
    """AG2 fail path: required metric UNKNOWN → action capped (AC: 2, 3)."""
    rulebook = _build_test_rulebook()
    gate_input = _build_gate_input(
        env=Environment.PROD,
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.8,
        sustained=True,
        peak=False,
        evidence_status_map={"topic_messages_in_per_sec": EvidenceStatus.UNKNOWN},
    )
    expected = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook, dedupe_store=None)
    # AG2 caps PAGE → NOTIFY; final should be NOTIFY or lower
    assert _action_priority(expected.final_action) <= _action_priority(Action.NOTIFY)

    casefile = _build_minimal_casefile(gate_input, expected)
    replayed = reproduce_gate_decision(casefile, rulebook)

    assert replayed.final_action == expected.final_action
    assert replayed.gate_rule_ids == expected.gate_rule_ids
    assert replayed.env_cap_applied == expected.env_cap_applied
    assert replayed.postmortem_required == expected.postmortem_required


def test_reproduce_gate_decision_ag4_sustained_fail() -> None:
    """AG4 fail path: sustained=False → action downgraded to OBSERVE (AC: 2, 3)."""
    rulebook = _build_test_rulebook()
    gate_input = _build_gate_input(
        env=Environment.PROD,
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.8,
        sustained=False,
        peak=True,
    )
    expected = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook, dedupe_store=None)
    assert expected.final_action == Action.OBSERVE
    assert "NOT_SUSTAINED" in expected.gate_reason_codes

    casefile = _build_minimal_casefile(gate_input, expected)
    replayed = reproduce_gate_decision(casefile, rulebook)

    assert replayed.final_action == expected.final_action
    assert replayed.gate_rule_ids == expected.gate_rule_ids
    assert replayed.env_cap_applied == expected.env_cap_applied
    assert replayed.postmortem_required == expected.postmortem_required


def test_reproduce_gate_decision_ag6_postmortem_trigger() -> None:
    """AG6 path: prod + TIER_0 + peak=True + sustained=True → PAGE + postmortem_required."""
    # AC: 2, 3
    rulebook = _build_test_rulebook()
    gate_input = _build_gate_input(
        env=Environment.PROD,
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.8,
        sustained=True,
        peak=True,
    )
    expected = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook, dedupe_store=None)
    assert expected.final_action == Action.PAGE
    assert expected.postmortem_required is True

    casefile = _build_minimal_casefile(gate_input, expected)
    replayed = reproduce_gate_decision(casefile, rulebook)

    assert replayed.final_action == expected.final_action
    assert replayed.gate_rule_ids == expected.gate_rule_ids
    assert replayed.env_cap_applied == expected.env_cap_applied
    assert replayed.postmortem_required == expected.postmortem_required


def test_reproduce_gate_decision_version_mismatch_raises_value_error() -> None:
    """Version mismatch: reproduce_gate_decision raises ValueError (AC: 2, 3, 6)."""
    rulebook = _build_test_rulebook(version=1)
    gate_input = _build_gate_input(proposed_action=Action.OBSERVE)
    action_decision = evaluate_rulebook_gates(
        gate_input=gate_input, rulebook=rulebook, dedupe_store=None
    )
    casefile = _build_minimal_casefile(gate_input, action_decision, rulebook_version="99")

    with pytest.raises(ValueError, match="version"):
        reproduce_gate_decision(casefile, rulebook)


# ---------------------------------------------------------------------------
# Task 3: build_audit_trail() — completeness assertions (AC: 4, 5, 6)
# ---------------------------------------------------------------------------

_REQUIRED_AUDIT_KEYS = frozenset(
    {
        "case_id",
        "triage_timestamp",
        "evidence_rows",
        "evidence_status_map",
        "gate_rule_ids",
        "gate_reason_codes",
        "final_action",
        "policy_versions",
        "triage_hash",
    }
)

_REQUIRED_POLICY_VERSION_KEYS = frozenset(
    {
        "rulebook_version",
        "peak_policy_version",
        "prometheus_metrics_contract_version",
        "exposure_denylist_version",
        "diagnosis_policy_version",
    }
)


def _action_priority(action: Action) -> int:
    return {"OBSERVE": 0, "NOTIFY": 1, "TICKET": 2, "PAGE": 3}[action.value]


def _make_full_audit_casefile() -> CaseFileTriageV1:
    """Build a casefile suitable for complete audit trail assertions."""
    rulebook = _build_test_rulebook()
    gate_input = _build_gate_input(
        env=Environment.PROD,
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.8,
        sustained=True,
        peak=True,
    )
    action_decision = evaluate_rulebook_gates(
        gate_input=gate_input, rulebook=rulebook, dedupe_store=None
    )
    return _build_minimal_casefile(gate_input, action_decision)


def test_build_audit_trail_returns_all_required_keys() -> None:
    """All NFR-T6 required keys present in audit trail (AC: 4, 6)."""
    casefile = _make_full_audit_casefile()
    trail: dict[str, Any] = build_audit_trail(casefile)
    assert _REQUIRED_AUDIT_KEYS.issubset(trail.keys()), (
        f"Missing keys: {_REQUIRED_AUDIT_KEYS - set(trail.keys())}"
    )


def test_build_audit_trail_policy_versions_contains_all_five_non_empty_strings() -> None:
    """policy_versions sub-dict has all 5 non-empty string values (AC: 5, 6)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    policy_versions: dict[str, Any] = trail["policy_versions"]

    missing_pv_keys = _REQUIRED_POLICY_VERSION_KEYS - set(policy_versions.keys())
    assert _REQUIRED_POLICY_VERSION_KEYS.issubset(policy_versions.keys()), (
        f"Missing policy_version keys: {missing_pv_keys}"
    )
    for key in _REQUIRED_POLICY_VERSION_KEYS:
        value = policy_versions[key]
        assert isinstance(value, str) and value, (
            f"policy_versions[{key!r}] must be a non-empty string, got {value!r}"
        )


def test_build_audit_trail_triage_hash_is_64_char_hex() -> None:
    """triage_hash in audit trail matches ^[0-9a-f]{64}$ (AC: 4, 6)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    assert re.fullmatch(r"[0-9a-f]{64}", trail["triage_hash"]), (
        f"triage_hash is not 64-char hex: {trail['triage_hash']!r}"
    )


def test_build_audit_trail_gate_rule_ids_contains_all_seven_gates() -> None:
    """gate_rule_ids contains AG0–AG6 for happy-path (AC: 4, 6)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    assert set(trail["gate_rule_ids"]) == {"AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6"}, (
        f"Unexpected gate_rule_ids: {trail['gate_rule_ids']}"
    )


def test_build_audit_trail_gate_reason_codes_is_list() -> None:
    """gate_reason_codes is a list (may be empty for clean paths) (AC: 4, 6)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    assert isinstance(trail["gate_reason_codes"], list)


def test_build_audit_trail_evidence_status_map_values_are_strings() -> None:
    """evidence_status_map values are string-serialized EvidenceStatus (AC: 4)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    for key, value in trail["evidence_status_map"].items():
        assert isinstance(value, str), (
            f"evidence_status_map[{key!r}] should be a string, got {type(value)}"
        )


def test_build_audit_trail_case_id_matches_casefile() -> None:
    """case_id in audit trail matches casefile.case_id (AC: 4)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    assert trail["case_id"] == casefile.case_id


def test_build_audit_trail_triage_hash_matches_casefile() -> None:
    """triage_hash in audit trail matches casefile.triage_hash (AC: 4)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    assert trail["triage_hash"] == casefile.triage_hash


def test_build_audit_trail_final_action_is_string() -> None:
    """final_action is a string value (AC: 4)."""
    casefile = _make_full_audit_casefile()
    trail = build_audit_trail(casefile)
    assert isinstance(trail["final_action"], str)
    assert trail["final_action"] == casefile.action_decision.final_action.value
