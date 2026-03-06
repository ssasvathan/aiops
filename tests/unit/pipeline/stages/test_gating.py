import io
import json
from datetime import UTC, datetime
from time import perf_counter

import pytest

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.contracts.rulebook import (
    GateCheck,
    GateEffect,
    GateEffects,
    GateSpec,
    RulebookCaps,
    RulebookDefaults,
    RulebookV1,
)
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.gating import (
    GateInputContext,
    collect_gate_inputs_by_scope,
    evaluate_rulebook_gates,
)
from aiops_triage_pipeline.pipeline.stages.peak import (
    collect_peak_stage_output,
    load_rulebook_policy,
)


def _peak_policy_for_tests() -> PeakPolicyV1:
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


def _rulebook_policy_for_tests(required: int = 5) -> RulebookV1:
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
    gates = tuple(
        GateSpec(
            id=gate_id,
            name=f"Gate {gate_id}",
            intent="test",
            effect=GateEffects(),
            checks=(GateCheck(check_id=f"{gate_id}_CHECK", type="always_pass"),),
        )
        for gate_id in ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
    )
    return RulebookV1(
        rulebook_id="rulebook.v1",
        version=1,
        evaluation_interval_minutes=5,
        sustained_intervals_required=required,
        defaults=defaults,
        caps=caps,
        gates=gates,
    )


class _DedupeStore:
    def __init__(self, *, duplicate: bool = False, fail_on_check: bool = False) -> None:
        self.duplicate = duplicate
        self.fail_on_check = fail_on_check
        self.remembered: list[str] = []
        self.remembered_actions: list[Action] = []

    def is_duplicate(self, fingerprint: str) -> bool:  # noqa: ARG002
        if self.fail_on_check:
            raise RuntimeError("dedupe store unavailable")
        return self.duplicate

    def remember(self, fingerprint: str, action: Action) -> bool:
        self.remembered.append(fingerprint)
        self.remembered_actions.append(action)
        return True


def _gate_input_for_eval() -> GateInputV1:
    return GateInputV1(
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role="SHARED_TOPIC",
        anomaly_family="VOLUME_DROP",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.95,
        sustained=True,
        findings=(
            Finding(
                finding_id="f-1",
                name="volume-drop",
                is_anomalous=True,
                evidence_required=("topic_messages_in_per_sec",),
                is_primary=True,
                severity="HIGH",
                reason_codes=("VOLUME_DROP",),
            ),
        ),
        evidence_status_map={"topic_messages_in_per_sec": EvidenceStatus.PRESENT},
        # Fingerprint is hardcoded for unit test isolation — it intentionally does not
        # reflect env/tier mutations applied via model_copy() in derived fixtures.
        action_fingerprint="prod/cluster-a/stream-orders/SHARED_TOPIC/orders/VOLUME_DROP/TIER_0",
        peak=True,
    )


def _parse_logs(stream: io.StringIO) -> list[dict]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_collect_gate_inputs_by_scope_propagates_unknown_evidence_status_map() -> None:
    samples = {
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
    evidence_output = collect_evidence_stage_output(samples)
    scope = ("prod", "cluster-a", "orders")
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evaluation_time=datetime(2026, 3, 3, 12, 0, tzinfo=UTC),
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        peak_policy=_peak_policy_for_tests(),
        rulebook_policy=_rulebook_policy_for_tests(),
    )

    gate_inputs_by_scope = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: GateInputContext(
                stream_id="stream-orders",
                topic_role="SOURCE_TOPIC",
                criticality_tier=CriticalityTier.TIER_0,
                proposed_action=Action.PAGE,
                diagnosis_confidence=0.75,
            )
        },
    )

    assert scope in gate_inputs_by_scope
    assert len(gate_inputs_by_scope[scope]) == 1
    gate_input = gate_inputs_by_scope[scope][0]
    assert gate_input.anomaly_family == "VOLUME_DROP"
    assert gate_input.evidence_status_map == dict(
        evidence_output.evidence_status_map_by_scope[scope]
    )
    assert (
        gate_input.evidence_status_map["failed_produce_requests_per_sec"]
        == EvidenceStatus.UNKNOWN
    )
    assert gate_input.topic == "orders"
    assert gate_input.consumer_group is None


def test_collect_gate_inputs_by_scope_uses_topic_context_fallback_for_group_scope() -> None:
    samples = {
        "consumer_group_lag": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 120.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 180.0,
            },
        ],
        "consumer_group_offset": [
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 2.0,
            },
            {
                "labels": {
                    "env": "prod",
                    "cluster_name": "cluster-a",
                    "group": "payments-worker",
                    "topic": "payments",
                },
                "value": 7.0,
            },
        ],
    }
    evidence_output = collect_evidence_stage_output(samples)
    group_scope = ("prod", "cluster-a", "payments-worker", "payments")
    topic_scope = ("prod", "cluster-a", "payments")
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evaluation_time=datetime(2026, 3, 3, 12, 0, tzinfo=UTC),
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        peak_policy=_peak_policy_for_tests(),
        rulebook_policy=_rulebook_policy_for_tests(),
    )

    gate_inputs_by_scope = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            topic_scope: GateInputContext(
                stream_id="stream-payments",
                topic_role="SHARED_TOPIC",
                criticality_tier=CriticalityTier.TIER_1,
                proposed_action=Action.TICKET,
                diagnosis_confidence=0.6,
            )
        },
    )

    assert group_scope in gate_inputs_by_scope
    gate_input = gate_inputs_by_scope[group_scope][0]
    assert gate_input.consumer_group == "payments-worker"
    assert gate_input.topic == "payments"
    assert gate_input.stream_id == "stream-payments"
    assert gate_input.anomaly_family == "CONSUMER_LAG"


def test_collect_gate_inputs_by_scope_raises_when_context_missing() -> None:
    samples = {
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
    }
    evidence_output = collect_evidence_stage_output(samples)
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={("prod", "cluster-a", "orders"): [10.0, 20.0, 30.0, 40.0]},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evaluation_time=datetime(2026, 3, 3, 12, 0, tzinfo=UTC),
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        peak_policy=_peak_policy_for_tests(),
        rulebook_policy=_rulebook_policy_for_tests(),
    )

    with pytest.raises(KeyError, match="Missing gate-input context"):
        collect_gate_inputs_by_scope(
            evidence_output=evidence_output,
            peak_output=peak_output,
            context_by_scope={},
        )


def test_evaluate_rulebook_gates_emits_complete_decision_and_ordered_gate_ids() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.gate_rule_ids == ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
    assert decision.final_action == Action.PAGE
    assert decision.env_cap_applied is False
    assert decision.action_fingerprint
    assert decision.postmortem_required is True
    assert decision.postmortem_mode == "SOFT"
    assert decision.postmortem_reason_codes == ("PM_PEAK_SUSTAINED",)


def test_evaluate_rulebook_gates_enforces_monotonic_action_reduction() -> None:
    rulebook = load_rulebook_policy()
    ag2 = next(gate for gate in rulebook.gates if gate.id == "AG2")
    strengthened_ag2 = ag2.model_copy(
        update={
            "effect": ag2.effect.model_copy(
                update={
                    "on_fail": GateEffect(
                        cap_action_to="PAGE",
                        set_reason_codes=("AG2_ATTEMPTED_ESCALATION",),
                    )
                }
            )
        }
    )
    reordered_gates = tuple(
        strengthened_ag2 if gate.id == "AG2" else gate for gate in rulebook.gates
    )
    monotonic_rulebook = rulebook.model_copy(update={"gates": reordered_gates})

    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={
                "proposed_action": Action.OBSERVE,
                "evidence_status_map": {"topic_messages_in_per_sec": EvidenceStatus.UNKNOWN},
            }
        ),
        rulebook=monotonic_rulebook,
    )

    assert decision.final_action == Action.OBSERVE
    assert "AG2_ATTEMPTED_ESCALATION" in decision.gate_reason_codes


def test_evaluate_rulebook_gates_fails_when_gate_order_is_invalid() -> None:
    rulebook = load_rulebook_policy()
    bad_order = rulebook.gates[:-2] + (rulebook.gates[-1], rulebook.gates[-2])
    invalid_rulebook = rulebook.model_copy(update={"gates": bad_order})

    with pytest.raises(ValueError, match="Rulebook gate order must be"):
        evaluate_rulebook_gates(
            gate_input=_gate_input_for_eval(),
            rulebook=invalid_rulebook,
        )


def test_evaluate_rulebook_gates_ag5_duplicate_suppresses_action() -> None:
    dedupe_store = _DedupeStore(duplicate=True)
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert decision.final_action == Action.OBSERVE
    assert "AG5_DUPLICATE_SUPPRESSED" in decision.gate_reason_codes
    assert dedupe_store.remembered == []


def test_evaluate_rulebook_gates_ag5_store_error_applies_safe_cap() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(fail_on_check=True),
    )

    assert decision.final_action == Action.NOTIFY
    assert "AG5_DEDUPE_STORE_ERROR" in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag5_missing_store_applies_safe_cap() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        dedupe_store=None,
    )

    assert decision.final_action == Action.NOTIFY
    assert "AG5_DEDUPE_STORE_ERROR" in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag5_non_duplicate_keeps_action_and_records_fingerprint() -> None:
    dedupe_store = _DedupeStore(duplicate=False)
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert decision.final_action == Action.PAGE
    assert dedupe_store.remembered == [decision.action_fingerprint]


def test_evaluate_rulebook_gates_ag6_sets_postmortem_without_action_escalation() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(update={"proposed_action": Action.OBSERVE}),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.OBSERVE
    assert decision.postmortem_required is True
    assert decision.postmortem_reason_codes == ("PM_PEAK_SUSTAINED",)


def test_evaluate_rulebook_gates_ag0_invalid_input_prevents_postmortem_trigger() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(update={"action_fingerprint": "   "}),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.OBSERVE
    assert "AG0_INVALID_INPUT" in decision.gate_reason_codes
    assert decision.postmortem_required is False
    assert decision.postmortem_mode is None
    assert decision.postmortem_reason_codes == ()


def test_evaluate_rulebook_gates_ag2_ignores_non_anomalous_primary_findings() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={
                "findings": (
                    Finding(
                        finding_id="anomalous",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=False,
                    ),
                    Finding(
                        finding_id="non-anomalous-primary",
                        name="non-anomalous",
                        is_anomalous=False,
                        evidence_required=("missing_metric",),
                        is_primary=True,
                    ),
                )
            }
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.PAGE
    assert "AG2_INSUFFICIENT_EVIDENCE" not in decision.gate_reason_codes


@pytest.mark.parametrize(
    "status",
    (EvidenceStatus.UNKNOWN, EvidenceStatus.ABSENT, EvidenceStatus.STALE),
)
def test_evaluate_rulebook_gates_ag2_downgrades_for_all_insufficient_statuses(
    status: EvidenceStatus,
) -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"evidence_status_map": {"topic_messages_in_per_sec": status}}
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.NOTIFY
    assert "AG2_INSUFFICIENT_EVIDENCE" in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag2_allows_explicit_non_present_status_per_finding() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={
                "findings": (
                    Finding(
                        finding_id="f-allow-unknown",
                        name="volume-drop",
                        is_anomalous=True,
                        evidence_required=("topic_messages_in_per_sec",),
                        is_primary=True,
                        allowed_non_present_statuses_by_evidence={
                            "topic_messages_in_per_sec": (EvidenceStatus.UNKNOWN,)
                        },
                    ),
                ),
                "evidence_status_map": {"topic_messages_in_per_sec": EvidenceStatus.UNKNOWN},
            }
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.PAGE
    assert "AG2_INSUFFICIENT_EVIDENCE" not in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag3_denies_page_for_source_topic() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(update={"topic_role": "SOURCE_TOPIC"}),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.TICKET
    assert "AG3_PAGING_DENIED_SOURCE_TOPIC" in decision.gate_reason_codes
    assert "AG2_INSUFFICIENT_EVIDENCE" not in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag2_short_circuits_page_before_ag3_for_source_topic() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={
                "topic_role": "SOURCE_TOPIC",
                "evidence_status_map": {"topic_messages_in_per_sec": EvidenceStatus.UNKNOWN},
            }
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.NOTIFY
    assert "AG2_INSUFFICIENT_EVIDENCE" in decision.gate_reason_codes
    assert "AG3_PAGING_DENIED_SOURCE_TOPIC" not in decision.gate_reason_codes
    assert "LOW_CONFIDENCE" not in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag4_downgrades_when_not_sustained() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"sustained": False, "diagnosis_confidence": 0.95}
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.OBSERVE
    assert "NOT_SUSTAINED" in decision.gate_reason_codes
    assert "LOW_CONFIDENCE" not in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag4_downgrades_when_confidence_is_below_floor() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"sustained": True, "diagnosis_confidence": 0.59}
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.OBSERVE
    assert "LOW_CONFIDENCE" in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


def test_evaluate_rulebook_gates_ag4_records_deterministic_reason_order_when_both_fail() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"sustained": False, "diagnosis_confidence": 0.59}
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.OBSERVE
    assert tuple(
        code for code in decision.gate_reason_codes if code in {"LOW_CONFIDENCE", "NOT_SUSTAINED"}
    ) == ("LOW_CONFIDENCE", "NOT_SUSTAINED")


def test_evaluate_rulebook_gates_ag4_allows_boundary_confidence_of_point_six() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"sustained": True, "diagnosis_confidence": 0.6}
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.PAGE
    assert "LOW_CONFIDENCE" not in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


@pytest.mark.parametrize(
    ("confidence", "sustained", "expected_action", "expected_reason_codes"),
    [
        (0.95, False, Action.OBSERVE, ("NOT_SUSTAINED",)),
        (0.59, True, Action.OBSERVE, ("LOW_CONFIDENCE",)),
        (0.6, True, Action.TICKET, ()),
    ],
)
def test_evaluate_rulebook_gates_ag4_applies_to_ticket_actions(
    confidence: float,
    sustained: bool,
    expected_action: Action,
    expected_reason_codes: tuple[str, ...],
) -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={
                "proposed_action": Action.TICKET,
                "diagnosis_confidence": confidence,
                "sustained": sustained,
            }
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == expected_action
    for reason_code in expected_reason_codes:
        assert reason_code in decision.gate_reason_codes
    for reason_code in {"LOW_CONFIDENCE", "NOT_SUSTAINED"} - set(expected_reason_codes):
        assert reason_code not in decision.gate_reason_codes


def test_evaluate_rulebook_gates_marks_env_cap_applied_and_records_reason() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"env": Environment.LOCAL, "diagnosis_confidence": 1.0, "sustained": True}
        ),
        rulebook=load_rulebook_policy(),
    )

    assert decision.env_cap_applied is True
    assert decision.final_action == Action.OBSERVE
    assert "AG1_ENV_OR_TIER_CAP" in decision.gate_reason_codes


def test_evaluate_rulebook_gates_uses_stage_alias_for_uat_env_cap() -> None:
    rulebook = load_rulebook_policy()
    legacy_caps = dict(rulebook.caps.max_action_by_env)
    legacy_caps.pop("uat", None)
    legacy_caps["stage"] = "TICKET"
    legacy_rulebook = rulebook.model_copy(
        update={
            "caps": rulebook.caps.model_copy(
                update={"max_action_by_env": legacy_caps}
            )
        }
    )

    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(update={"env": Environment.UAT}),
        rulebook=legacy_rulebook,
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.env_cap_applied is True
    assert decision.final_action == Action.TICKET
    assert "AG1_ENV_OR_TIER_CAP" in decision.gate_reason_codes


def test_evaluate_rulebook_gates_keeps_env_cap_applied_false_for_tier_only_cap() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"criticality_tier": CriticalityTier.TIER_1}
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.TICKET
    assert decision.env_cap_applied is False
    assert "AG1_ENV_OR_TIER_CAP" in decision.gate_reason_codes


def test_evaluate_rulebook_gates_applies_dev_env_cap() -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(update={"env": Environment.DEV}),
        rulebook=load_rulebook_policy(),
    )

    assert decision.env_cap_applied is True
    assert decision.final_action == Action.NOTIFY
    assert "AG1_ENV_OR_TIER_CAP" in decision.gate_reason_codes


@pytest.mark.parametrize(
    ("env", "tier", "expected_action", "expected_env_cap_applied", "expect_ag1_reason"),
    [
        (Environment.LOCAL, CriticalityTier.TIER_0, Action.OBSERVE, True, True),
        (Environment.DEV, CriticalityTier.TIER_0, Action.NOTIFY, True, True),
        (Environment.UAT, CriticalityTier.TIER_0, Action.TICKET, True, True),
        (Environment.PROD, CriticalityTier.TIER_0, Action.PAGE, False, False),
        (Environment.PROD, CriticalityTier.TIER_1, Action.TICKET, False, True),
        (Environment.PROD, CriticalityTier.TIER_2, Action.NOTIFY, False, True),
        (Environment.PROD, CriticalityTier.UNKNOWN, Action.NOTIFY, False, True),
    ],
)
def test_evaluate_rulebook_gates_ag1_matrix(
    env: Environment,
    tier: CriticalityTier,
    expected_action: Action,
    expected_env_cap_applied: bool,
    expect_ag1_reason: bool,
) -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={
                "env": env,
                "criticality_tier": tier,
            }
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.gate_rule_ids == ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
    assert decision.final_action == expected_action
    assert decision.env_cap_applied is expected_env_cap_applied
    if expect_ag1_reason:
        assert "AG1_ENV_OR_TIER_CAP" in decision.gate_reason_codes
    else:
        assert "AG1_ENV_OR_TIER_CAP" not in decision.gate_reason_codes


def test_evaluate_rulebook_gates_is_deterministic_for_same_input() -> None:
    gate_input = _gate_input_for_eval()
    rulebook = load_rulebook_policy()

    first = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook)
    second = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook)

    assert first == second


def test_evaluate_rulebook_gates_logs_latency_guardrail_warning_when_threshold_exceeded(
    monkeypatch,
    log_stream: io.StringIO,
) -> None:
    perf_counter_values = iter((10.0, 10.8))
    monkeypatch.setattr(
        "aiops_triage_pipeline.pipeline.stages.gating.perf_counter",
        lambda: next(perf_counter_values),
    )

    _ = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        latency_warning_threshold_ms=500,
    )

    warning_events = [
        entry
        for entry in _parse_logs(log_stream)
        if entry.get("event") == "rulebook_gate_evaluation_slow"
    ]
    assert len(warning_events) == 1
    assert warning_events[0]["latency_warning_threshold_ms"] == 500


def test_evaluate_rulebook_gates_micro_benchmark_guardrail() -> None:
    gate_input = _gate_input_for_eval()
    rulebook = load_rulebook_policy()
    durations_ms: list[float] = []

    for _ in range(200):
        started = perf_counter()
        _ = evaluate_rulebook_gates(gate_input=gate_input, rulebook=rulebook)
        durations_ms.append((perf_counter() - started) * 1000.0)

    durations_ms.sort()
    p99_index = int(len(durations_ms) * 0.99) - 1
    p99_duration_ms = durations_ms[max(p99_index, 0)]
    assert p99_duration_ms <= 500.0


def test_evaluate_rulebook_gates_ag5_remember_receives_current_action() -> None:
    dedupe_store = _DedupeStore(duplicate=False)
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert decision.final_action == Action.PAGE
    assert len(dedupe_store.remembered_actions) == 1
    assert dedupe_store.remembered_actions[0] == Action.PAGE


def test_evaluate_rulebook_gates_ag5_remember_receives_capped_action_after_ag1() -> None:
    dedupe_store = _DedupeStore(duplicate=False)
    # DEV env caps PAGE → NOTIFY via AG1; AG5 remember should receive NOTIFY
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(
            update={"env": Environment.DEV, "diagnosis_confidence": 0.95, "sustained": True}
        ),
        rulebook=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert decision.final_action == Action.NOTIFY
    assert len(dedupe_store.remembered_actions) == 1
    assert dedupe_store.remembered_actions[0] == Action.NOTIFY


def test_evaluate_rulebook_gates_ag5_skips_remember_on_duplicate() -> None:
    dedupe_store = _DedupeStore(duplicate=True)
    _ = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval(),
        rulebook=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert dedupe_store.remembered == []
    assert dedupe_store.remembered_actions == []


# ---------------------------------------------------------------------------
# AG6: PM_PEAK_SUSTAINED predicate boundary conditions
# ---------------------------------------------------------------------------



@pytest.mark.parametrize(
    ("update_fields", "expected_final_action"),
    [
        # PROD + TIER_0: outer guard passes, predicate fails — action unchanged by AG6
        ({"peak": False}, Action.PAGE),
        ({"peak": None}, Action.PAGE),
        ({"sustained": False}, Action.OBSERVE),  # AG4 caps PAGE→OBSERVE first
        # Non-PROD / non-TIER_0: outer guard never reached — action set by AG1 cap
        ({"env": Environment.DEV}, Action.NOTIFY),
        ({"env": Environment.UAT}, Action.TICKET),
        ({"criticality_tier": CriticalityTier.TIER_1}, Action.TICKET),
        ({"criticality_tier": CriticalityTier.TIER_2}, Action.NOTIFY),
        ({"criticality_tier": CriticalityTier.UNKNOWN}, Action.NOTIFY),
    ],
    ids=[
        "peak_false",
        "peak_none",
        "sustained_false",
        "env_dev",
        "env_uat",
        "tier_1",
        "tier_2",
        "tier_unknown",
    ],
)
def test_evaluate_rulebook_gates_ag6_predicate_does_not_fire_when_any_condition_missing(
    update_fields: dict,
    expected_final_action: Action,
) -> None:
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(update=update_fields),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.postmortem_required is False
    assert decision.postmortem_mode is None
    assert decision.postmortem_reason_codes == ()
    assert decision.final_action == expected_final_action  # AC4: AG6 must not change final_action


def test_evaluate_rulebook_gates_ag6_no_action_escalation_when_predicate_does_not_fire() -> None:
    # peak=False prevents predicate; all other conditions leave PAGE intact
    decision = evaluate_rulebook_gates(
        gate_input=_gate_input_for_eval().model_copy(update={"peak": False}),
        rulebook=load_rulebook_policy(),
        dedupe_store=_DedupeStore(duplicate=False),
    )

    assert decision.final_action == Action.PAGE  # AG6 must not change final_action
    assert decision.postmortem_required is False
    assert decision.postmortem_mode is None
    assert decision.postmortem_reason_codes == ()
