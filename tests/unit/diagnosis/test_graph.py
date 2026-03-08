"""Unit tests for diagnosis/graph.py — LangGraph graph and fire-and-forget launcher."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiops_triage_pipeline.config.settings import AppEnv, IntegrationMode
from aiops_triage_pipeline.contracts.enums import CriticalityTier, Environment
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.diagnosis.graph import (
    meets_invocation_criteria,
    run_cold_path_diagnosis,
    spawn_cold_path_diagnosis_task,
)
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.integrations.llm import LLMClient
from aiops_triage_pipeline.models.health import HealthStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EVIDENCE_SUMMARY = "Consumer lag elevated: 45000 messages behind."
_EMPTY_DENYLIST = DenylistV1(denylist_version="test-v1", denied_field_names=())


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


# ---------------------------------------------------------------------------
# meets_invocation_criteria
# ---------------------------------------------------------------------------


async def test_meets_invocation_criteria_prod_tier0_sustained_returns_true() -> None:
    """prod + TIER_0 + sustained=True → True."""
    excerpt = _make_eligible_excerpt()
    assert meets_invocation_criteria(excerpt, AppEnv.prod) is True


async def test_meets_invocation_criteria_local_env_returns_false() -> None:
    """Non-prod (local) → False regardless of tier/sustained."""
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
    assert meets_invocation_criteria(excerpt, AppEnv.local) is False


async def test_meets_invocation_criteria_prod_tier1_returns_false() -> None:
    """prod + TIER_1 → False (only TIER_0 qualifies)."""
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
    assert meets_invocation_criteria(excerpt, AppEnv.prod) is False


async def test_meets_invocation_criteria_prod_tier0_not_sustained_returns_false() -> None:
    """prod + TIER_0 + sustained=False → False."""
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
    assert meets_invocation_criteria(excerpt, AppEnv.prod) is False


# ---------------------------------------------------------------------------
# spawn_cold_path_diagnosis_task
# ---------------------------------------------------------------------------


async def test_spawn_ineligible_returns_none() -> None:
    """Ineligible case (local env) → spawn returns None, no task spawned."""
    registry = HealthRegistry()
    task = spawn_cold_path_diagnosis_task(
        case_id="test-001",
        triage_excerpt=_make_eligible_excerpt(),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=_make_mock_client(),
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        app_env=AppEnv.local,
    )
    assert task is None


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
    )
    assert report.schema_version == "v1"
    assert registry.get("llm") == HealthStatus.HEALTHY


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — denylist applied
# ---------------------------------------------------------------------------


async def test_denylist_applied_to_triage_excerpt() -> None:
    """apply_denylist is called on triage_excerpt before passing to LLMClient.invoke()."""
    registry = HealthRegistry()
    excerpt = _make_eligible_excerpt()

    with patch(
        "aiops_triage_pipeline.diagnosis.graph.apply_denylist",
    ) as mock_apply:
        # Return the full dict so reconstruction succeeds
        mock_apply.return_value = excerpt.model_dump(mode="json")
        await run_cold_path_diagnosis(
            case_id="test-denylist",
            triage_excerpt=excerpt,
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=_make_mock_client(),
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
        )

    mock_apply.assert_called_once()
    call_args = mock_apply.call_args
    # First positional arg is the dict from model_dump(mode="json")
    assert isinstance(call_args[0][0], dict)
    # Second positional arg is the denylist
    assert call_args[0][1] is _EMPTY_DENYLIST


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
        )

    mock_wait_for.assert_called_once()
    _, call_kwargs = mock_wait_for.call_args
    assert call_kwargs.get("timeout") == 60.0


async def test_timeout_raises_asyncio_timeout_error() -> None:
    """asyncio.wait_for raises TimeoutError when timeout elapses."""
    registry = HealthRegistry()

    async def slow_coroutine(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(10)
        return {}

    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=slow_coroutine)

    try:
        await run_cold_path_diagnosis(
            case_id="test-timeout-real",
            triage_excerpt=_make_eligible_excerpt("test-timeout-real"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=mock_client,
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            timeout_seconds=0.01,
        )
        assert False, "Expected TimeoutError"
    except asyncio.TimeoutError:
        pass

    assert registry.get("llm") == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# run_cold_path_diagnosis — inflight gauge balance
# ---------------------------------------------------------------------------


async def test_inflight_gauge_balanced_on_failure() -> None:
    """llm_inflight_add(-1) is called in finally even when invocation fails."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=RuntimeError("llm exploded"))

    with patch(
        "aiops_triage_pipeline.diagnosis.graph.llm_inflight_add",
    ) as mock_gauge:
        with pytest.raises(RuntimeError, match="llm exploded"):
            await run_cold_path_diagnosis(
                case_id="test-gauge-balance",
                triage_excerpt=_make_eligible_excerpt("test-gauge-balance"),
                evidence_summary=_EVIDENCE_SUMMARY,
                llm_client=mock_client,
                denylist=_EMPTY_DENYLIST,
                health_registry=registry,
            )

    # +1 on entry, -1 in finally — always balanced regardless of exception
    assert mock_gauge.call_count == 2
    assert mock_gauge.call_args_list[0][0][0] == 1
    assert mock_gauge.call_args_list[1][0][0] == -1


async def test_health_registry_degraded_on_generic_exception() -> None:
    """HealthRegistry 'llm' → DEGRADED when invocation raises a non-timeout exception."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=RuntimeError("unexpected llm error"))

    with pytest.raises(RuntimeError, match="unexpected llm error"):
        await run_cold_path_diagnosis(
            case_id="test-degraded-generic",
            triage_excerpt=_make_eligible_excerpt("test-degraded-generic"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=mock_client,
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
        )

    assert registry.get("llm") == HealthStatus.DEGRADED
