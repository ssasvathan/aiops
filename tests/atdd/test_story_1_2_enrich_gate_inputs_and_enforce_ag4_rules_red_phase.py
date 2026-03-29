"""ATDD red-phase acceptance tests for Story 1.2 gate-input enrichment and AG4 rules."""

from __future__ import annotations

import pytest

import aiops_triage_pipeline.pipeline.scheduler as scheduler_module
from aiops_triage_pipeline.contracts.enums import Action, Environment
from aiops_triage_pipeline.pipeline.scheduler import run_gate_input_stage_cycle
from aiops_triage_pipeline.pipeline.stages.gating import (
    collect_gate_inputs_by_scope,
    evaluate_rulebook_gates,
)
from aiops_triage_pipeline.pipeline.stages.peak import load_rulebook_policy
from tests.atdd.fixtures.story_1_2_test_data import (
    build_story_1_2_context,
    build_story_1_2_stage_inputs,
)


class _AllowingDedupeStore:
    def remember(self, fingerprint: str, action: Action) -> bool:  # noqa: ARG002
        return True


def _scoring_basis(*, score: float, reason_code: str) -> dict[str, object]:
    return {
        "score_version": "v1",
        "base_score": score,
        "sustained_boost": 0.0,
        "peak_boost": 0.0,
        "final_score": score,
        "score_reason_code": reason_code,
        "fallback_applied": False,
    }


def test_p0_scheduler_enriches_gate_input_context_before_collect() -> None:
    """AC1: scheduler must enrich GateInputContext confidence/action before collect call."""
    evidence_output, peak_output, scope = build_story_1_2_stage_inputs(
        sustained_value=True,
        is_peak_window=True,
    )
    context_by_scope = {scope: build_story_1_2_context()}

    def _collect_probe(
        *,
        evidence_output,  # noqa: ANN001
        peak_output,  # noqa: ANN001
        context_by_scope,  # noqa: ANN001
        max_safe_action,  # noqa: ANN001
    ) -> dict[tuple[str, ...], tuple[object, ...]]:
        context = context_by_scope[scope]
        assert context.diagnosis_confidence > 0.0, (
            "Story 1.2 RED phase: expected scheduler to enrich diagnosis_confidence "
            "before collect_gate_inputs_by_scope."
        )
        assert context.proposed_action in {Action.TICKET, Action.PAGE}, (
            "Story 1.2 RED phase: expected scheduler to enrich proposed_action "
            "before collect_gate_inputs_by_scope."
        )
        return {scope: ()}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(scheduler_module, "collect_gate_inputs_by_scope", _collect_probe)
    try:
        _ = run_gate_input_stage_cycle(
            evidence_output=evidence_output,
            peak_output=peak_output,
            context_by_scope=context_by_scope,
        )
    finally:
        monkeypatch.undo()


def test_p0_ag4_caps_low_confidence_ticket_or_page_candidates_to_observe() -> None:
    """AC2: confidence <0.6 must cap TICKET/PAGE to OBSERVE regardless of other positive signals."""
    evidence_output, peak_output, scope = build_story_1_2_stage_inputs(
        sustained_value=True,
        is_peak_window=True,
    )
    gate_input = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: build_story_1_2_context(
                proposed_action=Action.PAGE,
                diagnosis_confidence=0.59,
                decision_basis=_scoring_basis(
                    score=0.59,
                    reason_code="LOW_CONFIDENCE_INSUFFICIENT_EVIDENCE",
                ),
            )
        },
    )[scope][0]

    assert gate_input.diagnosis_confidence == pytest.approx(0.59)
    assert gate_input.proposed_action == Action.PAGE

    decision = evaluate_rulebook_gates(
        gate_input=gate_input,
        rulebook=load_rulebook_policy(),
        dedupe_store=_AllowingDedupeStore(),
    )
    assert decision.final_action == Action.OBSERVE
    assert "LOW_CONFIDENCE" in decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in decision.gate_reason_codes


def test_p0_ag4_allows_boundary_confidence_when_sustained_and_caps_still_apply() -> None:
    """AC3: confidence 0.6 + sustained=True allows progression; env caps remain final authority."""
    evidence_output, peak_output, scope = build_story_1_2_stage_inputs(
        sustained_value=True,
        is_peak_window=True,
    )
    gate_input = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: build_story_1_2_context(
                proposed_action=Action.PAGE,
                diagnosis_confidence=0.60,
                decision_basis=_scoring_basis(
                    score=0.60,
                    reason_code="MEDIUM_CONFIDENCE_BASELINE",
                ),
            )
        },
    )[scope][0]

    assert gate_input.diagnosis_confidence == pytest.approx(0.60)
    assert gate_input.proposed_action == Action.PAGE

    prod_decision = evaluate_rulebook_gates(
        gate_input=gate_input,
        rulebook=load_rulebook_policy(),
        dedupe_store=_AllowingDedupeStore(),
    )
    assert prod_decision.final_action == Action.PAGE
    assert "LOW_CONFIDENCE" not in prod_decision.gate_reason_codes
    assert "NOT_SUSTAINED" not in prod_decision.gate_reason_codes

    dev_decision = evaluate_rulebook_gates(
        gate_input=gate_input.model_copy(update={"env": Environment.DEV}),
        rulebook=load_rulebook_policy(),
        dedupe_store=_AllowingDedupeStore(),
    )
    assert dev_decision.final_action == Action.NOTIFY
    assert "AG1_ENV_OR_TIER_CAP" in dev_decision.gate_reason_codes


def test_p1_ag4_suppresses_not_sustained_even_when_confidence_meets_floor() -> None:
    """AC4: confidence >=0.6 with sustained=False must suppress TICKET/PAGE to OBSERVE."""
    evidence_output, peak_output, scope = build_story_1_2_stage_inputs(
        sustained_value=False,
        is_peak_window=True,
    )
    gate_input = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: build_story_1_2_context(
                proposed_action=Action.PAGE,
                diagnosis_confidence=0.60,
                decision_basis=_scoring_basis(
                    score=0.60,
                    reason_code="MEDIUM_CONFIDENCE_BASELINE",
                ),
            )
        },
    )[scope][0]

    assert gate_input.diagnosis_confidence == pytest.approx(0.60)
    assert gate_input.proposed_action == Action.PAGE
    assert gate_input.sustained is False

    decision = evaluate_rulebook_gates(
        gate_input=gate_input,
        rulebook=load_rulebook_policy(),
        dedupe_store=_AllowingDedupeStore(),
    )
    assert decision.final_action == Action.OBSERVE
    assert "NOT_SUSTAINED" in decision.gate_reason_codes
    assert "LOW_CONFIDENCE" not in decision.gate_reason_codes
