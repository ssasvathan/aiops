"""Internal health domain models — not part of the frozen contracts package."""

from enum import Enum

from pydantic import AwareDatetime, BaseModel


class HealthStatus(str, Enum):
    """Per-component health state tracked by HealthRegistry."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ComponentHealth(BaseModel, frozen=True):
    """Snapshot of a single component's health at a point in time.

    Stored in HealthRegistry._components. Immutable — each status change
    replaces the entry rather than mutating in place.

    Attributes:
        component: Unique component identifier (e.g., "redis", "prometheus", "llm")
        status: Current health state
        reason: Human-readable explanation of the current state (None if HEALTHY)
        updated_at: UTC timestamp of last status change
    """

    component: str
    status: HealthStatus
    reason: str | None = None
    updated_at: AwareDatetime  # rejects naive datetimes — always UTC-aware
