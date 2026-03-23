"""ATDD red-phase acceptance tests for Story 3.3 LLM invocation and prompt enrichment."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiops_triage_pipeline import __main__
from aiops_triage_pipeline.config.settings import AppEnv, IntegrationMode
from aiops_triage_pipeline.diagnosis.graph import (
    meets_invocation_criteria,
    spawn_cold_path_diagnosis_task,
)
from aiops_triage_pipeline.diagnosis.prompt import build_llm_prompt
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.integrations.llm import LLMClient
from tests.atdd.fixtures.story_3_3_test_data import build_case_header_event, build_triage_excerpt


def test_p0_meets_invocation_criteria_allows_non_prod_tier1_unsustained_cases() -> None:
    """Story 3.3 FR39: all cold-path cases must invoke diagnosis regardless of old criteria."""
    excerpt = build_triage_excerpt()

    assert meets_invocation_criteria(excerpt, AppEnv.local) is True


def test_p0_spawn_task_invokes_for_non_prod_non_tier0_and_non_sustained_case() -> None:
    """Story 3.3 FR39: launcher should return a task for non-prod/TIER_1/sustained=False."""
    excerpt = build_triage_excerpt()
    task = spawn_cold_path_diagnosis_task(
        case_id=excerpt.case_id,
        triage_excerpt=excerpt,
        evidence_summary="summary",
        llm_client=LLMClient(mode=IntegrationMode.MOCK),
        denylist=MagicMock(),
        health_registry=HealthRegistry(),
        object_store_client=MagicMock(),
        triage_hash="a" * 64,
        app_env=AppEnv.local,
    )

    assert isinstance(task, asyncio.Task)

    if task is not None:
        task.cancel()


def test_p0_prompt_contains_full_finding_fields_and_routing_context() -> None:
    """Story 3.3 FR40: prompt must include full finding semantics + routing/topology context."""
    excerpt = build_triage_excerpt()
    prompt = build_llm_prompt(excerpt, "evidence summary")

    assert "finding_id" in prompt
    assert "severity" in prompt
    assert "reason_codes" in prompt
    assert "evidence_required" in prompt
    assert "is_primary" in prompt
    assert "topic_role" in prompt
    assert "routing_key" in prompt


def test_p1_prompt_contains_confidence_guidance_and_few_shot_example_block() -> None:
    """Story 3.3 FR40: prompt should include confidence calibration and deterministic few-shot."""
    prompt = build_llm_prompt(build_triage_excerpt(), "evidence summary")
    lower_prompt = prompt.lower()

    assert "confidence calibration" in lower_prompt
    assert "few-shot" in lower_prompt
    assert "fault-domain" in lower_prompt or "fault domain" in lower_prompt


def test_p1_process_event_invokes_diagnosis_path_for_every_case(monkeypatch) -> None:
    """Story 3.3 wiring: process_event must call diagnosis path after context + summary build."""
    event = build_case_header_event()
    logger = MagicMock()
    object_store_client = MagicMock()

    monkeypatch.setattr(
        __main__,
        "retrieve_case_context_with_hash",
        lambda **_: SimpleNamespace(excerpt=build_triage_excerpt(), triage_hash="a" * 64),
    )
    monkeypatch.setattr(__main__, "build_evidence_summary", lambda _: "evidence summary")
    run_probe = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(__main__, "run_cold_path_diagnosis", run_probe, raising=False)

    __main__._cold_path_process_event(
        event,
        logger,
        object_store_client=object_store_client,
    )

    assert run_probe.call_count == 1
