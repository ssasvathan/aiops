"""ATDD red-phase acceptance tests for Story 3.4 diagnosis persistence guarantees."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pydantic

from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
from aiops_triage_pipeline.diagnosis.graph import run_cold_path_diagnosis
from aiops_triage_pipeline.integrations.llm import LLMClient
from tests.atdd.fixtures.story_3_4_test_data import (
    build_empty_denylist,
    build_health_registry,
    build_object_store_client,
    build_triage_excerpt,
)

_FAKE_TRIAGE_HASH = "b" * 64


def _find_log_call(mock_fn: MagicMock, event_name: str):
    for call in mock_fn.call_args_list:
        if call.args and call.args[0] == event_name:
            return call
    raise AssertionError(f"Expected log event {event_name!r} was not emitted")


def _make_validation_error() -> pydantic.ValidationError:
    try:
        DiagnosisReportV1.model_validate({})
    except pydantic.ValidationError as error:
        return error
    raise AssertionError("Expected DiagnosisReportV1.model_validate({}) to raise ValidationError")


async def _raise_wait_for_timeout(awaitable: object, *, timeout: float) -> object:
    del timeout
    if hasattr(awaitable, "close"):
        awaitable.close()
    raise asyncio.TimeoutError


async def _raise_wait_for_connect_error(awaitable: object, *, timeout: float) -> object:
    del timeout
    if hasattr(awaitable, "close"):
        awaitable.close()
    request = httpx.Request("POST", "http://llm-base-url/diagnose")
    raise httpx.ConnectError("connection refused", request=request)


async def _raise_wait_for_validation_error(awaitable: object, *, timeout: float) -> object:
    del timeout
    if hasattr(awaitable, "close"):
        awaitable.close()
    raise _make_validation_error()


def test_p0_success_persistence_log_includes_diagnosis_hash_for_case_correlation() -> None:
    """AC1: success persistence logs include diagnosis hash for full correlation context."""
    logger = MagicMock()

    with patch("aiops_triage_pipeline.diagnosis.graph._logger", logger):
        asyncio.run(
            run_cold_path_diagnosis(
                case_id="case-3-4-success-log",
                triage_excerpt=build_triage_excerpt("case-3-4-success-log"),
                evidence_summary="deterministic evidence summary",
                llm_client=LLMClient(mode=IntegrationMode.MOCK),
                denylist=build_empty_denylist(),
                health_registry=build_health_registry(),
                object_store_client=build_object_store_client(),
                triage_hash=_FAKE_TRIAGE_HASH,
            )
        )

    persist_call = _find_log_call(logger.info, "cold_path_diagnosis_json_written")
    assert persist_call.kwargs["case_id"] == "case-3-4-success-log"
    assert persist_call.kwargs["triage_hash"] == _FAKE_TRIAGE_HASH
    assert "diagnosis_hash" in persist_call.kwargs


def test_p0_timeout_fallback_marks_primary_diagnosis_absence_explicitly() -> None:
    """AC2: timeout fallback report should explicitly mark that primary diagnosis is absent."""
    with patch(
        "aiops_triage_pipeline.diagnosis.graph.asyncio.wait_for",
        side_effect=_raise_wait_for_timeout,
    ):
        report = asyncio.run(
            run_cold_path_diagnosis(
                case_id="case-3-4-timeout",
                triage_excerpt=build_triage_excerpt("case-3-4-timeout"),
                evidence_summary="deterministic evidence summary",
                llm_client=LLMClient(mode=IntegrationMode.MOCK),
                denylist=build_empty_denylist(),
                health_registry=build_health_registry(),
                object_store_client=build_object_store_client(),
                triage_hash=_FAKE_TRIAGE_HASH,
            )
        )

    assert report.reason_codes == ("LLM_TIMEOUT",)
    assert "PRIMARY_DIAGNOSIS_ABSENT" in report.gaps


def test_p0_transport_failure_fallback_marks_primary_diagnosis_absence_explicitly() -> None:
    """AC2: transport-unavailable fallback marks primary diagnosis absence explicitly."""
    with patch(
        "aiops_triage_pipeline.diagnosis.graph.asyncio.wait_for",
        side_effect=_raise_wait_for_connect_error,
    ):
        report = asyncio.run(
            run_cold_path_diagnosis(
                case_id="case-3-4-unavailable",
                triage_excerpt=build_triage_excerpt("case-3-4-unavailable"),
                evidence_summary="deterministic evidence summary",
                llm_client=LLMClient(mode=IntegrationMode.MOCK),
                denylist=build_empty_denylist(),
                health_registry=build_health_registry(),
                object_store_client=build_object_store_client(),
                triage_hash=_FAKE_TRIAGE_HASH,
            )
        )

    assert report.reason_codes == ("LLM_UNAVAILABLE",)
    assert "PRIMARY_DIAGNOSIS_ABSENT" in report.gaps


def test_p0_schema_invalid_fallback_marks_primary_diagnosis_absence_explicitly() -> None:
    """AC2: schema-invalid fallback should use a stable primary diagnosis absence marker."""
    with patch(
        "aiops_triage_pipeline.diagnosis.graph.asyncio.wait_for",
        side_effect=_raise_wait_for_validation_error,
    ):
        report = asyncio.run(
            run_cold_path_diagnosis(
                case_id="case-3-4-schema-invalid",
                triage_excerpt=build_triage_excerpt("case-3-4-schema-invalid"),
                evidence_summary="deterministic evidence summary",
                llm_client=LLMClient(mode=IntegrationMode.MOCK),
                denylist=build_empty_denylist(),
                health_registry=build_health_registry(),
                object_store_client=build_object_store_client(),
                triage_hash=_FAKE_TRIAGE_HASH,
            )
        )

    assert report.reason_codes == ("LLM_SCHEMA_INVALID",)
    assert "PRIMARY_DIAGNOSIS_ABSENT" in report.gaps


def test_p1_fallback_persistence_log_has_primary_absence_observability_flag() -> None:
    """AC2: fallback persistence log should carry explicit primary-diagnosis absence flag."""
    logger = MagicMock()
    with patch("aiops_triage_pipeline.diagnosis.graph._logger", logger), patch(
        "aiops_triage_pipeline.diagnosis.graph.asyncio.wait_for",
        side_effect=_raise_wait_for_timeout,
    ):
        asyncio.run(
            run_cold_path_diagnosis(
                case_id="case-3-4-fallback-log",
                triage_excerpt=build_triage_excerpt("case-3-4-fallback-log"),
                evidence_summary="deterministic evidence summary",
                llm_client=LLMClient(mode=IntegrationMode.MOCK),
                denylist=build_empty_denylist(),
                health_registry=build_health_registry(),
                object_store_client=build_object_store_client(),
                triage_hash=_FAKE_TRIAGE_HASH,
            )
        )

    fallback_call = _find_log_call(logger.info, "cold_path_fallback_diagnosis_json_written")
    assert fallback_call.kwargs["case_id"] == "case-3-4-fallback-log"
    assert fallback_call.kwargs["reason_codes"] == ("LLM_TIMEOUT",)
    assert fallback_call.kwargs.get("primary_diagnosis_absent") is True
