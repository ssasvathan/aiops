"""ATDD fixture builders for Story 3.4 diagnosis persistence fallback guarantees."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from aiops_triage_pipeline.contracts.enums import CriticalityTier, Environment
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult


def build_triage_excerpt(case_id: str = "case-3-4-red-001") -> TriageExcerptV1:
    """Build deterministic triage excerpt for Story 3.4 ATDD tests."""
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-story-3-4",
        stream_id="stream-story-3-4",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="OWN::Streaming::Payments",
        sustained=True,
        peak=True,
        evidence_status_map={},
        findings=(),
        triage_timestamp=datetime(2026, 3, 23, 0, 0, tzinfo=UTC),
    )


def build_empty_denylist() -> DenylistV1:
    """Build denylist with no denied fields for focused diagnosis tests."""
    return DenylistV1(denylist_version="test-v1", denied_field_names=())


def build_health_registry() -> HealthRegistry:
    """Build a fresh health registry for each ATDD test."""
    return HealthRegistry()


def build_object_store_client() -> MagicMock:
    """Build object store mock that supports write-once diagnosis persistence."""
    mock_store = MagicMock(spec=ObjectStoreClientProtocol)
    mock_store.put_if_absent.return_value = PutIfAbsentResult.CREATED
    return mock_store
