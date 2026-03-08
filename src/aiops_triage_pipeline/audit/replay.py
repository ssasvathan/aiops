"""Audit replay and trail functions for deterministic decision reproducibility.

Implements FR60, FR61, and NFR-T6 requirements.
"""

from __future__ import annotations

from typing import Any

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.models.case_file import CaseFileTriageV1
from aiops_triage_pipeline.pipeline.stages.gating import evaluate_rulebook_gates


def reproduce_gate_decision(
    casefile: CaseFileTriageV1,
    rulebook: RulebookV1,
) -> ActionDecisionV1:
    """Replay the gating decision stored in a CaseFile using the provided rulebook.

    Validates that the rulebook version matches the stamped version in the CaseFile,
    then re-evaluates AG0–AG6 deterministically without a dedupe store (AG5 excluded).

    Args:
        casefile: The stored CaseFileTriageV1 whose decision is to be replayed.
        rulebook: The RulebookV1 at the version that produced the original decision.

    Returns:
        A fresh ActionDecisionV1 from deterministic re-evaluation.

    Raises:
        ValueError: If rulebook version does not match casefile.policy_versions.rulebook_version.
    """
    stored_version = casefile.policy_versions.rulebook_version
    if str(rulebook.version) != stored_version:
        raise ValueError(
            f"Rulebook version mismatch: casefile records version {stored_version!r} "
            f"but provided rulebook has version {rulebook.version!r}. "
            "Use the exact rulebook version that produced the original decision."
        )
    return evaluate_rulebook_gates(
        gate_input=casefile.gate_input,
        rulebook=rulebook,
        dedupe_store=None,
    )


def build_audit_trail(casefile: CaseFileTriageV1) -> dict[str, Any]:
    """Construct an NFR-T6 compliant audit trail dict from a stored CaseFileTriageV1.

    Returns a plain serializable dict — suitable for JSON operator review.
    All required NFR-T6 fields are present in the returned structure.

    Args:
        casefile: The CaseFileTriageV1 to extract an audit trail from.

    Returns:
        A dict with keys: case_id, triage_timestamp, evidence_rows, evidence_status_map,
        gate_rule_ids, gate_reason_codes, final_action, policy_versions, triage_hash.
    """
    return {
        "case_id": casefile.case_id,
        "triage_timestamp": casefile.triage_timestamp.isoformat(),
        "evidence_rows": [
            {
                "metric_key": row.metric_key,
                "value": row.value,
                "scope": list(row.scope),
            }
            for row in casefile.evidence_snapshot.rows
        ],
        "evidence_status_map": {
            key: status.value
            for key, status in casefile.evidence_snapshot.evidence_status_map.items()
        },
        "gate_rule_ids": list(casefile.action_decision.gate_rule_ids),
        "gate_reason_codes": list(casefile.action_decision.gate_reason_codes),
        "final_action": casefile.action_decision.final_action.value,
        "policy_versions": casefile.policy_versions.model_dump(),
        "triage_hash": casefile.triage_hash,
    }
