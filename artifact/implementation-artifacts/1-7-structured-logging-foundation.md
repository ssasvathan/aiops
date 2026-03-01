# Story 1.7: Structured Logging Foundation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want structured JSON logging with correlation_id propagation,
so that all pipeline events are consistently formatted and traceable across components per NFR-O3.

## Acceptance Criteria

1. **Given** structlog is configured as the logging framework
   **When** any pipeline component emits a log event
   **Then** the output is structured JSON with consistent fields: `timestamp`, `correlation_id` (when set), `component`, `event_type` (when passed), `severity`

2. **And** log levels are used correctly: ERROR for failures requiring attention, WARN for degraded behavior, INFO for normal processing, DEBUG for diagnostic detail

3. **And** correlation_id propagates through async contexts (asyncio task-local via `contextvars`)

4. **And** a logging factory/helper (`get_logger(component)`) is available for components to create properly configured loggers

5. **And** unit tests verify: JSON output format, field presence, correlation_id propagation, log level filtering

## Tasks / Subtasks

- [x] Task 1: Implement `logging/setup.py` — structlog configuration and helpers (AC: #1, #2, #3, #4)
  - [x] Implement `configure_logging(log_level: str = "INFO") -> None` — sets up structlog processor pipeline
  - [x] Implement `_add_severity` private processor — renames `level` → `severity` (uppercase, NFR-O3)
  - [x] Implement `get_logger(component: str) -> structlog.BoundLogger` — factory with component pre-bound
  - [x] Implement `bind_correlation_id(correlation_id: str) -> None` — bind to asyncio task context
  - [x] Implement `clear_correlation_id() -> None` — clear structlog context vars
  - [x] Implement `get_correlation_id() -> str | None` — read current correlation_id from context

- [x] Task 2: Update `logging/__init__.py` exports (AC: all)
  - [x] Export all 5 public functions: `configure_logging`, `get_logger`, `bind_correlation_id`, `clear_correlation_id`, `get_correlation_id`
  - [x] Replace completely — currently a 1-line stub

- [x] Task 3: Create unit tests (AC: #5)
  - [x] Create `tests/unit/logging/__init__.py` — empty file
  - [x] Create `tests/unit/logging/conftest.py`:
    - `reset_structlog` autouse fixture — resets structlog defaults, clears contextvars, clears root handlers after each test
    - `log_stream` fixture — StringIO handler on root logger, calls `configure_logging("INFO")`, returns stream
  - [x] Create `tests/unit/logging/test_setup.py`:
    - `test_json_output_format` — `json.loads()` must succeed on output line
    - `test_timestamp_field_present` — `timestamp` key present, contains `T` (ISO 8601)
    - `test_severity_field_present_and_uppercase` — `severity` is `"INFO"`, `level` key absent
    - `test_component_field_present` — `component` matches `get_logger(component)` arg
    - `test_event_type_field_passthrough` — kwargs passed to logger appear in JSON
    - `test_correlation_id_appears_in_output` — bound correlation_id appears in JSON
    - `test_no_correlation_id_when_not_bound` — `correlation_id` key absent when not set
    - `test_correlation_id_cleared_after_clear` — clear removes correlation_id from output
    - `test_get_correlation_id_returns_bound_value` — `get_correlation_id()` matches bound value
    - `test_get_correlation_id_returns_none_when_not_bound` — returns `None`
    - `test_debug_filtered_at_info_level` — `logger.debug(...)` produces no output at INFO level
    - `test_info_not_filtered_at_info_level` — `logger.info(...)` produces output
    - `test_warning_appears_at_info_level` — WARNING emitted, `severity == "WARNING"`
    - `test_async_context_propagation` — `asyncio.create_task()` child inherits correlation_id

- [x] Task 4: Verify quality gates
  - [x] Run `uv run ruff check src/aiops_triage_pipeline/logging/` — zero errors
  - [x] Run `uv run pytest tests/unit/logging/ -v` — all tests pass (15/15)
  - [x] Run `uv run pytest -m "not integration"` — no regressions in full unit test suite (142/142)

## Dev Notes

### Processor Pipeline Design (CRITICAL — get this order exactly right)

structlog's processor chain runs in order. Each processor receives `(logger, method, event_dict)` and returns `event_dict` (or raises `DropEvent` to discard the message):

```
1. merge_contextvars  — inject asyncio task-local fields (correlation_id) FIRST
2. filter_by_level    — drop events below configured level EARLY (avoid processing dropped events)
3. add_log_level      — add 'level' field ("info", "warning", etc.)
4. _add_severity      — rename 'level' → 'severity', uppercased ("INFO", "WARNING", etc.)
5. TimeStamper        — add ISO 8601 UTC 'timestamp' field
6. StackInfoRenderer  — format stack_info if present
7. JSONRenderer       — render final event_dict as JSON string
```

**CRITICAL: `filter_by_level` placement** — must be AFTER `merge_contextvars` but BEFORE any expensive processing. It calls `logger.isEnabledFor(level)` on the stdlib logger (inherited from root) to drop events below the configured level.

**CRITICAL: `_add_severity` must come AFTER `add_log_level`** — `add_log_level` adds `level`; `_add_severity` pops and renames it.

### `logging/setup.py` — Full Implementation

```python
"""structlog configuration — structured JSON logging with correlation_id propagation.

This module configures structlog's processor pipeline for consistent JSON output
across all pipeline components. Call configure_logging() at application startup.

Correlation ID (case_id) propagates through asyncio task-local context using
Python's contextvars — asyncio.create_task() inherits the parent's context,
so correlation_id set in the scheduler propagates to all case-processing coroutines.

Required fields per NFR-O3: timestamp, correlation_id, component, event_type, severity
"""

import logging
import sys
from typing import Any

import structlog


def _add_severity(
    logger: Any,
    method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Rename 'level' to 'severity', uppercased, per NFR-O3 field schema.

    structlog.stdlib.add_log_level adds 'level' with lowercase values ("info", "warning").
    This processor renames it to 'severity' with uppercase values ("INFO", "WARNING").
    """
    event_dict["severity"] = event_dict.pop("level", method).upper()
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for structured JSON output with correlation_id propagation.

    Call once at application startup before any pipeline operations begin.
    Safe to call multiple times (reconfigures on each call).

    Processor pipeline:
    1. merge_contextvars — injects asyncio task-local fields (correlation_id)
    2. filter_by_level — drops events below configured level (stdlib-backed)
    3. add_log_level — adds 'level' field
    4. _add_severity — renames 'level' → 'severity', uppercased (NFR-O3)
    5. TimeStamper — adds ISO 8601 UTC 'timestamp' field (NFR-O3)
    6. StackInfoRenderer — formats stack_info if present
    7. JSONRenderer — renders event dict as JSON string

    Args:
        log_level: Minimum log level: DEBUG, INFO, WARNING, ERROR. Default INFO.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            _add_severity,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def get_logger(component: str) -> structlog.BoundLogger:
    """Return a structlog logger pre-bound with component name.

    Component names follow dot-notation package paths:
        logger = get_logger("pipeline.scheduler")
        logger = get_logger("health.registry")
        logger = get_logger("evidence.builder")

    The 'component' key appears in every JSON log event from this logger.
    Additional context (correlation_id) is injected automatically from
    asyncio task-local storage via the merge_contextvars processor.

    Args:
        component: Dot-notation module/service identifier

    Returns:
        structlog BoundLogger with component pre-bound
    """
    return structlog.get_logger(component).bind(component=component)


def bind_correlation_id(correlation_id: str) -> None:
    """Bind correlation_id to the current asyncio task context.

    The correlation_id (typically case_id) appears in all subsequent log events
    from the current coroutine and any child tasks created via asyncio.create_task().

    Args:
        correlation_id: Case ID or request ID for log correlation (e.g., "case-abc-123")
    """
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_correlation_id() -> None:
    """Clear all structlog context variables from the current asyncio task context.

    Call at the end of each case processing cycle to prevent stale correlation_ids
    from leaking into the next evaluation interval.
    """
    structlog.contextvars.clear_contextvars()


def get_correlation_id() -> str | None:
    """Return the correlation_id from the current asyncio task context.

    Returns:
        The correlation_id string if set, None otherwise.
    """
    return structlog.contextvars.get_contextvars().get("correlation_id")
```

### `logging/__init__.py` — Exports

```python
"""Structured logging — JSON output with correlation_id propagation."""

from aiops_triage_pipeline.logging.setup import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    get_correlation_id,
    get_logger,
)

__all__ = [
    "bind_correlation_id",
    "clear_correlation_id",
    "configure_logging",
    "get_correlation_id",
    "get_logger",
]
```

### Test Implementation

**`tests/unit/logging/conftest.py`:**

```python
import io
import logging

import pytest
import structlog

from aiops_triage_pipeline.logging.setup import clear_correlation_id, configure_logging


@pytest.fixture(autouse=True)
def reset_structlog():
    """Reset structlog and stdlib root logger after each test to prevent state bleed."""
    yield
    structlog.reset_defaults()
    clear_correlation_id()
    root = logging.getLogger()
    root.handlers.clear()


@pytest.fixture
def log_stream():
    """Configure logging to write to StringIO for test output inspection.

    Clears root handlers first so configure_logging() does NOT add its own stderr handler.
    After configure_logging(), root has exactly one handler: our StringIO handler.
    """
    stream = io.StringIO()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    configure_logging("INFO")
    return stream
```

**`tests/unit/logging/test_setup.py`:**

```python
import asyncio
import io
import json
import logging

import structlog

from aiops_triage_pipeline.logging.setup import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    get_correlation_id,
    get_logger,
)


def _last_log(stream: io.StringIO) -> dict:
    """Parse last non-empty JSON log line from the stream."""
    lines = [line for line in stream.getvalue().strip().split("\n") if line.strip()]
    return json.loads(lines[-1])


def test_json_output_format(log_stream):
    """JSON renderer produces valid, parseable JSON on each log line."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert isinstance(data, dict)


def test_timestamp_field_present(log_stream):
    """Log output includes 'timestamp' field in ISO 8601 UTC format."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert "timestamp" in data
    assert "T" in data["timestamp"]  # ISO 8601 contains 'T' separator


def test_severity_field_present_and_uppercase(log_stream):
    """Log output has 'severity' (uppercase), not 'level' (NFR-O3)."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert data["severity"] == "INFO"
    assert "level" not in data


def test_component_field_present(log_stream):
    """Logger factory binds component name into each log event."""
    get_logger("pipeline.scheduler").info("test_event")
    data = _last_log(log_stream)
    assert data["component"] == "pipeline.scheduler"


def test_event_type_field_passthrough(log_stream):
    """Extra kwargs (event_type, case_id, etc.) are included in JSON output."""
    get_logger("test").info("test_event", event_type="evidence_collected", case_id="abc-123")
    data = _last_log(log_stream)
    assert data["event_type"] == "evidence_collected"
    assert data["case_id"] == "abc-123"


def test_correlation_id_appears_in_output(log_stream):
    """Bound correlation_id propagates into JSON via merge_contextvars processor."""
    bind_correlation_id("case-xyz-789")
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert data["correlation_id"] == "case-xyz-789"


def test_no_correlation_id_when_not_bound(log_stream):
    """'correlation_id' key is absent from output when not bound."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert "correlation_id" not in data


def test_correlation_id_cleared_after_clear(log_stream):
    """clear_correlation_id() removes correlation_id from subsequent log events."""
    bind_correlation_id("case-to-clear")
    clear_correlation_id()
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert "correlation_id" not in data


def test_get_correlation_id_returns_bound_value():
    """get_correlation_id() returns the currently bound correlation_id."""
    configure_logging("INFO")
    bind_correlation_id("test-correlation-abc")
    assert get_correlation_id() == "test-correlation-abc"


def test_get_correlation_id_returns_none_when_not_bound():
    """get_correlation_id() returns None when no correlation_id is bound."""
    configure_logging("INFO")
    assert get_correlation_id() is None


def test_debug_filtered_at_info_level(log_stream):
    """DEBUG messages produce no output when log_level=INFO (filter_by_level drops them)."""
    get_logger("test").debug("should_be_filtered")
    assert log_stream.getvalue().strip() == ""


def test_info_not_filtered_at_info_level(log_stream):
    """INFO messages are emitted when log_level=INFO."""
    get_logger("test").info("should_appear")
    lines = [line for line in log_stream.getvalue().strip().split("\n") if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "should_appear"


def test_warning_appears_at_info_level(log_stream):
    """WARNING messages are emitted at INFO level with severity='WARNING'."""
    get_logger("test").warning("warn_message")
    data = _last_log(log_stream)
    assert data["severity"] == "WARNING"


async def test_async_context_propagation():
    """correlation_id bound in parent propagates to child tasks via asyncio.create_task()."""
    configure_logging("INFO")
    bind_correlation_id("case-async-propagation-test")

    async def child_coroutine() -> str | None:
        return get_correlation_id()

    # asyncio.create_task() copies the current contextvars context to the child
    result = await asyncio.create_task(child_coroutine())
    assert result == "case-async-propagation-test"
```

### CRITICAL — Existing Usage in `config/settings.py`

`settings.py` already uses `structlog.BoundLogger` in its `log_active_config()` method (Story 1.4). This story provides the `configure_logging()` call that makes it work. After Story 1.7, the startup sequence is:

```python
# In __main__.py (or equivalent startup code):
from aiops_triage_pipeline.logging.setup import configure_logging, get_logger
from aiops_triage_pipeline.config.settings import get_settings

configure_logging(log_level="INFO")  # Must be called FIRST
logger = get_logger("pipeline.main")
get_settings().log_active_config(logger)  # Now works correctly — structlog is configured
```

**Do NOT wire this into `__main__.py` in Story 1.7** — that's a pipeline integration concern. This story only provides the building blocks.

### CRITICAL — `filter_by_level` Mechanics

`structlog.stdlib.filter_by_level` calls `stdlib_logger.isEnabledFor(level)` where:
- `stdlib_logger` = `logging.getLogger(component_name)` (created by `LoggerFactory()`)
- `level` = mapped from method name ("debug" → `logging.DEBUG`, "info" → `logging.INFO`, etc.)
- Child loggers inherit level from root if their own level is `NOTSET`

So `root.setLevel(logging.INFO)` + `filter_by_level` correctly drops DEBUG events. ✅

**Test setup note:** The `log_stream` fixture clears root handlers BEFORE calling `configure_logging()`. This causes `configure_logging()` to skip the `if not root.handlers:` branch (our StringIO handler is already there), so no stderr handler is added. Root level is set to `logging.INFO` by `configure_logging()`. ✅

### CRITICAL — `cache_logger_on_first_use=True` and Tests

`cache_logger_on_first_use=True` caches the processor chain on first logger call. In tests, the `reset_structlog` autouse fixture calls `structlog.reset_defaults()` after each test — this clears the cache. Each test starts fresh. Always call `get_logger()` fresh in each test function (never store loggers in module-level variables in tests).

### Import Boundary Rules (CRITICAL)

`logging/` is a **provider package** — consumed by nearly all other packages:
- ✅ `from aiops_triage_pipeline.logging import get_logger, bind_correlation_id`
- ✅ `import structlog` (external)
- ✅ `import logging` (stdlib)
- ✅ `import sys` (stdlib)
- ❌ **NO** imports from `aiops_triage_pipeline.pipeline.*`
- ❌ **NO** imports from `aiops_triage_pipeline.health.*`
- ❌ **NO** imports from `aiops_triage_pipeline.config.*`
- ❌ **NO** imports from `aiops_triage_pipeline.models.*`
- ❌ **NO** imports from any other internal package

`logging/` has ZERO internal dependencies — it's essentially a leaf package.

### `contextvars` Propagation — How It Works

```
asyncio.create_task(child())     ← copies entire current Context to child
    ↓
child() runs with parent's contextvars
    ↓
bind_correlation_id("case-123") was called in parent
    ↓
child's get_correlation_id() returns "case-123" ✅
```

This is Python's built-in behavior for `asyncio.create_task()` — no special handling needed. structlog's `contextvars` module uses Python's `contextvars.ContextVar` internally, so propagation is automatic.

**DOES NOT propagate to**: threads created via `threading.Thread()` — but aiOps pipeline is purely asyncio (no threads).

### Project Structure — Files to Create/Modify

```
src/aiops_triage_pipeline/logging/
├── __init__.py               # UPDATE: export configure_logging, get_logger, bind_correlation_id,
│                             #          clear_correlation_id, get_correlation_id
│                             # Currently a 0-byte stub — replace completely
└── setup.py                  # IMPLEMENT: configure_logging(), get_logger(), bind_correlation_id(),
                              #             clear_correlation_id(), get_correlation_id(), _add_severity()
                              # Currently a 0-byte stub — replace completely

tests/unit/logging/
├── __init__.py               # CREATE: empty file
├── conftest.py               # CREATE: reset_structlog (autouse), log_stream fixtures
└── test_setup.py             # CREATE: 14 unit tests covering all ACs
```

**Files NOT touched:**
- `config/settings.py` — already uses `structlog.BoundLogger` type hint; no changes needed
- `__main__.py` — pipeline startup wiring is NOT Story 1.7 scope
- `health/`, `contracts/`, `models/`, `denylist/` — no changes needed

### Ruff Compliance Notes

- `dict[str, Any]` not `Dict[str, Any]` (Python 3.13 native)
- `str | None` not `Optional[str]`
- Line length 100 chars max
- `from typing import Any` — required for `Any` type annotation
- `_add_severity` is module-private by convention (underscore prefix, not in `__all__`)
- All imports are used — no unused imports
- `structlog.BoundLogger` for return type of `get_logger()` (consistent with `settings.py`)

### Previous Story Intelligence (from Stories 1.2–1.6)

**Established patterns to carry forward exactly:**
- `functools.cache` for singletons — not applicable here (no singleton to cache)
- `frozen=True` on class declaration — not applicable here (no Pydantic models)
- Fixtures always in `conftest.py` — `reset_structlog` (autouse) and `log_stream` in conftest ✅
- `uv run ruff check` must pass before review
- `str | None` not `Optional[str]`
- `asyncio_mode = "auto"` — all `async def test_*` run without decorator ✅
- `datetime.now(tz=timezone.utc)` — not applicable here

**Key difference from Stories 1.2–1.6:**
Story 1.7 introduces the first **cross-cutting infrastructure** component — a module that every other package will import. Unlike previous stories that created isolated packages (contracts, config, denylist, health), the `logging/` package is the foundation that enables observability in all future stories.

### Git Context (Recent Commits)

- `4bb5350 Story 1.6: Code review fixes — HealthRegistry & Degraded Mode Foundation`
- `7aab65c Story 1.6: HealthRegistry & Degraded Mode Foundation — reviewed and done`
- `77ec583 Story 1.5: Exposure Denylist Foundation — reviewed and done`
- `370d20a Story 1.4: Code review fixes — config & settings hardening`

**Confirmed implementations from prior stories (do NOT re-implement):**
- `errors/exceptions.py` — complete exception hierarchy (PipelineError, DegradableError, etc.)
- `config/settings.py` — Settings, get_settings(), log_active_config() — already uses `structlog.BoundLogger`
- `denylist/` — DenylistV1, load_denylist, apply_denylist
- `health/` — HealthRegistry, get_health_registry, /health endpoint
- All 12 contracts in `contracts/` — fully frozen Pydantic models

### What Is NOT In Scope for Story 1.7

- **Wiring `configure_logging()` into `__main__.py`** — pipeline startup is not this story's scope
- **Passing loggers to existing components** (settings.log_active_config, health/registry, etc.) — each story wires its own logging as it builds on Story 1.7
- **Log aggregation / Dynatrace shipping** — OTLP tracing integration is Story 7.2
- **`CallsiteParameterAdder` processor** — not required by NFR-O3, adds call site info (file, line, func) to logs; out of scope
- **Multiple log output formats** (dev console vs prod JSON) — single JSON format sufficient per architecture

### References

- NFR-O3: Structured logging — JSON with consistent fields: `timestamp`, `correlation_id`, `component`, `event_type`, `severity`: [Source: `artifact/planning-artifacts/epics.md#NFR-O3`]
- NFR-O4: Configuration transparency — active config logged at startup: [Source: `artifact/planning-artifacts/epics.md#NFR-O4`]
- structlog 25.5.0 pinned in pyproject.toml: [Source: `pyproject.toml#dependencies`]
- `logging/setup.py` as the Correlation ID source for all modules: [Source: `artifact/planning-artifacts/architecture.md#Correlation ID`]
- `logging/` directory in complete project structure: [Source: `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`]
- `logging/` import boundary: `pipeline/stages/`, `diagnosis/`, `outbox/`, `integrations/` can all import from `logging/`: [Source: `artifact/planning-artifacts/architecture.md#Architectural Boundaries`]
- `settings.log_active_config(logger: structlog.BoundLogger)` — Story 1.4 anticipates Story 1.7: [Source: `src/aiops_triage_pipeline/config/settings.py`]
- pytest-asyncio `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorator needed: [Source: `pyproject.toml#tool.pytest.ini_options`]
- Story 1.6 test pattern — autouse reset fixture preventing state bleed: [Source: `artifact/implementation-artifacts/1-6-healthregistry-and-degraded-mode-foundation.md`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Implemented 7-stage structlog processor pipeline in `logging/setup.py` per exact order specified in Dev Notes (merge_contextvars → filter_by_level → add_log_level → _add_severity → TimeStamper → StackInfoRenderer → JSONRenderer)
- `_add_severity` renames stdlib `level` field to NFR-O3 compliant `severity` (uppercase)
- `get_logger(component)` pre-binds `component` key so all log events carry the originating module name
- `bind_correlation_id` / `clear_correlation_id` / `get_correlation_id` wrap structlog.contextvars — asyncio.create_task() propagation confirmed via `test_async_context_propagation`
- `logging/__init__.py` replaced stub with full 5-function public API + `__all__`
- 15 unit tests written covering all ACs; all pass. Zero regressions in 142-test suite. Ruff clean.
- [Code Review] M1: Added `_VALID_LOG_LEVELS` validation to `configure_logging()` — now raises `ValueError` for unrecognised level names instead of silently falling back to INFO
- [Code Review] M2: Fixed `clear_correlation_id()` to use `unbind_contextvars("correlation_id")` — now surgically removes only correlation_id instead of clearing all context vars; updated `conftest.py` reset fixture to call `clear_contextvars()` directly for full test isolation
- [Code Review] M3: Added `test_error_appears_at_info_level` — verifies ERROR log level produces `severity == "ERROR"` output (AC2 gap)
- [Code Review] M4: Added `sprint-status.yaml` to File List (was modified in implementation commit but omitted)
- [Code Review] L1: Corrected `configure_logging()` docstring — accurately describes reconfiguration caveats with cached loggers
- [Code Review] L2: Improved `_last_log()` test helper — assertion error now includes stream contents for easier debugging
- [Code Review] L3: Added `root.setLevel(logging.WARNING)` to `reset_structlog` fixture — prevents log level bleed between tests

### File List

src/aiops_triage_pipeline/logging/setup.py
src/aiops_triage_pipeline/logging/__init__.py
tests/unit/logging/__init__.py
tests/unit/logging/conftest.py
tests/unit/logging/test_setup.py
artifact/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-03-01: Story 1.7 implemented — structured logging foundation with structlog 25.5.0. Implemented `logging/setup.py` (7-stage processor pipeline, correlation_id via contextvars), updated `logging/__init__.py` exports, created 14 unit tests covering all ACs (14/14 pass, 141/141 suite passes, ruff clean).
- 2026-03-01: Code review fixes applied — log_level validation (ValueError on bad input), `clear_correlation_id()` now uses unbind_contextvars for surgical removal, added ERROR level test, improved test fixture isolation and diagnostics. 15/15 tests pass, 142/142 suite, ruff clean. Status → done.
