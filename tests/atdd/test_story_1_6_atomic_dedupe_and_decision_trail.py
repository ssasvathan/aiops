"""ATDD acceptance tests for Story 1.6 AG4-AG6 + atomic AG5 dedupe behavior."""

from __future__ import annotations

from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.pipeline.stages.gating import evaluate_rulebook_gates
from aiops_triage_pipeline.pipeline.stages.peak import load_rulebook_policy
from tests.atdd.fixtures.story_1_6_test_data import build_gate_input


class _AtomicOnlyDedupeStore:
    """Store used to assert AG5 does not call a separate pre-read lookup."""

    def __init__(self) -> None:
        self.remember_calls: list[tuple[str, Action]] = []

    def is_duplicate(self, fingerprint: str) -> bool:  # noqa: ARG002
        raise AssertionError("Story 1.6 requires AG5 to avoid read-then-write dedupe lookups")

    def remember(self, fingerprint: str, action: Action) -> bool:
        self.remember_calls.append((fingerprint, action))
        return False


class _AtomicClaimFalseDedupeStore:
    """Store that reports duplicate using single atomic NX claim outcome."""

    def __init__(self) -> None:
        self.remember_calls: list[tuple[str, Action]] = []

    def is_duplicate(self, fingerprint: str) -> bool:  # noqa: ARG002
        return False

    def remember(self, fingerprint: str, action: Action) -> bool:
        self.remember_calls.append((fingerprint, action))
        return False


def test_p0_ag5_uses_single_atomic_claim_without_prelookup() -> None:
    """Given AG5 executes, it must use one atomic claim as authoritative dedupe check."""
    dedupe_store = _AtomicOnlyDedupeStore()
    decision = evaluate_rulebook_gates(
        gate_input=build_gate_input(),
        rulebook=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert dedupe_store.remember_calls == [(decision.action_fingerprint, Action.PAGE)]
    assert decision.final_action == Action.OBSERVE
    assert "AG5_DUPLICATE_SUPPRESSED" in decision.gate_reason_codes


def test_p0_ag5_false_atomic_claim_suppresses_action_as_duplicate() -> None:
    """Given atomic claim returns False, AG5 should treat fingerprint as duplicate."""
    dedupe_store = _AtomicClaimFalseDedupeStore()
    decision = evaluate_rulebook_gates(
        gate_input=build_gate_input(),
        rulebook=load_rulebook_policy(),
        dedupe_store=dedupe_store,
    )

    assert dedupe_store.remember_calls == [(decision.action_fingerprint, Action.PAGE)]
    assert decision.final_action == Action.OBSERVE
    assert "AG5_DUPLICATE_SUPPRESSED" in decision.gate_reason_codes
    assert "AG5_DEDUPE_STORE_ERROR" not in decision.gate_reason_codes


def test_p1_actiondecisionv1_retains_complete_gate_trail_on_atomic_duplicate() -> None:
    """Given AG5 suppresses duplicate, ActionDecisionV1 should retain full AG0..AG6 trail."""
    decision = evaluate_rulebook_gates(
        gate_input=build_gate_input(),
        rulebook=load_rulebook_policy(),
        dedupe_store=_AtomicClaimFalseDedupeStore(),
    )

    assert decision.gate_rule_ids == ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
    assert decision.final_action == Action.OBSERVE
    assert "AG5_DUPLICATE_SUPPRESSED" in decision.gate_reason_codes
    assert decision.postmortem_required is True
    assert decision.postmortem_mode == "SOFT"
