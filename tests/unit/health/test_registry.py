import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.models.events import DegradedModeEvent, TelemetryDegradedEvent
from aiops_triage_pipeline.models.health import ComponentHealth, HealthStatus


async def test_update_sets_healthy_status(registry: HealthRegistry) -> None:
    """update() with HEALTHY stores HEALTHY status."""
    await registry.update("redis", HealthStatus.HEALTHY)
    assert registry.get("redis") == HealthStatus.HEALTHY


async def test_update_sets_degraded_status(registry: HealthRegistry) -> None:
    """update() with DEGRADED stores DEGRADED status."""
    await registry.update("redis", HealthStatus.DEGRADED, reason="Connection refused")
    assert registry.get("redis") == HealthStatus.DEGRADED


async def test_update_sets_unavailable_status(registry: HealthRegistry) -> None:
    """update() with UNAVAILABLE stores UNAVAILABLE status."""
    await registry.update("prometheus", HealthStatus.UNAVAILABLE, reason="HTTP 503")
    assert registry.get("prometheus") == HealthStatus.UNAVAILABLE


def test_get_unknown_component_returns_none(registry: HealthRegistry) -> None:
    """get() on a never-registered component returns None."""
    assert registry.get("nonexistent") is None


async def test_is_degraded_true_for_degraded(registry: HealthRegistry) -> None:
    """is_degraded() returns True when component is DEGRADED."""
    await registry.update("redis", HealthStatus.DEGRADED)
    assert registry.is_degraded("redis") is True


async def test_is_degraded_true_for_unavailable(registry: HealthRegistry) -> None:
    """is_degraded() returns True when component is UNAVAILABLE."""
    await registry.update("prometheus", HealthStatus.UNAVAILABLE)
    assert registry.is_degraded("prometheus") is True


async def test_is_degraded_false_for_healthy(registry: HealthRegistry) -> None:
    """is_degraded() returns False when component is HEALTHY."""
    await registry.update("redis", HealthStatus.HEALTHY)
    assert registry.is_degraded("redis") is False


def test_is_degraded_false_for_unknown(registry: HealthRegistry) -> None:
    """is_degraded() returns False for unknown (never-registered) component."""
    assert registry.is_degraded("nonexistent") is False


async def test_get_all_returns_snapshot(registry: HealthRegistry) -> None:
    """get_all() returns all registered component health records."""
    await registry.update("redis", HealthStatus.DEGRADED)
    await registry.update("prometheus", HealthStatus.HEALTHY)
    all_health = registry.get_all()
    assert "redis" in all_health
    assert "prometheus" in all_health
    assert all_health["redis"].status == HealthStatus.DEGRADED
    assert all_health["prometheus"].status == HealthStatus.HEALTHY


async def test_get_all_returns_copy(registry: HealthRegistry) -> None:
    """get_all() returns a copy — mutating it does not affect the registry."""
    await registry.update("redis", HealthStatus.HEALTHY)
    snapshot = registry.get_all()
    snapshot.pop("redis")  # Mutate the copy
    assert registry.get("redis") == HealthStatus.HEALTHY  # Original unchanged


async def test_concurrent_updates_no_corruption(registry: HealthRegistry) -> None:
    """asyncio.gather with simultaneous updates does not corrupt registry state."""
    statuses = [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNAVAILABLE] * 7

    async def updater(s: HealthStatus) -> None:
        await registry.update("shared_component", s)

    # Fire 21 concurrent updates — no exception should be raised
    await asyncio.gather(*[updater(s) for s in statuses])

    # Final status must be one of the valid values (not None, not corrupted)
    final_status = registry.get("shared_component")
    assert final_status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNAVAILABLE)


def test_degraded_mode_event_creation() -> None:
    """DegradedModeEvent can be instantiated with all required fields."""
    event = DegradedModeEvent(
        affected_scope="redis",
        reason="ConnectionRefusedError: [Errno 111]",
        capped_action_level="NOTIFY-only",
        estimated_impact_window="unknown",
        timestamp=datetime.now(tz=timezone.utc),
    )
    assert event.affected_scope == "redis"
    assert event.capped_action_level == "NOTIFY-only"


def test_telemetry_degraded_event_creation() -> None:
    """TelemetryDegradedEvent can be instantiated with all required fields."""
    event = TelemetryDegradedEvent(
        affected_scope="prometheus",
        reason="HTTP 503 after 3 retries",
        recovery_status="pending",
        timestamp=datetime.now(tz=timezone.utc),
    )
    assert event.affected_scope == "prometheus"
    assert event.recovery_status == "pending"


def test_component_health_is_frozen() -> None:
    """ComponentHealth is immutable — mutation raises ValidationError."""
    health = ComponentHealth(
        component="redis",
        status=HealthStatus.HEALTHY,
        updated_at=datetime.now(tz=timezone.utc),
    )
    with pytest.raises(ValidationError):
        health.status = HealthStatus.DEGRADED  # type: ignore[misc]


async def test_update_stores_reason(registry: HealthRegistry) -> None:
    """update() with reason stores it in ComponentHealth.reason."""
    await registry.update("llm", HealthStatus.DEGRADED, reason="Timeout after 30s")
    health = registry.get_all()["llm"]
    assert health.reason == "Timeout after 30s"


async def test_concurrent_updates_multiple_components(registry: HealthRegistry) -> None:
    """Concurrent updates to distinct components all land correctly (no cross-contamination)."""
    components = ["redis", "prometheus", "llm", "postgres", "kafka"]
    target_status = HealthStatus.DEGRADED

    async def update_component(name: str) -> None:
        await registry.update(name, target_status, reason=f"{name}-degraded")

    await asyncio.gather(*[update_component(c) for c in components])

    for c in components:
        assert registry.get(c) == target_status
        assert registry.get_all()[c].reason == f"{c}-degraded"


async def test_update_overwrites_previous_status(registry: HealthRegistry) -> None:
    """Multiple update() calls on same component keep the latest status."""
    await registry.update("redis", HealthStatus.DEGRADED, reason="initial")
    await registry.update("redis", HealthStatus.HEALTHY)
    assert registry.get("redis") == HealthStatus.HEALTHY
    assert registry.get_all()["redis"].reason is None
