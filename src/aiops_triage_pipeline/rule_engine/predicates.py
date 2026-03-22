"""Pure predicates for AG0-AG3 rule-engine checks."""

from collections.abc import Mapping

from aiops_triage_pipeline.contracts.enums import Action, EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.rule_engine.safety import action_from_policy_value


def has_required_fields_present(gate_input: GateInputV1) -> bool:
    """Validate AG0 required fields for deterministic gate execution."""
    if not gate_input.action_fingerprint.strip():
        return False
    if not gate_input.findings:
        return False
    return True


def has_sufficient_required_evidence(gate_input: GateInputV1) -> bool:
    """Evaluate AG2 evidence sufficiency with UNKNOWN/ABSENT/STALE preservation."""
    anomalous_findings = [finding for finding in gate_input.findings if finding.is_anomalous]
    if not anomalous_findings:
        return True

    findings_to_check = [finding for finding in anomalous_findings if finding.is_primary]
    if not findings_to_check:
        findings_to_check = anomalous_findings

    for finding in findings_to_check:
        for required_evidence in finding.evidence_required:
            status = gate_input.evidence_status_map.get(required_evidence, EvidenceStatus.UNKNOWN)
            if status == EvidenceStatus.PRESENT:
                continue
            allowed_non_present_statuses = finding.allowed_non_present_statuses_by_evidence.get(
                required_evidence,
                (),
            )
            if status in allowed_non_present_statuses:
                continue
            return False
    return True


def should_apply_source_topic_page_deny(
    *,
    gate_input: GateInputV1,
    rulebook: RulebookV1,
    current_action: Action,
) -> bool:
    """Evaluate AG3 applicability prior to executing always_fail deny check."""
    return (
        gate_input.topic_role in rulebook.caps.paging_denied_topic_roles
        and current_action == Action.PAGE
    )


def resolve_action_mapping(
    *,
    rulebook: RulebookV1,
    mapping_ref: str,
) -> Mapping[str, str]:
    """Resolve known YAML mapping references used by AG1 checks."""
    if mapping_ref == "caps.max_action_by_env":
        return rulebook.caps.max_action_by_env
    if mapping_ref == "caps.max_action_by_tier_in_prod":
        return rulebook.caps.max_action_by_tier_in_prod
    raise ValueError(f"Unsupported mapping reference {mapping_ref!r}")


def env_policy_fallback_keys(env_key: str) -> tuple[str, ...]:
    """Support legacy stage/uat aliases while policy artifacts migrate."""
    if env_key == "uat":
        return ("stage",)
    if env_key == "stage":
        return ("uat",)
    return ()


def lookup_action_policy_entry(
    *,
    mapping: Mapping[str, str],
    key: str,
    context: str,
    fallback_keys: tuple[str, ...] = (),
) -> Action:
    """Resolve an action policy entry with explicit fallback precedence."""
    candidate_keys = (key,) + fallback_keys
    for candidate_key in candidate_keys:
        policy_value = mapping.get(candidate_key)
        if policy_value is None:
            continue
        return action_from_policy_value(
            policy_value,
            context=f"{context}[{candidate_key!r}]",
        )
    raise ValueError(f"Missing policy mapping for {context}[{key!r}]")
