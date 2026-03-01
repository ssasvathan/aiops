"""Centralized health registry — asyncio-safe, singleton, per-component status tracking."""

import asyncio
import functools
from datetime import datetime, timezone

from aiops_triage_pipeline.health.metrics import record_status
from aiops_triage_pipeline.models.health import ComponentHealth, HealthStatus


class HealthRegistry:
    """Singleton tracking per-component health status (HEALTHY/DEGRADED/UNAVAILABLE).

    Asyncio-safe: uses asyncio.Lock for write operations. Read operations
    (get, get_all, is_degraded) are lock-free — safe for single-threaded asyncio.

    Usage pattern in pipeline stages:
        registry = get_health_registry()
        if registry.is_degraded("redis"):
            action = min(action, "NOTIFY")  # Cap to NOTIFY-only
        ...
        await registry.update("redis", HealthStatus.DEGRADED, reason=str(exc))
    """

    def __init__(self) -> None:
        # asyncio.Lock — NOT threading.Lock (pipeline is single-threaded asyncio)
        self._lock = asyncio.Lock()
        self._components: dict[str, ComponentHealth] = {}

    async def update(
        self,
        component: str,
        status: HealthStatus,
        reason: str | None = None,
    ) -> None:
        """Update component status. Asyncio-safe write.

        Args:
            component: Unique component identifier (e.g., "redis", "prometheus", "llm")
            status: New health status
            reason: Optional reason for the transition (recommended for DEGRADED/UNAVAILABLE)
        """
        async with self._lock:
            self._components[component] = ComponentHealth(
                component=component,
                status=status,
                reason=reason,
                updated_at=datetime.now(tz=timezone.utc),
            )
        record_status(component, status)

    def get(self, component: str) -> HealthStatus | None:
        """Get current status for a component (lock-free read).

        Returns None if the component has not registered a status yet.
        Unknown components are treated as HEALTHY by convention (degraded behavior
        must be explicitly registered; silence is not degradation).
        """
        health = self._components.get(component)
        return health.status if health else None

    def get_all(self) -> dict[str, ComponentHealth]:
        """Return a shallow copy snapshot of all component health records (lock-free read).

        Returns a dict keyed by component name. Safe to iterate because
        dict() creates a shallow copy at call time — callers iterate the
        snapshot, not the live registry dict that update() mutates.
        """
        return dict(self._components)

    def is_degraded(self, component: str) -> bool:
        """Return True if component is DEGRADED or UNAVAILABLE.

        Pipeline stages call this before applying degraded-mode caps.
        Unknown components return False — unknown ≠ degraded.
        """
        status = self.get(component)
        return status in (HealthStatus.DEGRADED, HealthStatus.UNAVAILABLE)


@functools.cache
def get_health_registry() -> HealthRegistry:
    """Return the singleton HealthRegistry instance. Cached after first call.

    For testing, construct a fresh HealthRegistry() directly — do NOT call
    get_health_registry() in tests (singleton state bleeds across tests).
    Use get_health_registry.cache_clear() only if testing singleton behavior.
    """
    return HealthRegistry()
