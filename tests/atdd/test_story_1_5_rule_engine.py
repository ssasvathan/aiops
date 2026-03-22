"""ATDD acceptance tests for Story 1.5 isolated rule engine."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.pipeline.stages.peak import load_rulebook_policy
from aiops_triage_pipeline.rule_engine.protocol import UnknownCheckTypeStartupError
from tests.atdd.fixtures.story_1_5_test_data import (
    build_gate_input,
    build_rulebook_with_unknown_ag0_check_type,
    build_stage_alias_only_rulebook,
)


def _load_rule_engine_module() -> Any:
    try:
        return importlib.import_module("aiops_triage_pipeline.rule_engine")
    except ModuleNotFoundError:
        pytest.fail(
            "Story 1.5 RED phase: isolated package `aiops_triage_pipeline.rule_engine` "
            "does not exist yet."
        )


def _load_rule_engine_api() -> tuple[Any, Any]:
    module = _load_rule_engine_module()
    evaluate_gates = getattr(module, "evaluate_gates", None)
    validate_handlers = getattr(module, "validate_rulebook_handlers", None)

    if not callable(evaluate_gates):
        pytest.fail("Story 1.5: `rule_engine.evaluate_gates` is missing.")
    if not callable(validate_handlers):
        pytest.fail("Story 1.5: `rule_engine.validate_rulebook_handlers` is missing.")

    return evaluate_gates, validate_handlers


def test_p0_rule_engine_public_api_is_exposed() -> None:
    """Given Story 1.5 scope, when importing rule_engine, then public API is available."""
    module = _load_rule_engine_module()

    assert callable(getattr(module, "evaluate_gates", None))


def test_p0_startup_validation_fails_fast_for_unknown_check_type() -> None:
    """Given unknown YAML check type, startup validation must fail before runtime eval."""
    _, validate_handlers = _load_rule_engine_api()
    invalid_rulebook = build_rulebook_with_unknown_ag0_check_type()

    with pytest.raises(UnknownCheckTypeStartupError, match="handler_type_not_registered"):
        validate_handlers(invalid_rulebook)


def test_p0_ag0_ag3_path_produces_deterministic_source_topic_deny_outcome() -> None:
    """Given source-topic PAGE input, AG0-AG3 path caps to TICKET with stable reason code."""
    evaluate_gates, validate_handlers = _load_rule_engine_api()
    rulebook = load_rulebook_policy()
    validate_handlers(rulebook)

    decision = evaluate_gates(
        gate_input=build_gate_input(topic_role="SOURCE_TOPIC", proposed_action=Action.PAGE),
        rulebook=rulebook,
        initial_action=Action.PAGE,
    )

    assert decision.current_action == Action.TICKET
    assert decision.gate_reason_codes == ("AG3_PAGING_DENIED_SOURCE_TOPIC",)


def test_p1_ag1_never_escalates_with_stage_alias_fallback_and_safety_invariant() -> None:
    """Given UAT with legacy stage alias, AG1 cap remains monotonic and never pages."""
    evaluate_gates, validate_handlers = _load_rule_engine_api()
    stage_alias_rulebook = build_stage_alias_only_rulebook()
    validate_handlers(stage_alias_rulebook)

    decision = evaluate_gates(
        gate_input=build_gate_input(
            env=Environment.UAT,
            tier=CriticalityTier.TIER_0,
            proposed_action=Action.PAGE,
        ),
        rulebook=stage_alias_rulebook,
        initial_action=Action.PAGE,
    )

    assert decision.current_action == Action.TICKET
    assert decision.env_cap_applied is True
    assert "AG1_ENV_OR_TIER_CAP" in decision.gate_reason_codes


def test_p1_ag2_unknown_evidence_short_circuits_before_ag3_page_deny() -> None:
    """Given UNKNOWN required evidence, AG2 caps to NOTIFY and AG3 deny reason is absent."""
    evaluate_gates, validate_handlers = _load_rule_engine_api()
    rulebook = load_rulebook_policy()
    validate_handlers(rulebook)

    decision = evaluate_gates(
        gate_input=build_gate_input(
            topic_role="SOURCE_TOPIC",
            proposed_action=Action.PAGE,
            evidence_status=EvidenceStatus.UNKNOWN,
        ),
        rulebook=rulebook,
        initial_action=Action.PAGE,
    )

    assert decision.current_action == Action.NOTIFY
    assert "AG2_INSUFFICIENT_EVIDENCE" in decision.gate_reason_codes
    assert "AG3_PAGING_DENIED_SOURCE_TOPIC" not in decision.gate_reason_codes
