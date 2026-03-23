"""Unit tests for diagnosis/graph.py — LangGraph graph and fire-and-forget launcher."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pydantic
import pytest

from aiops_triage_pipeline.config.settings import AppEnv, IntegrationMode
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import CriticalityTier, DiagnosisConfidence, Environment
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.diagnosis.graph import (
    meets_invocation_criteria,
    run_cold_path_diagnosis,
    spawn_cold_path_diagnosis_task,
)
from aiops_triage_pipeline.health.alerts import (
    OperationalAlertEvaluator,
    load_operational_alert_policy,
)
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.integrations.llm import LLMClient
from aiops_triage_pipeline.models.health import HealthStatus
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EVIDENCE_SUMMARY = "Consumer lag elevated: 45000 messages behind."
_EMPTY_DENYLIST = DenylistV1(denylist_version="test-v1", denied_field_names=())
_FAKE_TRIAGE_HASH = "a" * 64


def _make_mock_store() -> MagicMock:
    """MagicMock object store that returns CREATED on put_if_absent."""
    mock_store = MagicMock(spec=ObjectStoreClientProtocol)
    mock_store.put_if_absent.return_value = PutIfAbsentResult.CREATED
    return mock_store


def _make_eligible_excerpt(case_id: str = "test-001") -> TriageExcerptV1:
    """TriageExcerptV1 that meets all three invocation criteria."""
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-x",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="OWN::Streaming::Payments",
        sustained=True,
        evidence_status_map={},
        findings=(),
        triage_timestamp=datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_mock_client() -> LLMClient:
    return LLMClient(mode=IntegrationMode.MOCK)


def _make_validation_error() -> pydantic.ValidationError:
    try:
        DiagnosisReportV1.model_validate({})
    except pydantic.ValidationError as error:
        return error
    raise AssertionError("Expected DiagnosisReportV1.model_validate({}) to raise ValidationError")


def _make_http_status_error() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://llm-base-url/diagnose")
    response = httpx.Response(500, request=request)
    return httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=request,
        response=response,
    )


def _make_read_timeout_error() -> httpx.ReadTimeout:
    request = httpx.Request("POST", "http://llm-base-url/diagnose")
    return httpx.ReadTimeout("Read timeout", request=request)


# ---------------------------------------------------------------------------
# meets_invocation_criteria
# ---------------------------------------------------------------------------


async def test_meets_invocation_criteria_prod_tier0_sustained_returns_true() -> None:
    """All-case invocation semantics: prod + TIER_0 + sustained=True → True."""
    excerpt = _make_eligible_excerpt()
    assert meets_invocation_criteria(excerpt, AppEnv.prod) is True


async def test_meets_invocation_criteria_local_env_returns_true() -> None:
    """All-case invocation semantics: non-prod (local) still returns True."""
    excerpt = TriageExcerptV1(
        case_id="test-001",
        env=Environment.LOCAL,
        cluster_id="cluster-a",
        stream_id="stream-x",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="OWN::Streaming::Payments",
        sustained=True,
        evidence_status_map={},
        findings=(),
        triage_timestamp=datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert meets_invocation_criteria(excerpt, AppEnv.local) is True


async def test_meets_invocation_criteria_prod_tier1_returns_true() -> None:
    """All-case invocation semantics: prod + TIER_1 still returns True."""
    excerpt = TriageExcerptV1(
        case_id="test-001",
        env=Environment.PROD,
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
    assert meets_invocation_criteria(excerpt, AppEnv.prod) is True


async def test_meets_invocation_criteria_prod_tier0_not_sustained_returns_true() -> None:
    """All-case invocation semantics: sustained=False still returns True."""
    excerpt = TriageExcerptV1(
        case_id="test-001",
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-x",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="OWN::Streaming::Payments",
        sustained=False,
        evidence_status_map={},
        findings=(),
        triage_timestamp=datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert meets_invocation_criteria(excerpt, AppEnv.prod) is True


# ---------------------------------------------------------------------------
# spawn_cold_path_diagnosis_task
# ---------------------------------------------------------------------------


async def test_spawn_local_env_returns_asyncio_task() -> None:
    """All-case invocation semantics: local env still spawns diagnosis task."""
    registry = HealthRegistry()
    task = spawn_cold_path_diagnosis_task(
        case_id="test-001",
        triage_excerpt=_make_eligible_excerpt(),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
        app_env=AppEnv.local,
    )
    assert isinstance(task, asyncio.Task)
    report = await task
    assert report.schema_version == "v1"


async def test_spawn_eligible_returns_asyncio_task() -> None:
    """Eligible case (prod + TIER_0 + sustained) → spawn returns asyncio.Task."""
    registry = HealthRegistry()
    task = spawn_cold_path_diagnosis_task(
        case_id="test-001",
        triage_excerpt=_make_eligible_excerpt(),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
        app_env=AppEnv.prod,
    )
    assert isinstance(task, asyncio.Task)
    # Clean up the task to avoid warnings
    report = await task
    assert report.schema_version == "v1"


async def test_fire_and_forget_independence() -> None:
    """Task is not done immediately after spawn — hot-path continues without waiting."""
    registry = HealthRegistry()
    task = spawn_cold_path_diagnosis_task(
        case_id="test-fire-forget",
        triage_excerpt=_make_eligible_excerpt("test-fire-forget"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
        app_env=AppEnv.prod,
    )
    assert task is not None
    # Hot-path continues without waiting — task not done yet
    assert not task.done()
    # Yield to event loop; task runs to completion
    await asyncio.sleep(0)
    report = await task
    assert report.schema_version == "v1"


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — HealthRegistry tracking
# ---------------------------------------------------------------------------


async def test_health_registry_updated_healthy_on_success() -> None:
    """run_cold_path_diagnosis updates 'llm' component to HEALTHY on success."""
    registry = HealthRegistry()
    report = await run_cold_path_diagnosis(
        case_id="test-health",
        triage_excerpt=_make_eligible_excerpt("test-health"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )
    assert report.schema_version == "v1"
    assert registry.get("llm") == HealthStatus.HEALTHY


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — denylist applied
# ---------------------------------------------------------------------------


async def test_denylist_applied_to_triage_excerpt() -> None:
    """apply_denylist is called on triage_excerpt before passing to LLMClient.invoke().

    apply_denylist is called twice: once for INPUT (triage_excerpt)
    and once for OUTPUT (LLM DiagnosisReportV1 narrative). This test verifies the first
    call receives the triage_excerpt dict.
    """
    registry = HealthRegistry()
    excerpt = _make_eligible_excerpt()
    mock_llm_client = _make_mock_client()

    # Build a minimal valid DiagnosisReportV1 dict to return for the second call
    _stub_report = mock_llm_client  # will use real MOCK client's output below

    with patch(
        "aiops_triage_pipeline.diagnosis.graph.apply_denylist",
    ) as mock_apply:
        # First call: excerpt INPUT sanitization → return excerpt dict
        # Second call: LLM OUTPUT sanitization → return valid DiagnosisReportV1 dict
        excerpt_dict = excerpt.model_dump(mode="json")
        report_dict = {
            "schema_version": "v1",
            "verdict": "UNKNOWN",
            "confidence": "LOW",
            "evidence_pack": {"facts": [], "missing_evidence": [], "matched_rules": []},
            "reason_codes": ["LLM_STUB"],
        }
        mock_apply.side_effect = [excerpt_dict, report_dict]
        await run_cold_path_diagnosis(
            case_id="test-denylist",
            triage_excerpt=excerpt,
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=mock_llm_client,
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash=_FAKE_TRIAGE_HASH,
        )

    assert mock_apply.call_count == 2
    first_call_args = mock_apply.call_args_list[0]
    # First positional arg of first call is the excerpt dict
    assert isinstance(first_call_args[0][0], dict)
    # Second positional arg is the denylist
    assert first_call_args[0][1] is _EMPTY_DENYLIST


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — timeout enforcement
# ---------------------------------------------------------------------------


async def test_timeout_enforced_at_graph_invocation() -> None:
    """asyncio.wait_for is called with timeout=60.0 at graph.ainvoke level."""
    registry = HealthRegistry()

    with patch(
        "aiops_triage_pipeline.diagnosis.graph.asyncio.wait_for",
        wraps=asyncio.wait_for,
    ) as mock_wait_for:
        await run_cold_path_diagnosis(
            case_id="test-timeout",
            triage_excerpt=_make_eligible_excerpt("test-timeout"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=_make_mock_client(),
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash=_FAKE_TRIAGE_HASH,
        )

    mock_wait_for.assert_called_once()
    _, call_kwargs = mock_wait_for.call_args
    assert call_kwargs.get("timeout") == 60.0


async def test_timeout_raises_asyncio_timeout_error() -> None:
    """asyncio.wait_for timeout → fallback LLM_TIMEOUT returned, registry DEGRADED."""
    registry = HealthRegistry()

    async def slow_coroutine(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(10)
        return {}

    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=slow_coroutine)
    mock_store = _make_mock_store()

    report = await run_cold_path_diagnosis(
        case_id="test-timeout-real",
        triage_excerpt=_make_eligible_excerpt("test-timeout-real"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
        timeout_seconds=0.01,
    )

    assert report.reason_codes == ("LLM_TIMEOUT",)
    assert report.triage_hash == _FAKE_TRIAGE_HASH
    assert registry.get("llm") == HealthStatus.DEGRADED
    mock_store.put_if_absent.assert_called_once()


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — inflight gauge balance
# ---------------------------------------------------------------------------


async def test_inflight_gauge_balanced_on_failure() -> None:
    """llm_inflight_add(-1) called in finally even when invocation fails (fallback returned)."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=RuntimeError("llm exploded"))

    with patch(
        "aiops_triage_pipeline.diagnosis.graph.llm_inflight_add",
    ) as mock_gauge:
        report = await run_cold_path_diagnosis(
            case_id="test-gauge-balance",
            triage_excerpt=_make_eligible_excerpt("test-gauge-balance"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=mock_client,
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash=_FAKE_TRIAGE_HASH,
        )

    # RuntimeError caught by except Exception → LLM_ERROR fallback returned
    assert report.reason_codes == ("LLM_ERROR",)
    # +1 on entry, -1 in finally — always balanced
    assert mock_gauge.call_count == 2
    assert mock_gauge.call_args_list[0][0][0] == 1
    assert mock_gauge.call_args_list[1][0][0] == -1


async def test_timeout_path_emits_llm_timeout_error_and_fallback_metrics() -> None:
    registry = HealthRegistry()

    async def slow_coroutine(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(10)
        return {}

    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=slow_coroutine)

    with (
        patch("aiops_triage_pipeline.diagnosis.graph.record_llm_invocation") as mock_invocation,
        patch("aiops_triage_pipeline.diagnosis.graph.record_llm_latency") as mock_latency,
        patch("aiops_triage_pipeline.diagnosis.graph.record_llm_timeout") as mock_timeout,
        patch("aiops_triage_pipeline.diagnosis.graph.record_llm_error") as mock_error,
        patch("aiops_triage_pipeline.diagnosis.graph.record_llm_fallback") as mock_fallback,
    ):
        report = await run_cold_path_diagnosis(
            case_id="test-timeout-metrics",
            triage_excerpt=_make_eligible_excerpt("test-timeout-metrics"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=mock_client,
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash=_FAKE_TRIAGE_HASH,
            timeout_seconds=0.01,
        )

    assert report.reason_codes == ("LLM_TIMEOUT",)
    mock_invocation.assert_called_once_with(result="fallback")
    mock_latency.assert_called_once()
    mock_timeout.assert_called_once_with()
    mock_error.assert_called_once_with(error_type="TimeoutError")
    mock_fallback.assert_called_once_with(reason_code="LLM_TIMEOUT")


async def test_run_cold_path_diagnosis_emits_operational_alert_for_llm_error_rate() -> None:
    class _CaptureLogger:
        def __init__(self) -> None:
            self.events: list[tuple[str, str, dict[str, object]]] = []

        def info(self, event: str, **kwargs: object) -> None:
            self.events.append(("info", event, kwargs))

        def warning(self, event: str, **kwargs: object) -> None:
            self.events.append(("warning", event, kwargs))

        def critical(self, event: str, **kwargs: object) -> None:
            self.events.append(("critical", event, kwargs))

    policy = load_operational_alert_policy()
    policy = policy.model_copy(
        update={
            "llm_error_rate": policy.llm_error_rate.model_copy(update={"window_size": 3}),
        }
    )
    evaluator = OperationalAlertEvaluator(policy=policy, app_env="local")
    logger = _CaptureLogger()
    registry = HealthRegistry()

    with patch("aiops_triage_pipeline.diagnosis.graph._logger", logger):
        failing_client = MagicMock(spec=LLMClient)
        failing_client.invoke = AsyncMock(side_effect=RuntimeError("llm exploded"))
        for case_id in ("test-llm-err-rate-1", "test-llm-err-rate-2"):
            _ = await run_cold_path_diagnosis(
                case_id=case_id,
                triage_excerpt=_make_eligible_excerpt(case_id),
                evidence_summary=_EVIDENCE_SUMMARY,
                llm_client=failing_client,
                denylist=_EMPTY_DENYLIST,
                health_registry=registry,
                object_store_client=_make_mock_store(),
                triage_hash=_FAKE_TRIAGE_HASH,
                alert_evaluator=evaluator,
            )

        _ = await run_cold_path_diagnosis(
            case_id="test-llm-err-rate-3",
            triage_excerpt=_make_eligible_excerpt("test-llm-err-rate-3"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=_make_mock_client(),
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash=_FAKE_TRIAGE_HASH,
            alert_evaluator=evaluator,
        )

    alert_events = [
        event
        for event in logger.events
        if event[2].get("event_type") == "operational_alert_rule_triggered"
    ]
    assert alert_events
    _, _, fields = alert_events[0]
    assert fields["rule_id"] == "ALERT_LLM_ERROR_RATE_SPIKE_CRITICAL"
    assert fields["component"] == "llm"


async def test_health_registry_degraded_on_generic_exception() -> None:
    """HealthRegistry 'llm' → DEGRADED when invocation raises — fallback returned, not raised."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=RuntimeError("unexpected llm error"))

    report = await run_cold_path_diagnosis(
        case_id="test-degraded-generic",
        triage_excerpt=_make_eligible_excerpt("test-degraded-generic"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert report.reason_codes == ("LLM_ERROR",)
    assert registry.get("llm") == HealthStatus.DEGRADED


async def test_internal_validation_error_is_not_mapped_as_schema_invalid() -> None:
    """Internal validation failures are tracked as invocation_failed, not schema_invalid."""
    registry = HealthRegistry()

    with pytest.raises(pydantic.ValidationError):
        await run_cold_path_diagnosis(
            case_id="test-internal-validation-failure",
            triage_excerpt=_make_eligible_excerpt("test-internal-validation-failure"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=_make_mock_client(),
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash="not-a-sha256-hash",
        )

    health = registry.get_all()["llm"]
    assert health.status == HealthStatus.DEGRADED
    assert health.reason == "cold_path_invocation_failed"


async def test_timeout_fallback_writes_diagnosis_json() -> None:
    """Timeout fallback writes diagnosis.json and returns LLM_TIMEOUT reason code."""
    registry = HealthRegistry()
    mock_store = _make_mock_store()

    async def slow_coroutine(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(10)
        return {}

    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=slow_coroutine)

    report = await run_cold_path_diagnosis(
        case_id="test-timeout-fallback-write",
        triage_excerpt=_make_eligible_excerpt("test-timeout-fallback-write"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
        timeout_seconds=0.01,
    )

    assert report.reason_codes == ("LLM_TIMEOUT",)
    mock_store.put_if_absent.assert_called_once()
    call_kwargs = mock_store.put_if_absent.call_args.kwargs
    assert "diagnosis.json" in call_kwargs["key"]


async def test_timeout_fallback_has_triage_hash() -> None:
    """Timeout fallback populates triage_hash."""
    registry = HealthRegistry()

    async def slow_coroutine(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(10)
        return {}

    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=slow_coroutine)

    report = await run_cold_path_diagnosis(
        case_id="test-timeout-fallback-hash",
        triage_excerpt=_make_eligible_excerpt("test-timeout-fallback-hash"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
        timeout_seconds=0.01,
    )

    assert report.reason_codes == ("LLM_TIMEOUT",)
    assert report.triage_hash == _FAKE_TRIAGE_HASH


async def test_schema_validation_error_returns_schema_invalid_fallback() -> None:
    """ValidationError from LLM output maps to LLM_SCHEMA_INVALID and schema gap message."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=_make_validation_error())

    report = await run_cold_path_diagnosis(
        case_id="test-schema-invalid",
        triage_excerpt=_make_eligible_excerpt("test-schema-invalid"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert report.reason_codes == ("LLM_SCHEMA_INVALID",)
    assert report.gaps == ("LLM output failed schema validation",)


async def test_schema_validation_error_writes_diagnosis_json() -> None:
    """ValidationError fallback persists diagnosis.json."""
    registry = HealthRegistry()
    mock_store = _make_mock_store()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=_make_validation_error())

    await run_cold_path_diagnosis(
        case_id="test-schema-invalid-write",
        triage_excerpt=_make_eligible_excerpt("test-schema-invalid-write"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    mock_store.put_if_absent.assert_called_once()


async def test_connect_error_returns_unavailable_fallback() -> None:
    """ConnectError maps to LLM_UNAVAILABLE fallback."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    report = await run_cold_path_diagnosis(
        case_id="test-connect-error",
        triage_excerpt=_make_eligible_excerpt("test-connect-error"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert report.reason_codes == ("LLM_UNAVAILABLE",)


async def test_connect_error_writes_diagnosis_json() -> None:
    """ConnectError fallback persists diagnosis.json."""
    registry = HealthRegistry()
    mock_store = _make_mock_store()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    await run_cold_path_diagnosis(
        case_id="test-connect-error-write",
        triage_excerpt=_make_eligible_excerpt("test-connect-error-write"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    mock_store.put_if_absent.assert_called_once()


async def test_http_error_returns_llm_error_fallback() -> None:
    """HTTPStatusError maps to generic LLM_ERROR fallback."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=_make_http_status_error())

    report = await run_cold_path_diagnosis(
        case_id="test-http-error",
        triage_excerpt=_make_eligible_excerpt("test-http-error"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert report.reason_codes == ("LLM_ERROR",)


async def test_http_error_writes_diagnosis_json() -> None:
    """Generic error fallback path persists diagnosis.json for HTTPStatusError."""
    registry = HealthRegistry()
    mock_store = _make_mock_store()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=_make_http_status_error())

    await run_cold_path_diagnosis(
        case_id="test-http-error-write",
        triage_excerpt=_make_eligible_excerpt("test-http-error-write"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    mock_store.put_if_absent.assert_called_once()


async def test_success_path_persistence_failure_raises_without_llm_fallback() -> None:
    """Persistence failure after successful LLM output should fail loud (no LLM fallback remap)."""
    registry = HealthRegistry()
    mock_store = _make_mock_store()
    mock_store.put_if_absent.side_effect = RuntimeError("transient object store blip")

    with pytest.raises(RuntimeError, match="transient object store blip"):
        await run_cold_path_diagnosis(
            case_id="test-success-path-persist-failure",
            triage_excerpt=_make_eligible_excerpt("test-success-path-persist-failure"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=_make_mock_client(),
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=mock_store,
            triage_hash=_FAKE_TRIAGE_HASH,
        )

    health = registry.get_all()["llm"]
    assert health.status == HealthStatus.DEGRADED
    assert health.reason == "cold_path_invocation_failed"
    mock_store.put_if_absent.assert_called_once()


async def test_transport_timeout_returns_unavailable_fallback() -> None:
    """Transport timeout maps to LLM_UNAVAILABLE fallback."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=_make_read_timeout_error())

    report = await run_cold_path_diagnosis(
        case_id="test-transport-timeout",
        triage_excerpt=_make_eligible_excerpt("test-transport-timeout"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert report.reason_codes == ("LLM_UNAVAILABLE",)


async def test_no_retry_on_timeout() -> None:
    """Timeout path invokes asyncio.wait_for exactly once (no retry in same cycle)."""
    registry = HealthRegistry()

    async def _raise_timeout(awaitable: object, *, timeout: float) -> object:
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    with patch(
        "aiops_triage_pipeline.diagnosis.graph.asyncio.wait_for",
        side_effect=_raise_timeout,
    ) as mock_wait_for:
        report = await run_cold_path_diagnosis(
            case_id="test-no-retry-timeout",
            triage_excerpt=_make_eligible_excerpt("test-no-retry-timeout"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=_make_mock_client(),
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash=_FAKE_TRIAGE_HASH,
        )

    assert report.reason_codes == ("LLM_TIMEOUT",)
    mock_wait_for.assert_called_once()


async def test_fallback_report_is_schema_valid() -> None:
    """Fallback report can be re-validated by DiagnosisReportV1 schema without errors."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    report = await run_cold_path_diagnosis(
        case_id="test-fallback-schema-valid",
        triage_excerpt=_make_eligible_excerpt("test-fallback-schema-valid"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    validated = DiagnosisReportV1.model_validate(report.model_dump(mode="json"))
    assert validated.reason_codes == ("LLM_UNAVAILABLE",)


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — triage_hash and diagnosis.json persistence
# ---------------------------------------------------------------------------


async def test_run_cold_path_diagnosis_populates_triage_hash() -> None:
    """Returned report has triage_hash == _FAKE_TRIAGE_HASH."""
    registry = HealthRegistry()
    report = await run_cold_path_diagnosis(
        case_id="test-triage-hash",
        triage_excerpt=_make_eligible_excerpt("test-triage-hash"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )
    assert report.triage_hash == _FAKE_TRIAGE_HASH


async def test_run_cold_path_diagnosis_writes_diagnosis_json() -> None:
    """After successful invocation, put_if_absent called with key containing 'diagnosis.json'."""
    registry = HealthRegistry()
    mock_store = MagicMock(spec=ObjectStoreClientProtocol)
    mock_store.put_if_absent.return_value = PutIfAbsentResult.CREATED

    await run_cold_path_diagnosis(
        case_id="test-write-diag",
        triage_excerpt=_make_eligible_excerpt("test-write-diag"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    mock_store.put_if_absent.assert_called_once()
    call_kwargs = mock_store.put_if_absent.call_args.kwargs
    assert "diagnosis.json" in call_kwargs["key"]


async def test_run_cold_path_diagnosis_casefile_triage_hash_matches() -> None:
    """The persisted casefile's triage_hash field equals _FAKE_TRIAGE_HASH."""
    from aiops_triage_pipeline.models.case_file import CaseFileDiagnosisV1
    from aiops_triage_pipeline.storage.casefile_io import validate_casefile_diagnosis_json

    registry = HealthRegistry()
    mock_store = MagicMock(spec=ObjectStoreClientProtocol)
    mock_store.put_if_absent.return_value = PutIfAbsentResult.CREATED

    await run_cold_path_diagnosis(
        case_id="test-casefile-hash",
        triage_excerpt=_make_eligible_excerpt("test-casefile-hash"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    call_kwargs = mock_store.put_if_absent.call_args.kwargs
    persisted_body: bytes = call_kwargs["body"]
    casefile = validate_casefile_diagnosis_json(persisted_body)
    assert isinstance(casefile, CaseFileDiagnosisV1)
    assert casefile.triage_hash == _FAKE_TRIAGE_HASH


# ---------------------------------------------------------------------------
# spawn_cold_path_diagnosis_task — triage_hash forwarding
# ---------------------------------------------------------------------------


async def test_spawn_cold_path_diagnosis_task_forwards_triage_hash() -> None:
    """Eligible case: task completes, returned report has triage_hash == _FAKE_TRIAGE_HASH."""
    registry = HealthRegistry()
    task = spawn_cold_path_diagnosis_task(
        case_id="test-spawn-hash",
        triage_excerpt=_make_eligible_excerpt("test-spawn-hash"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
        app_env=AppEnv.prod,
    )
    assert task is not None
    report = await task
    assert report.triage_hash == _FAKE_TRIAGE_HASH


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — LLM narrative OUTPUT denylist enforcement
# ---------------------------------------------------------------------------

_BEARER_TOKEN_DENYLIST = DenylistV1(
    denylist_version="v1.0.0",
    denied_field_names=(),
    denied_value_patterns=("(?i)bearer\\s+[A-Za-z0-9._+/=\\-]{10,}",),
)

_CREDENTIAL_URL_DENYLIST = DenylistV1(
    denylist_version="v1.0.0",
    denied_field_names=(),
    denied_value_patterns=("(?i)://[^:@/]+:[^@/]{3,}@",),
)


def _make_llm_report_with_verdict(verdict: str) -> DiagnosisReportV1:
    """Build a minimal DiagnosisReportV1 with the given verdict."""
    return DiagnosisReportV1(
        verdict=verdict,
        confidence=DiagnosisConfidence.LOW,
        evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
    )


def _make_llm_report_with_facts(*facts: str) -> DiagnosisReportV1:
    """Build a minimal DiagnosisReportV1 with the given facts."""
    return DiagnosisReportV1(
        verdict="Consumer lag root cause: upstream producer stall.",
        confidence=DiagnosisConfidence.MEDIUM,
        evidence_pack=EvidencePack(facts=facts, missing_evidence=(), matched_rules=()),
    )


def _make_mock_llm_client(report: DiagnosisReportV1) -> MagicMock:
    """Return a MagicMock(spec=LLMClient) whose invoke() returns the given report."""
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(return_value=report)
    return mock_client


async def test_llm_narrative_required_field_denied_triggers_schema_invalid_fallback() -> None:
    """LLM verdict (required field) containing Bearer token: denied verdict causes ValidationError
    on reconstruction → LLM_SCHEMA_INVALID fallback returned, dirty token never appears."""
    registry = HealthRegistry()
    dirty_verdict = "Bearer AbCdEfGhIjKlMnOpQrSt12345"
    mock_client = _make_mock_llm_client(_make_llm_report_with_verdict(dirty_verdict))

    report = await run_cold_path_diagnosis(
        case_id="test-output-sanitize-verdict",
        triage_excerpt=_make_eligible_excerpt("test-output-sanitize-verdict"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_BEARER_TOKEN_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    # verdict denied → absent from sanitized dict → ValidationError → LLM_SCHEMA_INVALID fallback
    assert dirty_verdict not in report.verdict
    assert "LLM_SCHEMA_INVALID" in report.reason_codes


async def test_llm_narrative_optional_field_denied_sanitized_and_persisted() -> None:
    """LLM fact (optional list item) containing Bearer token is removed; clean fact is preserved
    and the sanitized report is successfully persisted (happy-path sanitize-and-persist)."""
    registry = HealthRegistry()
    dirty_fact = "Authorization: Bearer AbCdEfGhIjKlMnOpQrSt12345"
    clean_fact = "Consumer lag elevated: 45000 messages behind."
    mock_client = _make_mock_llm_client(_make_llm_report_with_facts(dirty_fact, clean_fact))

    report = await run_cold_path_diagnosis(
        case_id="test-output-sanitize-persist",
        triage_excerpt=_make_eligible_excerpt("test-output-sanitize-persist"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_BEARER_TOKEN_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    # Sanitized report persisted successfully — no fallback triggered
    assert not report.reason_codes
    assert dirty_fact not in report.evidence_pack.facts
    assert clean_fact in report.evidence_pack.facts


async def test_llm_narrative_denied_field_in_facts_sanitized() -> None:
    """LLM facts containing credential URL are removed; clean facts are preserved."""
    registry = HealthRegistry()
    credential_url = "postgresql://user:secret@db-host/prod"
    clean_fact = "Consumer lag elevated: 45000 messages behind."
    mock_client = _make_mock_llm_client(
        _make_llm_report_with_facts(clean_fact, credential_url)
    )

    report = await run_cold_path_diagnosis(
        case_id="test-output-sanitize-facts",
        triage_excerpt=_make_eligible_excerpt("test-output-sanitize-facts"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_CREDENTIAL_URL_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    # Credential URL fact removed; clean fact preserved
    assert credential_url not in report.evidence_pack.facts
    assert clean_fact in report.evidence_pack.facts


async def test_llm_narrative_clean_output_passes_through_unchanged() -> None:
    """Clean LLM output with no denied patterns passes through apply_denylist unchanged."""
    registry = HealthRegistry()
    clean_verdict = "Consumer lag caused by upstream producer stall in payments stream."
    clean_fact = "Consumer group payments-consumer lag: 45000 messages."
    mock_client = _make_mock_llm_client(
        DiagnosisReportV1(
            verdict=clean_verdict,
            confidence=DiagnosisConfidence.LOW,
            evidence_pack=EvidencePack(
                facts=(clean_fact,), missing_evidence=(), matched_rules=()
            ),
        )
    )

    report = await run_cold_path_diagnosis(
        case_id="test-output-clean",
        triage_excerpt=_make_eligible_excerpt("test-output-clean"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_BEARER_TOKEN_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert report.verdict == clean_verdict
    assert clean_fact in report.evidence_pack.facts


async def test_llm_narrative_sanitization_uses_active_denylist() -> None:
    """A non-empty denylist with Bearer pattern correctly removes matching content."""
    registry = HealthRegistry()
    # Use a denylist with a specific Bearer pattern — verify it's NOT the empty stub
    active_denylist = DenylistV1(
        denylist_version="v1.0.0",
        denied_field_names=(),
        denied_value_patterns=("(?i)bearer\\s+[A-Za-z0-9._+/=\\-]{10,}",),
    )
    assert active_denylist.denied_value_patterns, "Active denylist must have patterns"

    dirty_fact = "Authorization: Bearer SecretToken12345abc"
    clean_fact = "Consumer lag elevated: 45000 messages behind."
    mock_client = _make_mock_llm_client(
        DiagnosisReportV1(
            verdict="CONSUMER_LAG_UPSTREAM_STALL",
            confidence=DiagnosisConfidence.HIGH,
            evidence_pack=EvidencePack(
                facts=(dirty_fact, clean_fact), missing_evidence=(), matched_rules=()
            ),
        )
    )

    report = await run_cold_path_diagnosis(
        case_id="test-active-denylist",
        triage_excerpt=_make_eligible_excerpt("test-active-denylist"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=active_denylist,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert dirty_fact not in report.evidence_pack.facts
    assert clean_fact in report.evidence_pack.facts
    assert clean_fact in report.evidence_pack.facts
