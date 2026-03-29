"""ATDD red-phase acceptance tests for Story 1.1 deterministic confidence scoring core."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

import aiops_triage_pipeline.pipeline.stages.gating as gating
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.pipeline.stages.gating import collect_gate_inputs_by_scope
from tests.atdd.fixtures.story_1_1_test_data import (
    build_story_1_1_context,
    build_story_1_1_stage_inputs,
)


def _locate_private_callable(*, prefix: str, contains: str) -> Callable[..., Any]:
    candidates: list[Callable[..., Any]] = []
    candidate_names: list[str] = []
    for name in sorted(dir(gating)):
        if not name.startswith(prefix):
            continue
        if contains not in name:
            continue
        candidate = getattr(gating, name)
        if callable(candidate):
            candidates.append(candidate)
            candidate_names.append(name)

    if not candidates:
        pytest.fail(
            f"Story 1.1 RED phase: expected private helper with prefix={prefix!r} and "
            f"name containing {contains!r}."
        )
    if len(candidates) > 1:
        pytest.fail(
            "Story 1.1 RED phase: ambiguous private helper lookup for "
            f"prefix={prefix!r}, contains={contains!r}. Matches: {candidate_names!r}"
        )
    return candidates[0]


def test_p0_collect_gate_inputs_computes_deterministic_score_and_action_from_stage_inputs() -> None:
    """AC1: scoring should derive confidence/action from evidence+sustained+peak in stage 6."""
    evidence_output, peak_output, scope = build_story_1_1_stage_inputs(
        sustained_value=True,
        is_peak_window=True,
    )

    gate_inputs_by_scope = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={scope: build_story_1_1_context()},
    )

    gate_input = gate_inputs_by_scope[scope][0]

    assert 0.0 < gate_input.diagnosis_confidence <= 1.0
    assert gate_input.proposed_action in {Action.TICKET, Action.PAGE}
    assert gate_input.decision_basis is not None
    for key in (
        "score_version",
        "base_score",
        "sustained_boost",
        "peak_boost",
        "final_score",
        "score_reason_code",
        "fallback_applied",
    ):
        assert key in gate_input.decision_basis
    assert gate_input.decision_basis["score_version"] == "v1"


def test_p0_action_band_thresholds_map_exactly_to_story_contract() -> None:
    """AC1: enforce action bands: <0.6 OBSERVE, 0.6-<0.85 TICKET, >=0.85 PAGE."""
    derive_action = _locate_private_callable(prefix="_derive_", contains="action")

    assert derive_action(0.59) == Action.OBSERVE
    assert derive_action(0.60) == Action.TICKET
    assert derive_action(0.85) == Action.PAGE


def test_p1_sustained_none_applies_zero_boost_and_output_is_repeatable() -> None:
    """AC2: `is_sustained=None` must not amplify and output must remain deterministic."""
    score_sustained = _locate_private_callable(prefix="_score_", contains="sustained")

    assert score_sustained(False) == pytest.approx(0.0)
    assert score_sustained(None) == pytest.approx(0.0)

    evidence_output, peak_output, scope = build_story_1_1_stage_inputs(
        sustained_value=None,
        is_peak_window=True,
    )
    context = {scope: build_story_1_1_context()}

    first = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope=context,
    )
    second = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope=context,
    )

    assert first == second
    first_gate_input = first[scope][0]
    assert first_gate_input.decision_basis is not None
    assert first_gate_input.decision_basis["sustained_boost"] == pytest.approx(0.0)


def test_p0_scoring_internal_exception_falls_back_to_observe_without_unhandled_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: scoring exceptions must degrade to 0.0/OBSERVE and keep gating flow alive."""
    score_base_name = "_score_base_from_evidence_status_map"
    score_base = getattr(gating, score_base_name, None)
    if not callable(score_base):
        pytest.fail("Story 1.1 RED phase: expected a private `_score_*base*` helper in gating.")

    def _raise_scoring_failure(*args: object, **kwargs: object) -> float:  # noqa: ARG001
        raise RuntimeError("story-1-1-intentional-red-phase-scoring-failure")

    monkeypatch.setattr(gating, score_base_name, _raise_scoring_failure)

    evidence_output, peak_output, scope = build_story_1_1_stage_inputs(
        sustained_value=True,
        is_peak_window=True,
    )

    gate_inputs_by_scope = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: build_story_1_1_context()
        },
    )

    gate_input = gate_inputs_by_scope[scope][0]

    assert gate_input.diagnosis_confidence == pytest.approx(0.0)
    assert gate_input.proposed_action == Action.OBSERVE
    assert gate_input.decision_basis is not None
    assert gate_input.decision_basis["fallback_applied"] is True
