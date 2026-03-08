"""Cold-path LangGraph diagnosis graph and fire-and-forget launcher (Story 6.2)."""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aiops_triage_pipeline.config.settings import AppEnv
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
from aiops_triage_pipeline.contracts.enums import CriticalityTier
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.health.metrics import llm_inflight_add
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.integrations.llm import LLMClient
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.health import HealthStatus

_logger = get_logger("diagnosis.graph")


class ColdPathDiagnosisState(TypedDict):
    case_id: str
    triage_excerpt: TriageExcerptV1
    evidence_summary: str
    diagnosis_report: DiagnosisReportV1 | None


def build_diagnosis_graph(llm_client: LLMClient) -> Any:
    """Build and compile a LangGraph diagnosis graph for the given LLM client.

    Do NOT compile a module-level singleton — compile per invocation to allow
    different client modes in tests without module-level state.
    """

    async def invoke_llm_node(state: ColdPathDiagnosisState) -> dict:
        report = await llm_client.invoke(
            case_id=state["case_id"],
            triage_excerpt=state["triage_excerpt"],
            evidence_summary=state["evidence_summary"],
        )
        return {"diagnosis_report": report}

    graph = StateGraph(ColdPathDiagnosisState)
    graph.add_node("invoke_llm", invoke_llm_node)
    graph.add_edge(START, "invoke_llm")
    graph.add_edge("invoke_llm", END)
    return graph.compile()


def meets_invocation_criteria(triage_excerpt: TriageExcerptV1, app_env: AppEnv) -> bool:
    """Return True only when ALL three criteria hold: PROD + TIER_0 + sustained.

    All other combinations return False. No logging inside this pure predicate.
    """
    return (
        app_env == AppEnv.prod
        and triage_excerpt.criticality_tier == CriticalityTier.TIER_0
        and triage_excerpt.sustained is True
    )


async def run_cold_path_diagnosis(
    *,
    case_id: str,
    triage_excerpt: TriageExcerptV1,
    evidence_summary: str,
    llm_client: LLMClient,
    denylist: DenylistV1,
    health_registry: HealthRegistry,
    timeout_seconds: float = 60.0,
) -> DiagnosisReportV1:
    """Invoke LLM diagnosis with denylist enforcement, health tracking, and timeout.

    Applies exposure denylist to triage_excerpt before sending to LLM (NFR-S8).
    Enforces 60s timeout via asyncio.wait_for at graph.ainvoke level (NFR-P4).
    Updates HealthRegistry "llm" component and in-flight OTLP gauge throughout.
    """
    safe_excerpt_dict = apply_denylist(triage_excerpt.model_dump(mode="json"), denylist)
    safe_excerpt = TriageExcerptV1.model_validate(safe_excerpt_dict)

    _logger.info("cold_path_diagnosis_started", case_id=case_id, timeout_seconds=timeout_seconds)
    await health_registry.update("llm", HealthStatus.HEALTHY, reason="cold_path_invocation_started")
    llm_inflight_add(+1)
    try:
        graph = build_diagnosis_graph(llm_client)
        result = await asyncio.wait_for(
            graph.ainvoke(
                {
                    "case_id": case_id,
                    "triage_excerpt": safe_excerpt,
                    "evidence_summary": evidence_summary,
                    "diagnosis_report": None,
                }
            ),
            timeout=timeout_seconds,
        )
        report = result["diagnosis_report"]
        if report is None:
            raise RuntimeError(
                f"LangGraph node did not populate diagnosis_report for case {case_id}"
            )
        await health_registry.update("llm", HealthStatus.HEALTHY)
        _logger.info("cold_path_diagnosis_completed", case_id=case_id)
        return report
    except BaseException as exc:
        await health_registry.update(
            "llm", HealthStatus.DEGRADED, reason="cold_path_invocation_failed"
        )
        _logger.warning(
            "cold_path_diagnosis_failed", case_id=case_id, error_type=type(exc).__name__
        )
        raise
    finally:
        llm_inflight_add(-1)


def spawn_cold_path_diagnosis_task(
    *,
    case_id: str,
    triage_excerpt: TriageExcerptV1,
    evidence_summary: str,
    llm_client: LLMClient,
    denylist: DenylistV1,
    health_registry: HealthRegistry,
    app_env: AppEnv,
    timeout_seconds: float = 60.0,
) -> "asyncio.Task[DiagnosisReportV1] | None":
    """Spawn a fire-and-forget cold-path diagnosis task if the case is eligible.

    Returns None if the case does not meet invocation criteria (non-PROD, non-TIER_0,
    or not sustained). Returns asyncio.Task without awaiting — hot-path continues
    immediately while the task runs in the background event loop.
    """
    if not meets_invocation_criteria(triage_excerpt, app_env):
        return None
    _logger.info(
        "cold_path_diagnosis_task_spawned",
        case_id=case_id,
        env=triage_excerpt.env.value,
        tier=triage_excerpt.criticality_tier.value,
        timeout_seconds=timeout_seconds,
    )
    return asyncio.create_task(
        run_cold_path_diagnosis(
            case_id=case_id,
            triage_excerpt=triage_excerpt,
            evidence_summary=evidence_summary,
            llm_client=llm_client,
            denylist=denylist,
            health_registry=health_registry,
            timeout_seconds=timeout_seconds,
        )
    )
