# Story 5.4: Expose Health, Metrics, and Runtime Alert Evaluation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want comprehensive runtime health and observability signals,
so that I can detect issues quickly and validate system SLO behavior.

**Implements:** FR54, FR55, FR56, FR57, FR58

## Acceptance Criteria

1. **Given** any runtime mode pod is running
   **When** `/health` is queried
   **Then** component health registry state is returned
   **And** hot-path includes coordination informational fields that do not alter K8s probe pass/fail semantics.

2. **Given** cycles and dispatch activity execute
   **When** telemetry/log emission occurs
   **Then** OTLP metrics for pipeline health are exported and structured logs include `case_id`, `pod_name`, and `pod_namespace`
   **And** operational alert thresholds are evaluated against live metric state with observable status updates.

## Tasks / Subtasks

- [x] Task 1: Add `HEALTH_SERVER_HOST` and `HEALTH_SERVER_PORT` to `Settings` (AC: 1)
  - [x] In `src/aiops_triage_pipeline/config/settings.py`, add two new fields to the `Settings` class
        immediately after the existing `STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES` field (before the OTLP block):
        ```python
        HEALTH_SERVER_HOST: str = "0.0.0.0"  # bind all interfaces for K8s liveness probes
        HEALTH_SERVER_PORT: int = 8080
        ```
  - [x] In `validate_kerberos_files()` (the catch-all validator), add port range check before the
        `OTLP_METRICS_EXPORT_INTERVAL_MILLIS` check:
        ```python
        if not 1 <= self.HEALTH_SERVER_PORT <= 65535:
            raise ValueError("HEALTH_SERVER_PORT must be between 1 and 65535")
        ```
  - [x] In `log_active_config()`, add to the log call (after `STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES`):
        ```python
        HEALTH_SERVER_HOST=self.HEALTH_SERVER_HOST,
        HEALTH_SERVER_PORT=self.HEALTH_SERVER_PORT,
        ```

- [x] Task 2: Add `coordination_info_fn` to `health/server.py` (AC: 1 — FR55)
  - [x] Add `from typing import Any, Callable` import at the top of `health/server.py`
  - [x] Modify `_handle_health_request` to accept a new keyword-only parameter:
        ```python
        async def _handle_health_request(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
            *,
            coordination_info_fn: Callable[[], dict[str, Any]] | None = None,
        ) -> None:
        ```
  - [x] In `_handle_health_request`, after building the `statuses` dict from `registry.get_all()`,
        add coordination info when provided:
        ```python
        if coordination_info_fn is not None:
            statuses["_coordination"] = coordination_info_fn()
        ```
        Place this immediately before `body = json.dumps(statuses, default=str).encode("utf-8")`.
  - [x] Modify `start_health_server` signature to accept the new keyword-only parameter:
        ```python
        async def start_health_server(
            host: str = "127.0.0.1",
            port: int = 8080,
            *,
            coordination_info_fn: Callable[[], dict[str, Any]] | None = None,
        ) -> asyncio.Server:
        ```
  - [x] Replace the direct `_handle_health_request` reference in `asyncio.start_server()` with a
        closure that captures `coordination_info_fn`:
        ```python
        async def _handle(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            await _handle_health_request(
                reader, writer, coordination_info_fn=coordination_info_fn
            )
        return await asyncio.start_server(_handle, host, port)
        ```
        The existing `start_health_server` docstring should be preserved unchanged.

- [x] Task 3: Bind pod identity in `logging/setup.py` (AC: 2 — FR57/NFR-A6)
  - [x] Add `import os` at the top of `logging/setup.py` (after the existing stdlib imports)
  - [x] At the **end** of `configure_logging()`, after `structlog.configure(...)`, add:
        ```python
        pod_name = os.getenv("POD_NAME")
        pod_namespace = os.getenv("POD_NAMESPACE")
        _pod_bindings: dict[str, str] = {}
        if pod_name:
            _pod_bindings["pod_name"] = pod_name
        if pod_namespace:
            _pod_bindings["pod_namespace"] = pod_namespace
        if _pod_bindings:
            structlog.contextvars.bind_contextvars(**_pod_bindings)
        ```
        This binds pod identity once at process startup so all subsequent log events (including
        child asyncio tasks) carry `pod_name` and `pod_namespace` automatically via
        `merge_contextvars`. Called before `asyncio.run()` in every mode, so the binding is
        inherited by all tasks.

- [x] Task 4: Add pod identity to OTLP resource attributes in `health/otlp.py` (AC: 2 — NFR-A6)
  - [x] Add `import os` at the top of `health/otlp.py` (after the existing stdlib imports)
  - [x] In `configure_otlp_metrics()`, replace the inline dict in `Resource.create(...)` with a
        dynamically-built dict that includes pod identity when env vars are set.
        **Locate** the `Resource.create(...)` call inside the `with _bootstrap_lock:` block and
        replace it with:
        ```python
        _resource_attrs: dict[str, str] = {
            "service.name": settings.OTLP_SERVICE_NAME,
            "service.version": settings.OTLP_SERVICE_VERSION,
            "deployment.environment": settings.OTLP_DEPLOYMENT_ENVIRONMENT,
        }
        _pod_name = os.getenv("POD_NAME")
        _pod_namespace = os.getenv("POD_NAMESPACE")
        if _pod_name:
            _resource_attrs["k8s.pod.name"] = _pod_name
        if _pod_namespace:
            _resource_attrs["k8s.namespace.name"] = _pod_namespace
        provider = MeterProvider(
            resource=Resource.create(_resource_attrs),
            metric_readers=[reader],
        )
        ```
        Use local variable names prefixed with `_` to avoid shadowing module-level names.

- [x] Task 5: Wire health server and coordination state in `__main__.py` (AC: 1, 2 — FR54, FR55)
  - [x] Add `from aiops_triage_pipeline.health.server import start_health_server` import
        (group with other `health.*` imports at the top of `__main__.py`).
  - [x] Add `import threading` import (with other stdlib imports).
  - [x] Define `_HotPathCoordinationState` class before `_run_hot_path()`. This is a mutable
        container updated by the hot-path scheduler each cycle and read by the health server
        request handler (same asyncio event loop — no concurrent access concern):
        ```python
        class _HotPathCoordinationState:
            """Coordination state snapshot for the hot-path health endpoint (FR55).

            Written from the asyncio event loop each cycle. Read by the health server
            handler on the same event loop — no concurrent mutation.
            Field semantics match the cycle-lock protocol outcomes.
            """

            def __init__(self, *, enabled: bool = False) -> None:
                self.enabled = enabled
                self.is_lock_holder: bool = False
                self.lock_holder_id: str | None = None
                self.lock_ttl_seconds: int | None = None
                self.last_cycle_time_utc: str | None = None

            def snapshot(self) -> dict[str, Any]:
                return {
                    "enabled": self.enabled,
                    "is_lock_holder": self.is_lock_holder,
                    "lock_holder_id": self.lock_holder_id,
                    "lock_ttl_seconds": self.lock_ttl_seconds,
                    "last_cycle_time_utc": self.last_cycle_time_utc,
                }
        ```
  - [x] Define `_start_health_server_background(host: str, port: int) -> None` helper. This
        starts a health server in a daemon thread for **sync** runtime modes (outbox-publisher,
        casefile-lifecycle). Place it after `_HotPathCoordinationState`, before `_run_hot_path`:
        ```python
        def _start_health_server_background(host: str, port: int) -> None:
            """Start health server in a background daemon thread (for sync runtime modes).

            Uses a new event loop in a daemon thread — exits when the main thread exits.
            Not used for async modes (hot-path, cold-path) which use asyncio.create_task.
            """
            async def _serve() -> None:
                server = await start_health_server(host=host, port=port)
                async with server:
                    await server.serve_forever()

            t = threading.Thread(
                target=lambda: asyncio.run(_serve()),
                daemon=True,
                name="health-server",
            )
            t.start()
        ```
  - [x] **In `_run_hot_path()`:** Create `coordination_state` before the `asyncio.run()` call:
        ```python
        coordination_state = _HotPathCoordinationState(
            enabled=settings.DISTRIBUTED_CYCLE_LOCK_ENABLED
        )
        asyncio.run(
            _hot_path_scheduler_loop(
                ...
                coordination_state=coordination_state,   # add this
            )
        )
        ```
        The `coordination_state` is created outside `asyncio.run()` so it persists if the loop
        restarts (not that it does currently, but consistent with the existing pattern for
        `shard_coordinator`).
  - [x] **In `_hot_path_scheduler_loop()`:** Add `coordination_state: _HotPathCoordinationState`
        as the last keyword-only parameter. Then at the **top of the function body** (immediately
        after `_previous_shard_holders: dict[int, str] = {}` initialization, before `while True`):
        ```python
        # Wire health server (FR54/FR55) — runs concurrently with the scheduler loop.
        _health_server = await start_health_server(
            host=settings.HEALTH_SERVER_HOST,
            port=settings.HEALTH_SERVER_PORT,
            coordination_info_fn=coordination_state.snapshot,
        )
        asyncio.create_task(_health_server.serve_forever(), name="health-server")
        ```
  - [x] **In `_hot_path_scheduler_loop()` `while True` body:** After the line
        `evaluation_time = datetime.now(UTC)`, immediately update last cycle time:
        ```python
        coordination_state.last_cycle_time_utc = evaluation_time.isoformat()
        ```
  - [x] **In `_hot_path_scheduler_loop()` inside `if settings.DISTRIBUTED_CYCLE_LOCK_ENABLED:` block:**
        Update coordination state after each lock outcome (three branches):
        - After `if lock_outcome.status == CycleLockStatus.acquired:` log statement, add:
          ```python
          coordination_state.is_lock_holder = True
          coordination_state.lock_holder_id = cycle_lock_owner_id
          coordination_state.lock_ttl_seconds = lock_outcome.ttl_seconds
          ```
        - After `elif lock_outcome.status == CycleLockStatus.yielded:` log statement, add:
          ```python
          coordination_state.is_lock_holder = False
          coordination_state.lock_holder_id = lock_outcome.holder_id
          coordination_state.lock_ttl_seconds = lock_outcome.ttl_seconds
          ```
        - In the `fail_open` branch (after `record_cycle_lock_fail_open()`), add:
          ```python
          coordination_state.is_lock_holder = True  # fail-open: proceed as if lock held
          coordination_state.lock_holder_id = None
          coordination_state.lock_ttl_seconds = None
          ```
  - [x] **In `_cold_path_consumer_loop()`:** At the very **start of the function body** (before
        the `await registry.update("kafka_cold_path_connected", ...)` call), add:
        ```python
        # Wire health server (FR54) — runs concurrently with the consume loop.
        _health_server = await start_health_server(
            host=settings.HEALTH_SERVER_HOST,
            port=settings.HEALTH_SERVER_PORT,
        )
        asyncio.create_task(_health_server.serve_forever(), name="health-server")
        ```
  - [x] **In `_run_outbox_publisher()`:** Add health server start for daemon mode only, before
        the `if once:` branch:
        ```python
        if not once:
            _start_health_server_background(
                settings.HEALTH_SERVER_HOST, settings.HEALTH_SERVER_PORT
            )
        ```
  - [x] **In `_run_casefile_lifecycle()`:** Add health server start for daemon mode only, before
        the `if once:` branch:
        ```python
        if not once:
            _start_health_server_background(
                settings.HEALTH_SERVER_HOST, settings.HEALTH_SERVER_PORT
            )
        ```
  - [x] **In `tests/unit/test_main.py`:** Read all tests that call `_hot_path_scheduler_loop()`
        and update them:
        1. Import `_HotPathCoordinationState` from `aiops_triage_pipeline.__main__`
        2. Add `coordination_state=_HotPathCoordinationState()` to the call
        3. Patch `start_health_server` in the `aiops_triage_pipeline.__main__` namespace to avoid
           real socket binding. Pattern:
           ```python
           from unittest.mock import AsyncMock, MagicMock
           mock_server = MagicMock()
           mock_server.serve_forever = AsyncMock()
           mock_server.__aenter__ = AsyncMock(return_value=mock_server)
           mock_server.__aexit__ = AsyncMock(return_value=None)
           monkeypatch.setattr(
               "aiops_triage_pipeline.__main__.start_health_server",
               AsyncMock(return_value=mock_server),
           )
           ```
        4. Similarly patch `start_health_server` in any test that calls `_cold_path_consumer_loop()`
        5. Do NOT add `coordination_state` to tests that do NOT call `_hot_path_scheduler_loop()`
           directly — only the loop-level tests are affected.

- [x] Task 6: Write unit tests (AC: 1, 2)
  - [x] In `tests/unit/health/test_server.py`, add two tests after the existing tests:
    - `test_server_includes_coordination_info_when_fn_provided`:
      Start server with `coordination_info_fn=lambda: {"is_lock_holder": True, "lock_ttl_seconds": 120}`.
      Query `/health`. Assert body JSON contains `"_coordination"` key with
      `{"is_lock_holder": True, "lock_ttl_seconds": 120}`. Uses `patched_registry` fixture.
    - `test_server_excludes_coordination_key_when_fn_is_none`:
      Start server with no `coordination_info_fn` argument (defaults to `None`).
      Query `/health` on an empty registry.
      Assert `"_coordination"` key is NOT in the parsed body.
  - [x] In `tests/unit/logging/test_setup.py`, add three tests:
    - `test_configure_logging_binds_pod_name_when_env_var_set`:
      Use `monkeypatch.setenv("POD_NAME", "test-pod-1")`. Call `configure_logging()`.
      Assert `structlog.contextvars.get_contextvars().get("pod_name") == "test-pod-1"`.
      Clear contextvars after: `structlog.contextvars.clear_contextvars()`.
    - `test_configure_logging_binds_pod_namespace_when_env_var_set`:
      Use `monkeypatch.setenv("POD_NAMESPACE", "aiops-system")`. Call `configure_logging()`.
      Assert `structlog.contextvars.get_contextvars().get("pod_namespace") == "aiops-system"`.
      Clear contextvars after.
    - `test_configure_logging_does_not_bind_pod_name_when_env_var_absent`:
      Ensure `POD_NAME` is absent: `monkeypatch.delenv("POD_NAME", raising=False)`.
      Call `configure_logging()`.
      Assert `"pod_name"` is NOT in `structlog.contextvars.get_contextvars()`.
      Clear contextvars after.
  - [x] In `tests/unit/config/test_settings.py`, add two tests (or find the appropriate place
        following the existing settings test pattern):
    - `test_settings_health_server_default_host_is_0_0_0_0`:
      Instantiate `Settings()` (with `get_settings.cache_clear()` before and after).
      Assert `settings.HEALTH_SERVER_HOST == "0.0.0.0"`.
    - `test_settings_health_server_port_validation_rejects_out_of_range`:
      Assert `ValidationError` (or `ValueError`) when `HEALTH_SERVER_PORT=0`
      and when `HEALTH_SERVER_PORT=65536`.

- [x] Task 7: Run full regression (AC: 1, 2)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q tests/unit`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### What Already Exists — Do NOT Reimplement

**Health subsystem is fully implemented (Stories 5.1–5.3):**
- `health/registry.py` — `HealthRegistry` singleton, asyncio-safe, per-component HEALTHY/DEGRADED/UNAVAILABLE tracking. `get_health_registry()` returns the singleton.
- `health/server.py` — `start_health_server(host, port)` exists and works. The server always returns `HTTP 200 OK` with the registry contents as JSON. **It is NOT wired in any runtime mode** — this is the Story 5.4 gap.
- `health/metrics.py` — Extensive OTLP metrics for all pipeline components: cycle lock (`_coordination_cycle_lock_acquired_total`, etc.), evidence builder, pipeline stages, casefile lifecycle, servicenow, LLM, redis — all already defined and called from their respective modules. No new metric counters needed.
- `outbox/metrics.py` — Separate OTLP metrics for outbox delivery (queue depth, oldest age, publish latency, SLO breaches, publish outcomes) — already called from `outbox/worker.py`.
- `health/alerts.py` — `OperationalAlertEvaluator` fully implemented. Wired in **all four** runtime modes in `__main__.py` (hot-path, cold-path, outbox-publisher, casefile-lifecycle).
- `health/otlp.py` — `configure_otlp_metrics(settings)` called in `_bootstrap_mode()` for all modes. Already configures MeterProvider with OTLP exporter.
- `logging/setup.py` — `configure_logging()`, `bind_correlation_id()`, `clear_correlation_id()`. Pod identity (FR57/NFR-A6) binding is the **only gap** here — `configure_logging()` currently does not read `POD_NAME`/`POD_NAMESPACE`.

**The four gaps Story 5.4 closes:**
1. `start_health_server()` is never called in `__main__.py` for any runtime mode (FR54 gap).
2. Hot-path health response lacks coordination informational fields (lock holder, TTL, last cycle) — requires `coordination_info_fn` support in `server.py` and `_HotPathCoordinationState` in `__main__.py` (FR55 gap).
3. `configure_logging()` does not bind `pod_name`/`pod_namespace` to structlog context (FR57/NFR-A6 gap).
4. `configure_otlp_metrics()` does not include `k8s.pod.name`/`k8s.namespace.name` in OTLP resource attributes (NFR-A6 gap).

### Precise Architecture for Health Server Wiring

**Async modes (hot-path, cold-path):** Both use `asyncio.run()`. Start the health server with `asyncio.create_task()` inside the async main loop function. The task runs concurrently on the same event loop. When `asyncio.run()` exits (normally or via exception), the event loop cancels all pending tasks automatically — no explicit cleanup needed.

**Sync modes (outbox-publisher, casefile-lifecycle):** These are synchronous blocking loops (`worker.run_forever()` and `while True: runner.run_once()`). Start the health server in a daemon thread that runs its own event loop (`asyncio.run(_serve())`). The `daemon=True` flag ensures the thread exits when the main process exits without blocking shutdown. Do NOT start in `once` mode (used for tests and one-shot Kubernetes jobs).

**Hot-path coordination info (FR55 — key design constraint):** The `/health` endpoint MUST always return `HTTP 200 OK` regardless of coordination state — K8s liveness/readiness probes use HTTP status code, not body content. Adding `_coordination` to the body is safe because it never causes a 5xx response. The `_HotPathCoordinationState` object lives in `_run_hot_path()` scope, created before `asyncio.run()`, and passed to `_hot_path_scheduler_loop()` as a parameter — following the established dependency injection pattern (`shard_coordinator` does the same). The state is updated by the loop and read by the health server handler on the **same single-threaded asyncio event loop** — no locking required.

### Precise Change Description for `server.py`

The existing test `test_server_body_reflects_registry_state` patches `get_health_registry` via monkeypatch. This continues to work unchanged because the closure approach still calls `get_health_registry()` inside `_handle_health_request`. The four existing tests pass `coordination_info_fn=None` implicitly (the new default) and are unaffected.

The closure pattern in `start_health_server` is required because `asyncio.start_server` requires a callback with signature `(reader, writer)`. The closure captures `coordination_info_fn` from the outer scope:

```python
async def start_health_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    *,
    coordination_info_fn: Callable[[], dict[str, Any]] | None = None,
) -> asyncio.Server:
    """Start the asyncio-based /health HTTP endpoint server.
    ...
    """
    async def _handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await _handle_health_request(
            reader, writer, coordination_info_fn=coordination_info_fn
        )
    return await asyncio.start_server(_handle, host, port)
```

The `_coordination` key uses a leading underscore convention to signal it is metadata (not a component health entry) when parsing the JSON body.

### Precise Change Description for `test_main.py`

Tests calling `_hot_path_scheduler_loop()` directly must:
1. Add `from aiops_triage_pipeline.__main__ import _HotPathCoordinationState` import
2. Pass `coordination_state=_HotPathCoordinationState()` in the call
3. Patch `start_health_server` in the `__main__` module before the call

The tests raise `CancelledError` via mocked dependencies early in the loop (at `topology_loader.reload_if_changed()`). The health server start happens BEFORE `while True:` — it is NOT inside the loop. Therefore, `start_health_server` IS reached by all tests that call `_hot_path_scheduler_loop()`. The `AsyncMock` approach prevents real socket binding.

Mock server pattern (works with `asyncio.create_task(_health_server.serve_forever())`):
```python
mock_server = MagicMock()
mock_server.serve_forever = AsyncMock()
# _health_server_task = asyncio.create_task(mock_server.serve_forever()) will create a task
# that completes immediately since AsyncMock() returns a coroutine that returns immediately.
monkeypatch.setattr(
    "aiops_triage_pipeline.__main__.start_health_server",
    AsyncMock(return_value=mock_server),
)
```

### Technical Requirements

- FR54: Every runtime mode pod (hot-path, cold-path, outbox-publisher, casefile-lifecycle) exposes `/health` reporting `HealthRegistry` state.
- FR55: Hot-path `/health` response includes `_coordination` section with `enabled`, `is_lock_holder`, `lock_holder_id`, `lock_ttl_seconds`, `last_cycle_time_utc`. HTTP status is always 200 — K8s probe semantics unchanged.
- FR56: OTLP metrics are already defined and exported for all required areas (cycle completion, outbox delivery, gate evaluation latency, deduplication, coordination lock stats). No new metrics needed in this story.
- FR57: `pod_name` and `pod_namespace` are bound in structlog context at startup via `configure_logging()`. `case_id` is already propagated as `correlation_id` via `bind_correlation_id()`. No changes needed to `correlation_id` handling.
- NFR-A6: Pod identity stamped in OTLP resource attributes (`k8s.pod.name`, `k8s.namespace.name`) when `POD_NAME`/`POD_NAMESPACE` env vars are present.
- FR58: Alert evaluator already wired in all modes — no changes needed.

### Architecture Compliance

- **Composition root**: All new wiring (`start_health_server` calls) happens in `__main__.py` and the `asyncio.run()` entrypoints. No new module-level singletons.
- **Dependency injection**: `_HotPathCoordinationState` is passed as a constructor parameter to `_hot_path_scheduler_loop()`, not stored as a module singleton. Pattern is identical to `shard_coordinator: RedisShardCoordinator | None = None` already in the function signature.
- **No new packages/modules**: No new files created. All changes are to existing files.
- **`health/metrics.py` rule**: No new metric functions are needed. FR56 is satisfied by existing metrics.
- **`asyncio.create_task`**: Used for background health server in async modes, matching the established pattern for background tasks (line 80 of implementation-patterns-consistency-rules.md: "Background tasks: `asyncio.create_task` for baseline computation scheduling.").
- **Sync Redis**: No new Redis usage. The background thread for sync modes runs its own independent asyncio event loop — no mixing with any sync Redis clients.

### Library / Framework Requirements

- Locked stack (do not change):
  - Python `>=3.13` — use `X | None` union syntax; `Callable` from `collections.abc` or `typing`
  - `structlog~=24.0`: `structlog.contextvars.bind_contextvars()` and `get_contextvars()` are the established API (already used in `bind_correlation_id()` and `clear_correlation_id()`)
  - `opentelemetry-sdk`: `Resource.create(dict)` — same API, just adding optional keys
  - `asyncio.create_task(coro, name=str)` — Python 3.7+ API (well within range)
  - `pytest==9.0.2`, `AsyncMock` from `unittest.mock` (Python 3.8+)

### File Structure Requirements

**Modified files (no new files):**
- `src/aiops_triage_pipeline/config/settings.py` — add `HEALTH_SERVER_HOST`, `HEALTH_SERVER_PORT`, validation, log_active_config
- `src/aiops_triage_pipeline/health/server.py` — add `coordination_info_fn` parameter + closure
- `src/aiops_triage_pipeline/logging/setup.py` — add `import os`; pod identity binding in `configure_logging()`
- `src/aiops_triage_pipeline/health/otlp.py` — add `import os`; pod identity in Resource attributes
- `src/aiops_triage_pipeline/__main__.py` — add imports; add `_HotPathCoordinationState` class; add `_start_health_server_background()` helper; wire health server in all 4 modes; add `coordination_state` parameter to `_hot_path_scheduler_loop()`; update coordination state in lock outcome branches
- `tests/unit/health/test_server.py` — add 2 tests
- `tests/unit/logging/test_setup.py` — add 3 tests
- `tests/unit/config/test_settings.py` — add 2 tests
- `tests/unit/test_main.py` — update tests calling `_hot_path_scheduler_loop()` and `_cold_path_consumer_loop()` to patch `start_health_server`

**Do NOT modify:**
- `src/aiops_triage_pipeline/health/metrics.py` — all metrics already defined; no new counters needed
- `src/aiops_triage_pipeline/health/alerts.py` — alert evaluator fully wired; no changes
- `src/aiops_triage_pipeline/health/otlp.py` beyond the described pod identity change
- `src/aiops_triage_pipeline/health/registry.py` — no changes; `HealthRegistry` is complete
- `src/aiops_triage_pipeline/outbox/metrics.py` — no changes
- Any pipeline stage files (`stages/anomaly.py`, `stages/gating.py`, etc.) — not touched in this story
- `config/policies/operational-alert-policy-v1.yaml` — no policy changes

### Testing Requirements

**For `test_server.py` coordination tests:**
```python
async def test_server_includes_coordination_info_when_fn_provided(patched_registry):
    """_coordination key appears in body when coordination_info_fn is supplied."""
    server = await start_health_server(
        host="127.0.0.1",
        port=0,
        coordination_info_fn=lambda: {"is_lock_holder": True, "lock_ttl_seconds": 120},
    )
    port = server.sockets[0].getsockname()[1]
    async with server:
        _, body = await _http_get("127.0.0.1", port)
    data = json.loads(body)
    assert "_coordination" in data
    assert data["_coordination"]["is_lock_holder"] is True
    assert data["_coordination"]["lock_ttl_seconds"] == 120


async def test_server_excludes_coordination_key_when_fn_is_none(patched_registry):
    """_coordination key is absent from body when coordination_info_fn is None."""
    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        _, body = await _http_get("127.0.0.1", port)
    assert "_coordination" not in json.loads(body)
```

**For `test_setup.py` pod identity tests:**
- Use `monkeypatch.setenv("POD_NAME", "test-pod-1")` to set env vars
- Call `structlog.contextvars.clear_contextvars()` in test teardown (or use a fixture) to prevent state bleed
- Use `structlog.reset_defaults()` if testing structlog processor chain state; use `structlog.contextvars.clear_contextvars()` for context binding assertions
- Call `configure_logging()` in each test that relies on it; `configure_logging()` is idempotent within a test run due to `cache_logger_on_first_use=True`, so tests may need `structlog.reset_defaults()` before calling `configure_logging()` to force reprocessing — check existing `test_setup.py` patterns for how they handle this.

**No pytest.skip anywhere** — use `pytest.fail` if unexpected behavior is encountered.
**Per-file test doubles**: Any mock/stub defined in new tests must be defined in the same test file.
**`get_settings.cache_clear()`**: Any test instantiating `Settings()` directly must clear the settings cache before and after.
**Preferred regression command:**
```
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

### Previous Story Intelligence

**From Story 5.3 (done — anomaly policy wiring and topology version stamp):**
- Full regression: 1050 unit tests pass, 0 skipped (baseline for this story's delta).
- File list in Dev Agent Record must include ALL changed files including `sprint-status.yaml`.
- No `pytest.skip` anywhere — use `pytest.fail`.
- `uv run ruff check` must run clean before claiming done.
- `get_settings.cache_clear()` in any test that instantiates `Settings` directly.
- All new parameters added as keyword-only with defaults for backward-compatible call sites.

**From Story 5.2 (done — prod integration guardrails):**
- `_bootstrap_mode()` validates integration modes and wires `alert_evaluator` for ALL runtime modes. The `alert_evaluator` does not need to be re-wired.

**From Story 5.1 (done — policy startup loading):**
- `configure_otlp_metrics(settings)` is called in `_bootstrap_mode()` — it runs before `asyncio.run()` and before `start_health_server`. Pod identity env vars are read at OTLP config time (K8s injects them as env vars, not file-based). No timing concern.

### Git Intelligence Summary

Recent commits (most relevant to this story):
- `5215757`: fix(epic-5/5-3): resolve code review findings — 1050 unit tests after review
- `871b57a`: feat(epic-5/5-3): story dev done — anomaly threshold wiring + topology version stamp
- `0df61f4`: fix(epic-5/5-2): resolve code review findings — prod integration guardrails
- `0c0dd45`: feat(epic-5/5-2): story dev done — 1042 unit tests after review

No prior story touched `health/server.py`, `logging/setup.py`, or `health/otlp.py` pod identity paths. The `health/server.py` tests are already in place (5 tests for the basic server behavior). Story 5.4 adds the `coordination_info_fn` path.

No story touched `__main__.py` health server wiring — `start_health_server` import is not present in `__main__.py`. Add it with the other `health.*` imports at the top of the file.

### Latest Tech Information

External verification date: 2026-03-23.

- **`asyncio.create_task(coro, name=str)`**: The `name` keyword arg is Python 3.7+. Used for task identification in `asyncio.all_tasks()` dumps. Safe to use.
- **`structlog.contextvars.bind_contextvars(**kwargs)`**: The established pattern in this codebase (see `bind_correlation_id()` in `logging/setup.py` line 112). `bind_contextvars` modifies the current `contextvars.Context`. When called before `asyncio.run()`, the binding is present in the root context and inherited by all child tasks via `asyncio.create_task()`. This is the correct approach for process-wide constants like pod identity.
- **`structlog.contextvars.get_contextvars()`**: Returns a dict of all currently-bound context vars. Use in tests to assert pod identity binding.
- **OpenTelemetry Semantic Conventions**: `k8s.pod.name` and `k8s.namespace.name` are the OTEL semantic convention keys for Kubernetes pod identity (stable as of otel-python 1.x). Use these exact strings.
- **`threading.Thread(daemon=True)`**: A daemon thread is automatically killed when the main process exits. No `join()` needed. The pattern `target=lambda: asyncio.run(_serve())` is idiomatic for running an asyncio server in a background thread when the calling context is synchronous.

### Project Context Reference

Applied `archive/project-context.md` and implementation patterns:
- Python 3.13 typing — `X | None`, `Callable[[], dict[str, Any]]`, no `Optional`.
- No DI container — `_HotPathCoordinationState` propagates as a function parameter, not a module singleton.
- Single flat `Settings` class — two new fields added there, nothing else.
- `asyncio.create_task` for background work within async contexts.
- Daemon thread + new event loop for background work within sync contexts.
- No new Redis consumers, no new packages, no new files.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 5 / Story 5.4 (line 724)]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR54, FR55, FR56, FR57, FR58]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-A6]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
  — Dependency Injection, OTLP Metrics pattern, Async Patterns, Enforcement Guidelines]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`
  — Runtime mode boundaries table; `health/` package structure]
- [Source: `src/aiops_triage_pipeline/health/server.py`
  — `start_health_server()` exists (not wired), `_handle_health_request()` (line 9–40)]
- [Source: `src/aiops_triage_pipeline/health/registry.py`
  — `HealthRegistry`, `get_health_registry()` singleton]
- [Source: `src/aiops_triage_pipeline/health/metrics.py`
  — All existing metric functions; no new functions needed for FR56]
- [Source: `src/aiops_triage_pipeline/health/alerts.py`
  — `OperationalAlertEvaluator` fully implemented and wired; no changes for FR58]
- [Source: `src/aiops_triage_pipeline/health/otlp.py`
  — `configure_otlp_metrics()` (line 33); `Resource.create(...)` (line 59–67)]
- [Source: `src/aiops_triage_pipeline/logging/setup.py`
  — `configure_logging()` (line 36); `bind_correlation_id()` (line 112)]
- [Source: `src/aiops_triage_pipeline/config/settings.py`
  — `Settings` class; `validate_kerberos_files()` (line 170); `log_active_config()` (line 235)]
- [Source: `src/aiops_triage_pipeline/__main__.py`
  — `_bootstrap_mode()` (line 260+); `_run_hot_path()` (line 297); `_hot_path_scheduler_loop()` (line 415); lock outcome branches (lines 475–501); `_cold_path_consumer_loop()` (line 964); `_run_outbox_publisher()` (line 1236); `_run_casefile_lifecycle()` (line 1273)]
- [Source: `src/aiops_triage_pipeline/coordination/cycle_lock.py`
  — `CycleLockStatus.acquired`, `.yielded`, `.fail_open`; `lock_outcome.ttl_seconds`, `.holder_id`]
- [Source: `tests/unit/health/test_server.py`
  — Existing 5 tests; `_http_get()` helper; `patched_registry` fixture pattern]
- [Source: `artifact/implementation-artifacts/5-3-enable-operator-and-maintainer-policy-tuning-workflows.md`
  — Previous story dev notes; test patterns; 1050 unit test baseline]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- create-story workflow for story key `5-4-expose-health-metrics-and-runtime-alert-evaluation`
- sprint-status.yaml: story 5-4 status=backlog confirmed; epic-5 already in-progress
- epics.md (line 724): Story 5.4 AC text and FR54-FR58 mapping
- prd/functional-requirements.md: FR54 (health endpoint), FR55 (coordination info), FR56 (OTLP metrics), FR57 (structured logs with pod identity), FR58 (alert evaluation)
- prd/non-functional-requirements.md: NFR-A6 (pod identity in OTLP and logs)
- health/server.py: `start_health_server()` exists (line 43–58) but zero calls in __main__.py confirmed via grep
- health/metrics.py: All required FR56 metrics already defined (coordination, casefile, pipeline, evidence, prometheus, redis, LLM, servicenow)
- health/otlp.py: Resource.create dict (lines 59–67) — no pod identity keys; gap confirmed
- logging/setup.py: configure_logging() (line 36) — no os.getenv POD_NAME/POD_NAMESPACE; gap confirmed
- __main__.py: start_health_server not imported, not called in any runtime mode — FR54 gap confirmed
- coordination/cycle_lock.py: CycleLockStatus enum, lock_outcome fields (ttl_seconds, holder_id, status)
- previous story 5.3: 1050 unit tests baseline; test_main.py notes (CancelledError pattern before casefile path, but health server wired BEFORE while True loop — tests WILL hit start_health_server)
- git log: no prior story touched health/server.py coordination path or logging pod identity

### Completion Notes List

- All Tasks 1–7 verified complete. Tasks 1–5 were already implemented in source files; this session completed the missing test coverage (Task 6) and fixed 2 failing cold-path tests.
- Task 1: `HEALTH_SERVER_HOST`/`HEALTH_SERVER_PORT` fields, validation, and `log_active_config` entries confirmed in `settings.py`.
- Task 2: `coordination_info_fn` parameter + closure confirmed in `health/server.py`.
- Task 3: Pod identity `bind_contextvars` on `POD_NAME`/`POD_NAMESPACE` confirmed in `logging/setup.py`.
- Task 4: `k8s.pod.name`/`k8s.namespace.name` in OTLP resource attrs confirmed in `health/otlp.py`.
- Task 5: All `__main__.py` wiring confirmed. Fixed 2 failing cold-path tests (missing `HEALTH_SERVER_HOST`/`HEALTH_SERVER_PORT` in settings mock + missing `start_health_server` patch). Also patched `start_health_server` in shard tests helper and lock-disabled test.
- Task 6: Added 7 new tests — 2 coordination tests in `test_server.py`, 3 pod identity tests in `test_setup.py`, 2 health server settings tests in `test_settings.py`.
- Task 7: `uv run ruff check` clean for all modified files. `uv run pytest -q tests/unit`: 1057 passed, 0 skipped.

### File List

- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/health/server.py`
- `src/aiops_triage_pipeline/logging/setup.py`
- `src/aiops_triage_pipeline/health/otlp.py`
- `src/aiops_triage_pipeline/__main__.py`
- `tests/unit/health/test_server.py`
- `tests/unit/logging/test_setup.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/test_main.py`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `artifact/implementation-artifacts/5-4-expose-health-metrics-and-runtime-alert-evaluation.md`
