"""ATDD support data for Story 1.5 red-phase tests."""

from __future__ import annotations

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.rulebook import GateCheck, RulebookV1
from aiops_triage_pipeline.pipeline.stages.peak import load_rulebook_policy


def build_gate_input(
    *,
    env: Environment = Environment.PROD,
    tier: CriticalityTier = CriticalityTier.TIER_0,
    topic_role: str = "SHARED_TOPIC",
    proposed_action: Action = Action.PAGE,
    evidence_status: EvidenceStatus = EvidenceStatus.PRESENT,
) -> GateInputV1:
    """Build deterministic gate input payload used by Story 1.5 acceptance tests."""
    return GateInputV1(
        env=env,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role=topic_role,
        anomaly_family="VOLUME_DROP",
        criticality_tier=tier,
        proposed_action=proposed_action,
        diagnosis_confidence=0.95,
        sustained=True,
        findings=(
            Finding(
                finding_id="f-1",
                name="volume-drop",
                is_anomalous=True,
                evidence_required=("topic_messages_in_per_sec",),
                is_primary=True,
                reason_codes=("VOLUME_DROP",),
            ),
        ),
        evidence_status_map={"topic_messages_in_per_sec": evidence_status},
        action_fingerprint=(
            f"{env.value}/cluster-a/stream-orders/{topic_role}/orders/VOLUME_DROP/{tier.value}"
        ),
        peak=True,
    )


def build_rulebook_with_unknown_ag0_check_type(
    rulebook: RulebookV1 | None = None,
) -> RulebookV1:
    """Inject an unknown AG0 check type to verify startup handler validation."""
    loaded = rulebook or load_rulebook_policy()
    mutated_gates = []
    for gate in loaded.gates:
        if gate.id != "AG0":
            mutated_gates.append(gate)
            continue
        mutated_gates.append(
            gate.model_copy(
                update={
                    "checks": gate.checks
                    + (
                        GateCheck(
                            check_id="AG0_UNKNOWN_HANDLER_TYPE",
                            type="handler_type_not_registered",
                        ),
                    )
                }
            )
        )

    return loaded.model_copy(update={"gates": tuple(mutated_gates)})


def build_stage_alias_only_rulebook(rulebook: RulebookV1 | None = None) -> RulebookV1:
    """Drop canonical `uat` cap and keep legacy `stage` alias for compatibility checks."""
    loaded = rulebook or load_rulebook_policy()
    env_caps = dict(loaded.caps.max_action_by_env)
    env_caps.pop("uat", None)
    env_caps["stage"] = "TICKET"
    return loaded.model_copy(
        update={
            "caps": loaded.caps.model_copy(update={"max_action_by_env": env_caps})
        }
    )
