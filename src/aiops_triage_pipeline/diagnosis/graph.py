"""Cold-path LangGraph diagnosis graph and fire-and-forget launcher (Stories 6.2, 6.3).

Story 6.3 additions: structured prompt construction via diagnosis/prompt.py, triage_hash
hash chain injection, diagnosis.json write-once persistence after successful LLM response.
Story 6.4 additions: targeted exception handling per failure scenario (timeout,
schema-invalid, unavailable, error), fallback DiagnosisReport written to
diagnosis.json for all failure paths.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict

import httpx
import pydantic
from langgraph.graph import END, START, StateGraph

from aiops_triage_pipeline.config.settings import AppEnv
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
from aiops_triage_pipeline.contracts.enums import CriticalityTier
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.diagnosis.fallback import build_fallback_report
from aiops_triage_pipeline.diagnosis.prompt import build_llm_prompt
from aiops_triage_pipeline.health.metrics import llm_inflight_add
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.integrations.llm import LLMClient
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.case_file import DIAGNOSIS_HASH_PLACEHOLDER, CaseFileDiagnosisV1
from aiops_triage_pipeline.models.health import HealthStatus
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_diagnosis_hash,
    persist_casefile_diagnosis_write_once,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol

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
        built_prompt = build_llm_prompt(state["triage_excerpt"], state["evidence_summary"])
        report = await llm_client.invoke(
            case_id=state["case_id"],
            triage_excerpt=state["triage_excerpt"],
            evidence_summary=state["evidence_summary"],
            prompt=built_prompt,
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


def _make_and_persist_fallback(
    *,
    reason_codes: tuple[str, ...],
    case_id: str,
    triage_hash: str,
    object_store_client: ObjectStoreClientProtocol,
    gaps: tuple[str, ...] = (),
) -> DiagnosisReportV1:
    """Build fallback DiagnosisReportV1, inject triage_hash/gaps, and persist diagnosis.json."""
    raw = build_fallback_report(reason_codes=reason_codes, case_id=case_id)
    report = DiagnosisReportV1.model_validate(
        {
            **raw.model_dump(mode="json"),
            "triage_hash": triage_hash,
            "case_id": case_id,
            "gaps": list(gaps),
        }
    )

    casefile_placeholder = CaseFileDiagnosisV1(
        case_id=case_id,
        diagnosis_report=report,
        triage_hash=triage_hash,
        diagnosis_hash=DIAGNOSIS_HASH_PLACEHOLDER,
    )
    computed_hash = compute_casefile_diagnosis_hash(casefile_placeholder)
    casefile = CaseFileDiagnosisV1(
        case_id=case_id,
        diagnosis_report=report,
        triage_hash=triage_hash,
        diagnosis_hash=computed_hash,
    )
    persist_casefile_diagnosis_write_once(
        object_store_client=object_store_client,
        casefile=casefile,
    )
    _logger.info(
        "cold_path_fallback_diagnosis_json_written",
        case_id=case_id,
        reason_codes=reason_codes,
    )
    return report


async def run_cold_path_diagnosis(
    *,
    case_id: str,
    triage_excerpt: TriageExcerptV1,
    evidence_summary: str,
    llm_client: LLMClient,
    denylist: DenylistV1,
    health_registry: HealthRegistry,
    object_store_client: ObjectStoreClientProtocol,
    triage_hash: str,
    timeout_seconds: float = 60.0,
) -> DiagnosisReportV1:
    """Invoke LLM diagnosis with denylist enforcement, health tracking, and timeout.

    Applies exposure denylist to triage_excerpt before sending to LLM (NFR-S8).
    Enforces 60s timeout via asyncio.wait_for at graph.ainvoke level (NFR-P4).
    Updates HealthRegistry "llm" component and in-flight OTLP gauge throughout.
    Writes diagnosis.json to object storage after successful LLM response (Story 6.3).
    """
    safe_excerpt_dict = apply_denylist(triage_excerpt.model_dump(mode="json"), denylist)
    safe_excerpt = TriageExcerptV1.model_validate(safe_excerpt_dict)

    _logger.info("cold_path_diagnosis_started", case_id=case_id, timeout_seconds=timeout_seconds)
    await health_registry.update("llm", HealthStatus.HEALTHY, reason="cold_path_invocation_started")
    llm_inflight_add(+1)
    try:
        graph = build_diagnosis_graph(llm_client)
        try:
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
        except asyncio.TimeoutError:
            await health_registry.update("llm", HealthStatus.DEGRADED, reason="cold_path_timeout")
            _logger.warning(
                "cold_path_diagnosis_failed",
                case_id=case_id,
                error_type="TimeoutError",
            )
            return _make_and_persist_fallback(
                reason_codes=("LLM_TIMEOUT",),
                case_id=case_id,
                triage_hash=triage_hash,
                object_store_client=object_store_client,
            )
        except pydantic.ValidationError:
            await health_registry.update(
                "llm",
                HealthStatus.DEGRADED,
                reason="cold_path_schema_invalid",
            )
            _logger.warning(
                "cold_path_diagnosis_failed",
                case_id=case_id,
                error_type="ValidationError",
            )
            return _make_and_persist_fallback(
                reason_codes=("LLM_SCHEMA_INVALID",),
                case_id=case_id,
                triage_hash=triage_hash,
                object_store_client=object_store_client,
                gaps=("LLM output failed schema validation",),
            )
        except httpx.TransportError as exc:
            await health_registry.update(
                "llm",
                HealthStatus.DEGRADED,
                reason="cold_path_unavailable",
            )
            _logger.warning(
                "cold_path_diagnosis_failed",
                case_id=case_id,
                error_type=type(exc).__name__,
            )
            return _make_and_persist_fallback(
                reason_codes=("LLM_UNAVAILABLE",),
                case_id=case_id,
                triage_hash=triage_hash,
                object_store_client=object_store_client,
            )
        except Exception as exc:
            await health_registry.update(
                "llm",
                HealthStatus.DEGRADED,
                reason="cold_path_invocation_failed",
            )
            _logger.warning(
                "cold_path_diagnosis_failed",
                case_id=case_id,
                error_type=type(exc).__name__,
            )
            return _make_and_persist_fallback(
                reason_codes=("LLM_ERROR",),
                case_id=case_id,
                triage_hash=triage_hash,
                object_store_client=object_store_client,
            )

        try:
            raw_report = result["diagnosis_report"]
            if raw_report is None:
                raise RuntimeError(
                    f"LangGraph node did not populate diagnosis_report for case {case_id}"
                )

            # Validate LLM output shape first; only this branch maps to LLM_SCHEMA_INVALID.
            validated_llm_report = DiagnosisReportV1.model_validate(raw_report)
        except pydantic.ValidationError:
            await health_registry.update(
                "llm",
                HealthStatus.DEGRADED,
                reason="cold_path_schema_invalid",
            )
            _logger.warning(
                "cold_path_diagnosis_failed",
                case_id=case_id,
                error_type="ValidationError",
            )
            return _make_and_persist_fallback(
                reason_codes=("LLM_SCHEMA_INVALID",),
                case_id=case_id,
                triage_hash=triage_hash,
                object_store_client=object_store_client,
                gaps=("LLM output failed schema validation",),
            )
        except Exception as exc:
            await health_registry.update(
                "llm",
                HealthStatus.DEGRADED,
                reason="cold_path_invocation_failed",
            )
            _logger.warning(
                "cold_path_diagnosis_failed",
                case_id=case_id,
                error_type=type(exc).__name__,
            )
            return _make_and_persist_fallback(
                reason_codes=("LLM_ERROR",),
                case_id=case_id,
                triage_hash=triage_hash,
                object_store_client=object_store_client,
            )

        # Reconstruct with triage_hash for hash chain (AC5)
        try:
            report = DiagnosisReportV1.model_validate(
                {
                    **validated_llm_report.model_dump(mode="json"),
                    "triage_hash": triage_hash,
                    "case_id": case_id,
                }
            )

            # Write diagnosis.json (AC4)
            casefile_placeholder = CaseFileDiagnosisV1(
                case_id=case_id,
                diagnosis_report=report,
                triage_hash=triage_hash,
                diagnosis_hash=DIAGNOSIS_HASH_PLACEHOLDER,
            )
            computed_hash = compute_casefile_diagnosis_hash(casefile_placeholder)
            casefile = CaseFileDiagnosisV1(
                case_id=case_id,
                diagnosis_report=report,
                triage_hash=triage_hash,
                diagnosis_hash=computed_hash,
            )
            persist_casefile_diagnosis_write_once(
                object_store_client=object_store_client,
                casefile=casefile,
            )
            _logger.info(
                "cold_path_diagnosis_json_written",
                case_id=case_id,
                triage_hash=triage_hash,
            )
        except Exception:
            # Fail loud for non-LLM failures in success path (e.g., persistence/invariant errors).
            await health_registry.update(
                "llm",
                HealthStatus.DEGRADED,
                reason="cold_path_invocation_failed",
            )
            raise

        await health_registry.update("llm", HealthStatus.HEALTHY)
        _logger.info("cold_path_diagnosis_completed", case_id=case_id)
        return report
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
    object_store_client: ObjectStoreClientProtocol,
    triage_hash: str,
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
            object_store_client=object_store_client,
            triage_hash=triage_hash,
            timeout_seconds=timeout_seconds,
        )
    )
