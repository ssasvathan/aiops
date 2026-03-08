"""Integration tests for AG5 Redis dedupe and degraded-mode behavior (Story 5.5).

Tests use a real Redis instance via Testcontainers to verify:
- Deduplication within TTL window (FR33)
- NOTIFY-only cap when Redis is unavailable (FR34)
- DegradedModeEvent emission and HealthRegistry update (FR51)
- Recovery restores normal AG5 behavior
"""

from __future__ import annotations

import socket
import time
from datetime import UTC, datetime

import pytest
import redis as redis_lib
from testcontainers.core.container import DockerContainer

from aiops_triage_pipeline.cache.dedupe import RedisActionDedupeStore
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.redis_ttl_policy import AG5DedupeTtlConfig
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.models.health import HealthStatus
from aiops_triage_pipeline.pipeline.scheduler import (
    emit_redis_degraded_mode_events,
    run_gate_decision_stage_cycle,
)
from aiops_triage_pipeline.pipeline.stages.peak import load_rulebook_policy
from tests.integration.conftest import _is_environment_prereq_error, _wait_for_redis


@pytest.fixture(scope="module")
def redis_container():
    try:
        with DockerContainer("redis:7.2-alpine").with_exposed_ports(6379) as container:
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(6379))
            _wait_for_redis(host, port)
            yield container
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Docker/Redis unavailable: {exc}")
        raise


@pytest.fixture()
def redis_client(redis_container):
    client = redis_lib.Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        decode_responses=True,
    )
    client.flushall()
    return client


def _bad_redis_client() -> redis_lib.Redis:
    """Return a Redis client pointing at a port guaranteed to be unreachable.

    Allocates a free port via the OS, releases it, then targets it — the port
    will not be listening, so Redis connection attempts fail immediately.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return redis_lib.Redis(host="127.0.0.1", port=port, socket_connect_timeout=1)


def _gate_input(fingerprint: str = "fp-test") -> GateInputV1:
    return GateInputV1(
        env="prod",
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role="SHARED_TOPIC",
        anomaly_family="VOLUME_DROP",
        criticality_tier="TIER_0",
        proposed_action="PAGE",
        diagnosis_confidence=0.95,
        sustained=True,
        findings=(
            Finding(
                finding_id="f-1",
                name="volume-drop",
                is_anomalous=True,
                evidence_required=("topic_messages_in_per_sec",),
                is_primary=True,
            ),
        ),
        evidence_status_map={"topic_messages_in_per_sec": "PRESENT"},
        action_fingerprint=fingerprint,
        peak=True,
    )


# ── Deduplication within TTL window (FR33) ────────────────────────────────────


def test_redis_dedupe_store_is_not_duplicate_on_first_action(redis_client) -> None:
    store = RedisActionDedupeStore(redis_client)
    assert store.is_duplicate("fp-new") is False


def test_redis_dedupe_store_remembers_and_detects_duplicate(redis_client) -> None:
    store = RedisActionDedupeStore(redis_client)
    store.remember("fp-dup", Action.PAGE)
    assert store.is_duplicate("fp-dup") is True


def test_redis_dedupe_store_page_ttl_expires_and_allows_new_action(redis_client) -> None:
    short_ttl = AG5DedupeTtlConfig(page_seconds=1, ticket_seconds=2, notify_seconds=1)
    store = RedisActionDedupeStore(redis_client, ttl_config=short_ttl)
    store.remember("fp-expiry", Action.PAGE)

    assert store.is_duplicate("fp-expiry") is True
    time.sleep(2)
    assert store.is_duplicate("fp-expiry") is False


def test_redis_dedupe_store_different_fingerprints_are_independent(redis_client) -> None:
    store = RedisActionDedupeStore(redis_client)
    store.remember("fp-a", Action.TICKET)

    assert store.is_duplicate("fp-a") is True
    assert store.is_duplicate("fp-b") is False


# ── AG5 gate integration with real Redis ─────────────────────────────────────


def test_ag5_gate_suppresses_duplicate_action_within_ttl(redis_client) -> None:
    store = RedisActionDedupeStore(redis_client)
    rulebook = load_rulebook_policy()
    gate_input = _gate_input("fp-storm")

    first = run_gate_decision_stage_cycle(
        gate_inputs_by_scope={("prod", "cluster-a", "orders"): (gate_input,)},
        rulebook_policy=rulebook,
        dedupe_store=store,
    )
    second = run_gate_decision_stage_cycle(
        gate_inputs_by_scope={("prod", "cluster-a", "orders"): (gate_input,)},
        rulebook_policy=rulebook,
        dedupe_store=store,
    )

    assert first[("prod", "cluster-a", "orders")][0].final_action == Action.PAGE
    assert second[("prod", "cluster-a", "orders")][0].final_action == Action.OBSERVE
    scope_key = ("prod", "cluster-a", "orders")
    assert "AG5_DUPLICATE_SUPPRESSED" in second[scope_key][0].gate_reason_codes


# ── Redis unavailability → NOTIFY-only cap (FR34) ─────────────────────────────


def test_ag5_gate_caps_to_notify_when_redis_unavailable() -> None:
    bad_client = _bad_redis_client()
    store = RedisActionDedupeStore(bad_client)
    rulebook = load_rulebook_policy()

    decisions = run_gate_decision_stage_cycle(
        gate_inputs_by_scope={("prod", "cluster-a", "orders"): (_gate_input("fp-unavail"),)},
        rulebook_policy=rulebook,
        dedupe_store=store,
    )

    decision = decisions[("prod", "cluster-a", "orders")][0]
    assert decision.final_action == Action.NOTIFY
    assert "AG5_DEDUPE_STORE_ERROR" in decision.gate_reason_codes
    assert store.is_healthy is False


# ── DegradedModeEvent emission and HealthRegistry update (FR51) ───────────────


async def test_emit_redis_degraded_mode_events_on_real_connection_failure() -> None:
    bad_client = _bad_redis_client()
    store = RedisActionDedupeStore(bad_client)

    # Trigger failure
    try:
        store.is_duplicate("fp-test")
    except Exception:
        pass

    registry = HealthRegistry()
    events = await emit_redis_degraded_mode_events(
        dedupe_store=store,
        evaluation_time=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
        health_registry=registry,
    )

    assert len(events) == 1
    assert events[0].affected_scope == "redis"
    assert events[0].capped_action_level == "NOTIFY-only"
    assert registry.get("redis") == HealthStatus.DEGRADED


# ── Recovery restores normal behavior ────────────────────────────────────────


async def test_redis_recovery_restores_health_status(redis_client) -> None:
    bad_client = _bad_redis_client()
    store = RedisActionDedupeStore(bad_client)

    try:
        store.is_duplicate("fp-pre-fail")
    except Exception:
        pass

    registry = HealthRegistry()
    await emit_redis_degraded_mode_events(
        dedupe_store=store,
        evaluation_time=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
        health_registry=registry,
    )
    assert registry.get("redis") == HealthStatus.DEGRADED

    # Swap to working Redis
    recovered_store = RedisActionDedupeStore(redis_client)
    recovered_store.is_duplicate("fp-recovery-check")  # succeeds

    recovery_events = await emit_redis_degraded_mode_events(
        dedupe_store=recovered_store,
        evaluation_time=datetime(2026, 3, 6, 12, 5, tzinfo=UTC),
        health_registry=registry,
    )

    assert recovery_events == ()
    assert registry.get("redis") == HealthStatus.HEALTHY
