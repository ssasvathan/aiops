# Story 1.6: HealthRegistry & Degraded Mode Foundation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/operator,
I want a centralized health registry that tracks per-component status and coordinates degraded-mode behavior,
so that the pipeline can safely degrade when individual components fail and I can query system health via a /health endpoint.

## Acceptance Criteria

1. **Given** the HealthRegistry singleton is initialized,
   **When** a component reports a status change (HEALTHY / DEGRADED / UNAVAILABLE),
   **Then** the registry updates that component's status using asyncio-safe primitives (no threading locks)

2. **And** pipeline stages can query the registry to apply degraded-mode caps
   (e.g., Redis DEGRADED → NOTIFY-only per AG5)

3. **And** a lightweight `/health` HTTP endpoint returns current component statuses as JSON
   (served via asyncio — no external HTTP framework added)

4. **And** `DegradedModeEvent` is emittable when a component transitions to DEGRADED / UNAVAILABLE,
   containing: `affected_scope`, `reason`, `capped_action_level`, `estimated_impact_window`, `timestamp`

5. **And** `TelemetryDegradedEvent` is emittable when Prometheus is unavailable,
   containing: `affected_scope`, `reason`, `recovery_status`, `timestamp`

6. **And** unit tests verify:
   - Status transitions (all three values stored and retrieved correctly)
   - Concurrent access safety (asyncio.gather with multiple simultaneous updates — no corruption)
   - Degraded-mode query behavior (`is_degraded()` returns True for DEGRADED/UNAVAILABLE, False for HEALTHY)
   - Event model creation (both event types instantiable with all required fields)

## Tasks / Subtasks

- [x] Task 1: Define health models in `models/health.py` (AC: #1, #2)
  - [x] Define `HealthStatus(str, Enum)` with three values: `HEALTHY`, `DEGRADED`, `UNAVAILABLE`
  - [x] Define `ComponentHealth(BaseModel, frozen=True)` with fields: `component: str`, `status: HealthStatus`, `reason: str | None = None`, `updated_at: datetime`
  - [x] Confirm these are in `models/health.py` — NOT in `contracts/` (contracts/ holds the 12 frozen event/policy contracts only; internal domain models live in `models/`)

- [x] Task 2: Define event models in `models/events.py` (AC: #4, #5)
  - [x] Define `DegradedModeEvent(BaseModel, frozen=True)` with fields:
    - `affected_scope: str` — component or subsystem name (e.g., "redis", "prometheus")
    - `reason: str` — why it degraded
    - `capped_action_level: str` — e.g., "NOTIFY-only" (the new maximum allowed action)
    - `estimated_impact_window: str | None = None` — e.g., "unknown", "5m" (optional)
    - `timestamp: datetime` — UTC timestamp of transition
  - [x] Define `TelemetryDegradedEvent(BaseModel, frozen=True)` with fields:
    - `affected_scope: str` — e.g., "prometheus"
    - `reason: str` — why Prometheus is unavailable
    - `recovery_status: str` — e.g., "pending", "resolved"
    - `timestamp: datetime` — UTC timestamp
  - [x] Both models: `frozen=True` on class declaration (not via `model_config`)

- [x] Task 3: Implement `HealthRegistry` singleton in `health/registry.py` (AC: #1, #2)
  - [x] In `src/aiops_triage_pipeline/health/registry.py`, define `HealthRegistry` class:
    - `__init__`: create `asyncio.Lock()` (NOT `threading.Lock`) and `dict[str, ComponentHealth]` storage
    - `async update(component, status, reason=None) -> None`: acquire lock, set ComponentHealth with `datetime.now(tz=timezone.utc)`
    - `get(component: str) -> HealthStatus | None`: read-only, no lock needed (returns status or None if unknown)
    - `get_all() -> dict[str, ComponentHealth]`: return shallow copy of all component health records
    - `is_degraded(component: str) -> bool`: True if status is DEGRADED or UNAVAILABLE (what pipeline stages call before capping actions)
  - [x] Define `get_health_registry() -> HealthRegistry` using `@functools.cache` (same singleton pattern as `get_settings()` in `config/settings.py`)
  - [x] Do NOT import from `pipeline/`, `denylist/`, `contracts/`, `integrations/` — health/ is a provider package

- [x] Task 4: Implement `/health` HTTP server in `health/server.py` (AC: #3)
  - [x] In `src/aiops_triage_pipeline/health/server.py`, implement `start_health_server(host, port) -> asyncio.Server`
  - [x] Use `asyncio.start_server()` — NO new HTTP framework dependency (aiohttp/fastapi not needed)
  - [x] Handler reads HTTP request headers until blank line (`\r\n`), returns HTTP 200 with JSON body
  - [x] JSON body: serialized `ComponentHealth` records from `get_health_registry().get_all()` using `model.model_dump(mode="json")`
  - [x] Include `datetime` serialization via `default=str` in `json.dumps()`
  - [x] Add `Connection: close` header — single-shot responses (health polling, not streaming)

- [x] Task 5: Implement OTLP health metrics stub in `health/metrics.py` (AC: deferred to Story 7.2)
  - [x] In `src/aiops_triage_pipeline/health/metrics.py`, define `HealthMetrics` class that wraps OpenTelemetry gauge
  - [x] Create `opentelemetry.metrics.Meter` using `opentelemetry.metrics.get_meter(__name__)`
  - [x] Define `component_health_gauge`: UpDownCounter/ObservableGauge for component status (0=HEALTHY, 1=DEGRADED, 2=UNAVAILABLE)
  - [x] Expose `record_status(component: str, status: HealthStatus) -> None` function
  - [x] **Scope for 1.6**: metric definitions and recording only — full OTLP exporter + Dynatrace wiring is Story 7.2

- [x] Task 6: Update `__init__.py` exports (AC: all)
  - [x] `src/aiops_triage_pipeline/health/__init__.py`: export `HealthRegistry`, `get_health_registry`
  - [x] `src/aiops_triage_pipeline/models/__init__.py`: export `HealthStatus`, `ComponentHealth`, `DegradedModeEvent`, `TelemetryDegradedEvent`
  - [x] Both files are currently 1-line stubs — replace completely

- [x] Task 7: Create unit tests (AC: #6)
  - [x] Create `tests/unit/health/conftest.py`:
    - `registry()` fixture: returns a fresh `HealthRegistry()` instance (NOT the singleton — avoids cross-test pollution)
  - [x] Create `tests/unit/health/test_registry.py`:
    - `test_update_sets_healthy_status` — update to HEALTHY, get() returns HEALTHY
    - `test_update_sets_degraded_status` — update to DEGRADED, get() returns DEGRADED
    - `test_update_sets_unavailable_status` — update to UNAVAILABLE, get() returns UNAVAILABLE
    - `test_get_unknown_component_returns_none` — get() on unknown component returns None
    - `test_is_degraded_true_for_degraded` — DEGRADED → is_degraded() returns True
    - `test_is_degraded_true_for_unavailable` — UNAVAILABLE → is_degraded() returns True
    - `test_is_degraded_false_for_healthy` — HEALTHY → is_degraded() returns False
    - `test_is_degraded_false_for_unknown` — unknown component → is_degraded() returns False
    - `test_get_all_returns_snapshot` — get_all() returns all registered components
    - `test_concurrent_updates_no_corruption` — asyncio.gather 20 concurrent updates, no ValueError/KeyError raised, final status is valid
    - `test_degraded_mode_event_creation` — DegradedModeEvent can be instantiated with all required fields
    - `test_telemetry_degraded_event_creation` — TelemetryDegradedEvent can be instantiated with all required fields
    - `test_component_health_is_frozen` — attempting to mutate ComponentHealth raises ValidationError
  - [x] Verify `tests/unit/health/__init__.py` exists (it does — from Story 1.1)

- [x] Task 8: Verify quality gates
  - [x] Run `uv run ruff check src/aiops_triage_pipeline/health/ src/aiops_triage_pipeline/models/` — zero errors
  - [x] Run `uv run pytest tests/unit/health/ -v` — all tests pass (16/16)
  - [x] Run `uv run pytest -m "not integration"` — no regressions in full unit test suite (121/121)

## Dev Notes

### PREREQUISITE: Stories 1.2–1.5 patterns established

- `frozen=True` on class declaration: `class Foo(BaseModel, frozen=True)` — NOT `model_config = ConfigDict(frozen=True)`
- `tuple[str, ...]` for immutable sequences; `dict[str, X]` for mutable registries
- `Literal["v1"] = "v1"` for schema_version (not needed here — health models are internal, no schema_version)
- Fixtures always in `conftest.py` — never inside test files
- `uv run ruff check` must pass before review (line-length 100, target py313, Ruff 0.15.x)
- `str | None` not `Optional[str]`
- `functools.cache` for singletons (established by `get_settings()` in `config/settings.py`)

### `models/health.py` — HealthStatus and ComponentHealth

```python
"""Internal health domain models — not part of the frozen contracts package."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


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
    updated_at: datetime
```

**Why NOT in `contracts/`:**
The `contracts/` package holds the 12 frozen Pydantic models for external event interchange
(CaseHeaderEventV1, TriageExcerptV1, etc.). Internal domain models (ComponentHealth, EvidenceSnapshot,
PeakResult, DegradedModeEvent) live in `models/`. This is explicitly called out in the architecture.

### `models/events.py` — DegradedModeEvent and TelemetryDegradedEvent

```python
"""Internal operational event models for degraded-mode transitions."""

from datetime import datetime

from pydantic import BaseModel


class DegradedModeEvent(BaseModel, frozen=True):
    """Emitted when a component transitions to DEGRADED or UNAVAILABLE state.

    Used by:
    - Story 5.5: Redis unavailability → capped to NOTIFY-only
    - Future stories: any DegradableError handler

    Attributes:
        affected_scope: Component or subsystem that degraded (e.g., "redis", "llm")
        reason: Why the component degraded (e.g., "ConnectionRefusedError on port 6379")
        capped_action_level: Maximum action level now in effect (e.g., "NOTIFY-only")
        estimated_impact_window: Optional estimate of degradation duration (e.g., "unknown", "5m")
        timestamp: UTC time when the transition occurred
    """

    affected_scope: str
    reason: str
    capped_action_level: str
    estimated_impact_window: str | None = None
    timestamp: datetime


class TelemetryDegradedEvent(BaseModel, frozen=True):
    """Emitted when Prometheus becomes totally unavailable (FR67a).

    Used by:
    - Story 2.7: Prometheus unavailability detection

    Attributes:
        affected_scope: Always "prometheus" for this event type
        reason: Why Prometheus is unavailable (e.g., "HTTP 503 after 3 retries")
        recovery_status: Current recovery state: "pending" | "resolved"
        timestamp: UTC time of the detection
    """

    affected_scope: str
    reason: str
    recovery_status: str  # "pending" | "resolved"
    timestamp: datetime
```

**Why "emittable" and not "emitted" in Story 1.6:**
The DegradedModeEvent and TelemetryDegradedEvent Pydantic models are *defined* in this story.
The actual emission to logs and Slack happens in the stories that wire them:
- Story 5.5 (Redis degraded mode) creates and dispatches DegradedModeEvent
- Story 2.7 (Prometheus unavailability) creates and dispatches TelemetryDegradedEvent

### `health/registry.py` — HealthRegistry Singleton

```python
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

        Returns a dict keyed by component name. Safe to iterate — the underlying
        dict is replaced on update, not mutated in place.
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
```

**CRITICAL — asyncio.Lock() vs threading.Lock():**
- ✅ `asyncio.Lock()` — correct for asyncio-based pipeline (single event loop, cooperative multitasking)
- ❌ `threading.Lock()` — wrong for asyncio; would cause deadlocks if awaited in a coroutine

In Python 3.13, `asyncio.Lock()` can be created before the event loop starts (no deprecation warning).

**CRITICAL — Singleton and tests:**
`get_health_registry()` uses `@functools.cache`. In tests, NEVER call it directly — the cached singleton
carries state between tests. Instead, construct `HealthRegistry()` directly in fixtures.

### `health/server.py` — /health HTTP Endpoint

```python
"""Lightweight /health HTTP endpoint — asyncio raw TCP, no external HTTP framework."""

import asyncio
import json

from aiops_triage_pipeline.health.registry import get_health_registry


async def _handle_health_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single HTTP GET /health request."""
    # Read and discard HTTP request headers (we don't inspect method or path)
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break

    registry = get_health_registry()
    statuses = {
        name: health.model_dump(mode="json")
        for name, health in registry.get_all().items()
    }
    body = json.dumps(statuses, default=str).encode("utf-8")

    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        b"Connection: close\r\n"
        b"\r\n"
        + body
    )
    writer.write(response)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> asyncio.Server:
    """Start the asyncio-based /health HTTP endpoint server.

    Args:
        host: Bind address (default 0.0.0.0 — all interfaces)
        port: Port to listen on (default 8080)

    Returns:
        asyncio.Server instance — caller is responsible for closing on shutdown.

    Usage:
        server = await start_health_server(port=8080)
        async with server:
            await server.serve_forever()
    """
    return await asyncio.start_server(_handle_health_request, host, port)
```

**Why raw asyncio and NOT aiohttp/fastapi:**
`pyproject.toml` contains no HTTP framework dependency — aiohttp, fastapi, uvicorn are not listed.
Adding them for a single `/health` endpoint violates the "minimal dependencies" principle.
`asyncio.start_server()` is part of the Python stdlib — zero new dependencies, fully asyncio-native.
The health endpoint only needs to return JSON (no routing, no middleware, no auth).

### `health/metrics.py` — OTLP Health Metrics Stub

```python
"""OTLP metric definitions for component health monitoring.

Story 1.6 scope: define metrics and recording function.
Story 7.2 scope: configure OTLP exporter + Dynatrace pipeline resource attributes.
"""

from opentelemetry import metrics

from aiops_triage_pipeline.models.health import HealthStatus

# Meter — name matches package for traceability in Dynatrace dashboards
_meter = metrics.get_meter("aiops_triage_pipeline.health")

# Numeric encoding: HEALTHY=0, DEGRADED=1, UNAVAILABLE=2
_STATUS_VALUES: dict[HealthStatus, int] = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNAVAILABLE: 2,
}

# UpDownCounter tracks current status per component (not cumulative)
_component_health_gauge = _meter.create_up_down_counter(
    name="aiops.component.health_status",
    description="Current health status per component: 0=HEALTHY, 1=DEGRADED, 2=UNAVAILABLE",
    unit="1",
)


def record_status(component: str, status: HealthStatus) -> None:
    """Record component health status as an OTLP metric.

    Called by HealthRegistry.update() after storing the new status.
    Full OTLP exporter pipeline (resource, OTLP endpoint, Dynatrace headers)
    is configured in Story 7.2.

    Args:
        component: Component identifier matching HealthRegistry component name
        status: The new health status to record
    """
    _component_health_gauge.add(
        _STATUS_VALUES[status],
        attributes={"component": component, "status": status.value},
    )
```

**Story 7.2 deferred work:**
The OTLP SDK `MeterProvider` with `OTLPMetricExporter` and Dynatrace resource attributes
(`service.name`, `service.version`, `deployment.environment`) is configured in Story 7.2.
In Story 1.6, the `metrics.get_meter()` call uses the NoOp provider (default SDK behavior
when no MeterProvider is configured) — metrics are recorded but not exported. This is intentional.

### `health/__init__.py` — Exports

```python
"""HealthRegistry + telemetry — asyncio-safe component health tracking."""

from aiops_triage_pipeline.health.registry import HealthRegistry, get_health_registry

__all__ = [
    "HealthRegistry",
    "get_health_registry",
]
```

### `models/__init__.py` — Exports

```python
"""Internal domain models for aiops-triage-pipeline."""

from aiops_triage_pipeline.models.events import DegradedModeEvent, TelemetryDegradedEvent
from aiops_triage_pipeline.models.health import ComponentHealth, HealthStatus

__all__ = [
    "ComponentHealth",
    "DegradedModeEvent",
    "HealthStatus",
    "TelemetryDegradedEvent",
]
```

**Note on existing models in `models/`:**
- `models/case_file.py` — currently a stub (Story 4.1 implements it)
- `models/evidence.py` — currently a stub (Story 2.1 implements it)
- `models/peak.py` — currently a stub (Story 2.3 implements it)
- `models/health.py` — **implement now** (this story)
- `models/events.py` — **implement now** (this story)

Do NOT modify `case_file.py`, `evidence.py`, or `peak.py` — they are stubs owned by other stories.

### Import Boundary Rules (CRITICAL)

`health/` is a **provider package** — consumed by pipeline stages, diagnosis, outbox:

- ✅ `from aiops_triage_pipeline.models.health import ComponentHealth, HealthStatus`
- ✅ `from aiops_triage_pipeline.models.events import DegradedModeEvent, TelemetryDegradedEvent`
- ✅ `from opentelemetry import metrics` (external — opentelemetry-sdk already in pyproject.toml)
- ✅ `import asyncio`, `import functools`, `import json`, `from datetime import datetime, timezone`
- ❌ **NO** imports from `aiops_triage_pipeline.pipeline` (avoid circular dependency — pipeline imports health)
- ❌ **NO** imports from `aiops_triage_pipeline.denylist` (denylist is a leaf package; health doesn't apply denylist)
- ❌ **NO** imports from `aiops_triage_pipeline.contracts` (contracts are external event schemas; health is internal)
- ❌ **NO** imports from `aiops_triage_pipeline.diagnosis` or `aiops_triage_pipeline.outbox`

`models/` is a **near-leaf package**:
- ✅ `from pydantic import BaseModel`
- ✅ `from enum import Enum`
- ✅ `from datetime import datetime`
- ❌ **NO** imports from any other `aiops_triage_pipeline.*` package (models has no internal deps)

### Unit Test Pattern

**`tests/unit/health/conftest.py`** — shared fixtures:
```python
import pytest

from aiops_triage_pipeline.health.registry import HealthRegistry


@pytest.fixture
def registry() -> HealthRegistry:
    """Fresh HealthRegistry instance per test.

    IMPORTANT: Do NOT use get_health_registry() in unit tests — the @functools.cache
    singleton retains state across tests. Construct a fresh instance here.
    """
    return HealthRegistry()
```

**`tests/unit/health/test_registry.py`** — all tests async (asyncio_mode = "auto" in pyproject.toml):
```python
import asyncio
from datetime import datetime, timezone

import pytest

from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.models.events import DegradedModeEvent, TelemetryDegradedEvent
from aiops_triage_pipeline.models.health import ComponentHealth, HealthStatus
from pydantic import ValidationError


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


async def test_update_overwrites_previous_status(registry: HealthRegistry) -> None:
    """Multiple update() calls on same component keep the latest status."""
    await registry.update("redis", HealthStatus.DEGRADED, reason="initial")
    await registry.update("redis", HealthStatus.HEALTHY)
    assert registry.get("redis") == HealthStatus.HEALTHY
    assert registry.get_all()["redis"].reason is None
```

**Asyncio test setup:**
`pyproject.toml` has `asyncio_mode = "auto"` — all `async def test_*` functions run automatically
as async tests. No `@pytest.mark.asyncio` decorator needed. `pytest-asyncio==1.3.0` is already in dev deps.

### What Is NOT In Scope for Story 1.6

- **OTLP exporter configuration** (Story 7.2): `MeterProvider` with `OTLPMetricExporter`, resource attributes (`service.name`, `service.version`), OTLP endpoint env vars. Only metric definitions are in scope here.
- **OpenTelemetry tracing** (Story 7.2): Span creation, trace propagation, W3C TraceContext headers.
- **Wiring health into pipeline stages** (Stories 5.5, 2.7, 6.1, 6.3): Health registry is defined here; pipeline stages call `get_health_registry()` in their respective stories.
- **Integration test** (`tests/integration/test_degraded_modes.py`): Redis-down → NOTIFY-only end-to-end test is Story 5.5 scope.
- **OpenTelemetry Collector container** for OTLP export testing (Story 7.2 and integration tests).
- **`pipeline/scheduler.py`** interaction with HealthRegistry (Story 5.1+): The scheduler's lifecycle management of HealthRegistry (registering recovery on reconnect) is a pipeline concern.

### Project Structure — Files to Create/Modify

```
src/aiops_triage_pipeline/models/
├── __init__.py               # UPDATE: export HealthStatus, ComponentHealth, DegradedModeEvent, TelemetryDegradedEvent
│                             # Currently a 1-line stub — replace completely
├── health.py                 # IMPLEMENT: HealthStatus enum + ComponentHealth frozen model
│                             # Currently a 1-line stub
└── events.py                 # IMPLEMENT: DegradedModeEvent + TelemetryDegradedEvent frozen models
                              # Currently a 1-line stub

src/aiops_triage_pipeline/health/
├── __init__.py               # UPDATE: export HealthRegistry, get_health_registry
│                             # Currently a 1-line stub — replace completely
├── registry.py               # IMPLEMENT: HealthRegistry class + get_health_registry() singleton
│                             # Currently a 1-line stub
├── metrics.py                # IMPLEMENT: OTLP health metrics stub (record_status function)
│                             # Currently a 1-line stub
└── server.py                 # IMPLEMENT: start_health_server() using asyncio.start_server
                              # Currently a 1-line stub

tests/unit/health/
├── __init__.py               # EXISTS: no changes (empty, from Story 1.1)
├── conftest.py               # CREATE: fresh HealthRegistry() fixture
└── test_registry.py          # CREATE: 14 unit tests covering all ACs
```

**Files NOT touched:**
- `contracts/` — health models NOT added here (contracts/ holds the 12 external event contracts only)
- `models/case_file.py`, `models/evidence.py`, `models/peak.py` — stubs owned by other stories
- `errors/exceptions.py` — already fully implemented (Story 1.1+); no changes needed
- `config/settings.py` — no health-related settings needed for Story 1.6

### Ruff Compliance Notes

Same rules as Stories 1.2–1.5:
- Python 3.13 native types: `dict`, `list`, `frozenset` — no `from typing import Dict, List`
- `str | None` not `Optional[str]`
- Line length 100 chars max
- Enum: `class HealthStatus(str, Enum)` — `str` first (JSON serializable as string value)
- `asyncio.Lock` is top-level import (always used in HealthRegistry)
- `functools.cache` is top-level import (always used for singleton)
- All imports used — no unused imports
- `datetime.now(tz=timezone.utc)` — always UTC-aware, never naive datetime

### Previous Story Intelligence (from Stories 1.2–1.5)

**Established patterns to follow exactly:**
- `frozen=True` on class declaration (confirmed working in Stories 1.2, 1.3, 1.5)
- `tuple[str, ...]` for immutable sequences (not `list[str]`) — not needed here (no tuple fields)
- `Literal["v1"] = "v1"` for schema_version — not applicable (health models are internal, no versioning)
- Fixtures in `conftest.py` — never in test files (confirmed pattern in Story 1.5)
- `uv run ruff check` must pass before review
- `str | None` not `Optional[str]`
- `functools.cache` for singletons (confirmed by `get_settings()` in `config/settings.py`)

**New patterns for Story 1.6 (not in previous stories):**
- `asyncio.Lock()` for asyncio-safe registry writes (first async concurrency pattern in this project)
- `async def update()` — first async method in the codebase
- `asyncio_mode = "auto"` already configured — no additional test decorator needed
- `asyncio.gather()` for concurrent test execution
- `datetime.now(tz=timezone.utc)` for UTC-aware timestamps (not `datetime.utcnow()` — deprecated in 3.12)

**Critical difference from previous stories:**
Story 1.6 introduces the first **mutable runtime state** in the pipeline. Unlike the frozen Pydantic models in Stories 1.2–1.5, HealthRegistry holds mutable state that changes at runtime. The immutability discipline is maintained by making `ComponentHealth` frozen — each state change creates a new `ComponentHealth` instance rather than mutating an existing one.

### Git Context (Recent Commits)

- `77ec583 Story 1.5: Exposure Denylist Foundation — reviewed and done` — denylist foundation complete
- `370d20a Story 1.4: Code review fixes — config & settings hardening` — settings validation patterns established
- `085576b 1.3 - low bug fixed` — policy contract models complete
- `018d383 Story 1.3: Policy & Operational Contract Models — reviewed and done` — YAML loading pattern
- `8a581b9 Story 1.2: Code review fixes — contract validation hardening` — frozen Pydantic patterns

**Confirmed existing implementations (do not re-implement):**
- `src/aiops_triage_pipeline/errors/exceptions.py` — fully implemented (PipelineError hierarchy including `DegradableError`, `RedisUnavailable`, `LLMUnavailable`)
- `src/aiops_triage_pipeline/config/settings.py` — fully implemented (Settings, get_settings, load_policy_yaml)
- `src/aiops_triage_pipeline/denylist/` — fully implemented (DenylistV1, load_denylist, apply_denylist)
- All 12 contracts in `src/aiops_triage_pipeline/contracts/` — fully implemented

### References

- HealthRegistry singleton (asyncio-safe, HEALTHY/DEGRADED/UNAVAILABLE): [Source: `artifact/planning-artifacts/architecture.md#Decision 4C`]
- `health/` package structure (`registry.py`, `metrics.py`, `server.py`): [Source: `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`]
- `models/health.py` (HealthStatus, ComponentHealth) and `models/events.py` (DegradedModeEvent, TelemetryDegradedEvent): [Source: `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`]
- Import rules — health/ as provider package for pipeline/, diagnosis/, outbox/: [Source: `artifact/planning-artifacts/architecture.md#Import Rules`]
- FR51 (DegradedModeEvent to logs and Slack when Redis unavailable): [Source: `artifact/planning-artifacts/epics.md#FR51`]
- FR67a (TelemetryDegradedEvent when Prometheus unavailable, cap to OBSERVE/NOTIFY): [Source: `artifact/planning-artifacts/epics.md#FR67a`]
- FR34 (Redis unavailability → cap to NOTIFY-only per AG5): [Source: `artifact/planning-artifacts/epics.md#FR34`]
- Story 2.7 depends on HealthRegistry (Prometheus status = UNAVAILABLE): [Source: `artifact/planning-artifacts/epics.md#Story 2.7`]
- Story 5.5 depends on HealthRegistry (Redis DEGRADED → NOTIFY-only, DegradedModeEvent): [Source: `artifact/planning-artifacts/epics.md#Story 5.5`]
- Story 6.1 registers fire-and-forget cold-path tasks with HealthRegistry: [Source: `artifact/planning-artifacts/epics.md#Story 6.1`]
- DegradableError → HealthRegistry updated, pipeline continues with caps: [Source: `artifact/planning-artifacts/architecture.md#Error Handling Patterns`]
- opentelemetry-sdk==1.39.1 already in pyproject.toml: [Source: `pyproject.toml#dependencies`]
- pytest-asyncio==1.3.0 + asyncio_mode="auto" already configured: [Source: `pyproject.toml#tool.pytest.ini_options`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No blockers encountered. All stubs replaced in single pass per Dev Notes specifications.

### Completion Notes List

- Implemented `models/health.py`: `HealthStatus(str, Enum)` + `ComponentHealth(BaseModel, frozen=True)` per architecture spec
- Implemented `models/events.py`: `DegradedModeEvent` + `TelemetryDegradedEvent` — both `frozen=True` on class declaration
- Implemented `health/registry.py`: `HealthRegistry` with asyncio.Lock for write-safe updates; `get_health_registry()` singleton via `@functools.cache`
- Implemented `health/server.py`: raw asyncio TCP server returning JSON health snapshot; no HTTP framework added
- Implemented `health/metrics.py`: OTLP UpDownCounter stub via NoOp provider; full export wiring deferred to Story 7.2
- Updated `health/__init__.py` and `models/__init__.py` with proper exports
- Created `tests/unit/health/conftest.py` with fresh `HealthRegistry()` fixture (avoids singleton state bleed)
- Created `tests/unit/health/test_registry.py` with 16 tests covering all ACs including concurrent safety
- All 16 new tests pass; full regression suite 121/121 green; ruff zero violations

### File List

- `src/aiops_triage_pipeline/models/health.py`
- `src/aiops_triage_pipeline/models/events.py`
- `src/aiops_triage_pipeline/models/__init__.py`
- `src/aiops_triage_pipeline/health/registry.py`
- `src/aiops_triage_pipeline/health/server.py`
- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/health/__init__.py`
- `tests/unit/health/conftest.py`
- `tests/unit/health/test_registry.py`
- `tests/unit/health/test_server.py`
- `artifact/implementation-artifacts/sprint-status.yaml`

## Change Log

- **2026-03-01**: Story 1.6 implemented — HealthRegistry singleton (asyncio-safe), ComponentHealth/HealthStatus domain models, DegradedModeEvent/TelemetryDegradedEvent event models, /health asyncio TCP server, OTLP metrics stub, full exports, 16 unit tests (121/121 suite green, ruff clean).
- **2026-03-01**: Code review fixes (HIGH/MEDIUM) — 5 issues resolved: (H1) metrics.py delta-based UpDownCounter to correctly represent current status; (H2) server.py try/finally ensures writer always closed on handler exception; (M1) server.py default host changed to 127.0.0.1; (M2) registry.py wires record_status() call after update; (M3) test_server.py added with 5 tests covering AC3 (126/126 suite green, ruff clean).
- **2026-03-01**: Code review fixes (LOW) — 5 issues resolved: (L1) registry.py get_all() docstring corrected; (L2) models/health.py updated_at uses AwareDatetime to reject naive datetimes; (L3) test_registry.py added test_concurrent_updates_multiple_components for multi-component concurrency; (L4) health/__init__.py exports start_health_server; (L5) Dev Notes registry.py snippet corrected to match actual imports (127/127 suite green, ruff clean).
