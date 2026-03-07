"""Unit tests for integrations/llm.py — LLMClient stub and failure-injection mode coverage."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
from aiops_triage_pipeline.contracts.enums import CriticalityTier, DiagnosisConfidence, Environment
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.integrations.llm import LLMClient, LLMFailureMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CASE_ID = "case-test-001"
_EVIDENCE_SUMMARY = "Consumer lag elevated: 45000 messages behind."


def _make_excerpt(case_id: str = _CASE_ID) -> TriageExcerptV1:
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.LOCAL,
        cluster_id="cluster-a",
        stream_id="stream-x",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_1,
        routing_key="OWN::Streaming::Payments",
        sustained=True,
        evidence_status_map={},
        findings=(),
        triage_timestamp=datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_client(
    mode: IntegrationMode = IntegrationMode.MOCK,
    failure_mode: LLMFailureMode = LLMFailureMode.NONE,
) -> LLMClient:
    return LLMClient(mode=mode, failure_mode=failure_mode)


# ---------------------------------------------------------------------------
# Stub (MOCK + NONE)
# ---------------------------------------------------------------------------


async def test_mock_none_returns_stub_report() -> None:
    """MOCK + NONE returns DiagnosisReportV1 with LLM_STUB reason_code."""
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.NONE)
    report = await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)

    assert isinstance(report, DiagnosisReportV1)
    assert report.schema_version == "v1"
    assert report.reason_codes == ("LLM_STUB",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW
    assert report.case_id == _CASE_ID


# ---------------------------------------------------------------------------
# Failure injection
# ---------------------------------------------------------------------------


async def test_mock_timeout_returns_timeout_reason_code() -> None:
    """MOCK + TIMEOUT returns reason_codes=('LLM_TIMEOUT',)."""
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.TIMEOUT)
    report = await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)

    assert report.reason_codes == ("LLM_TIMEOUT",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW


async def test_mock_unavailable_returns_unavailable_reason_code() -> None:
    """MOCK + UNAVAILABLE returns reason_codes=('LLM_UNAVAILABLE',)."""
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.UNAVAILABLE)
    report = await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)

    assert report.reason_codes == ("LLM_UNAVAILABLE",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW


async def test_mock_malformed_returns_schema_invalid_reason_code() -> None:
    """MOCK + MALFORMED returns reason_codes=('LLM_SCHEMA_INVALID',)."""
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.MALFORMED)
    report = await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)

    assert report.reason_codes == ("LLM_SCHEMA_INVALID",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW


async def test_mock_error_returns_error_reason_code() -> None:
    """MOCK + ERROR returns reason_codes=('LLM_ERROR',)."""
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.ERROR)
    report = await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)

    assert report.reason_codes == ("LLM_ERROR",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW


# ---------------------------------------------------------------------------
# LOG mode
# ---------------------------------------------------------------------------


async def test_log_mode_returns_stub_report() -> None:
    """LOG mode returns same stub DiagnosisReport as MOCK+NONE."""
    client = _make_client(IntegrationMode.LOG, LLMFailureMode.NONE)
    report = await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)

    assert report.reason_codes == ("LLM_STUB",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW
    assert report.case_id == _CASE_ID


# ---------------------------------------------------------------------------
# OFF and LIVE mode error paths
# ---------------------------------------------------------------------------


async def test_off_mode_raises_value_error() -> None:
    """OFF mode raises ValueError — not a valid LLM operation mode."""
    client = _make_client(IntegrationMode.OFF)

    with pytest.raises(ValueError, match="INTEGRATION_MODE_LLM=OFF"):
        await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)


async def test_live_mode_raises_not_implemented() -> None:
    """LIVE mode raises NotImplementedError until Story 6.2."""
    client = _make_client(IntegrationMode.LIVE)

    with pytest.raises(NotImplementedError, match="Story 6.2"):
        await client.invoke(_CASE_ID, _make_excerpt(), _EVIDENCE_SUMMARY)


# ---------------------------------------------------------------------------
# case_id propagation
# ---------------------------------------------------------------------------


async def test_case_id_propagated_in_mock_mode() -> None:
    """case_id is propagated to report.case_id in MOCK mode."""
    specific_case_id = "case-propagation-test"
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.NONE)
    report = await client.invoke(
        specific_case_id, _make_excerpt(specific_case_id), _EVIDENCE_SUMMARY
    )

    assert report.case_id == specific_case_id


async def test_case_id_propagated_in_log_mode() -> None:
    """case_id is propagated to report.case_id in LOG mode."""
    specific_case_id = "case-log-propagation"
    client = _make_client(IntegrationMode.LOG, LLMFailureMode.NONE)
    report = await client.invoke(
        specific_case_id, _make_excerpt(specific_case_id), _EVIDENCE_SUMMARY
    )

    assert report.case_id == specific_case_id


async def test_case_id_propagated_in_timeout_mode() -> None:
    """case_id is propagated to report.case_id in TIMEOUT failure mode."""
    specific_case_id = "case-failure-timeout"
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.TIMEOUT)
    report = await client.invoke(
        specific_case_id, _make_excerpt(specific_case_id), _EVIDENCE_SUMMARY
    )
    assert report.case_id == specific_case_id


async def test_case_id_propagated_in_unavailable_mode() -> None:
    """case_id is propagated to report.case_id in UNAVAILABLE failure mode."""
    specific_case_id = "case-failure-unavailable"
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.UNAVAILABLE)
    report = await client.invoke(
        specific_case_id, _make_excerpt(specific_case_id), _EVIDENCE_SUMMARY
    )
    assert report.case_id == specific_case_id


async def test_case_id_propagated_in_malformed_mode() -> None:
    """case_id is propagated to report.case_id in MALFORMED failure mode."""
    specific_case_id = "case-failure-malformed"
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.MALFORMED)
    report = await client.invoke(
        specific_case_id, _make_excerpt(specific_case_id), _EVIDENCE_SUMMARY
    )
    assert report.case_id == specific_case_id


async def test_case_id_propagated_in_error_mode() -> None:
    """case_id is propagated to report.case_id in ERROR failure mode."""
    specific_case_id = "case-failure-error"
    client = _make_client(IntegrationMode.MOCK, LLMFailureMode.ERROR)
    report = await client.invoke(
        specific_case_id, _make_excerpt(specific_case_id), _EVIDENCE_SUMMARY
    )
    assert report.case_id == specific_case_id


# ---------------------------------------------------------------------------
# No network I/O verification (AC2)
# ---------------------------------------------------------------------------


def test_llm_module_imports_no_http_library() -> None:
    """AC2: integrations/llm.py must not import any HTTP library — no network I/O in stub."""
    import inspect

    import aiops_triage_pipeline.integrations.llm as llm_module

    source = inspect.getsource(llm_module)
    forbidden_imports = [
        "import httpx",
        "import requests",
        "import aiohttp",
        "import urllib.request",
    ]
    for lib in forbidden_imports:
        assert lib not in source, f"Found HTTP import in integrations/llm.py: {lib}"
