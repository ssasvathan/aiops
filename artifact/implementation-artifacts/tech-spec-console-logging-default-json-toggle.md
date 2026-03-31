---
title: 'Console Logging as Default with JSON Toggle'
slug: 'console-logging-default-json-toggle'
created: '2026-03-31T00:00:00Z'
status: 'Completed'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - 'Python 3.13'
  - 'structlog==25.5.0'
  - 'pytest==9.0.2 + pytest-asyncio==1.3.0'
files_to_modify:
  - 'src/aiops_triage_pipeline/logging/setup.py'
  - 'tests/unit/logging/conftest.py'
  - 'tests/unit/pipeline/conftest.py'
  - 'tests/unit/logging/test_setup.py'
code_patterns:
  - 'os.getenv with default for env-var-driven config (POD_NAME/POD_NAMESPACE pattern)'
  - 'structlog processor chain split by format branch'
  - '_add_severity is JSON-only processor'
  - 'log_format parameter: explicit arg > LOG_FORMAT env var > "console" default'
test_patterns:
  - 'pytest fixtures in conftest.py control configure_logging() call site'
  - '_last_log(stream) helper parses last JSON line'
  - 'autouse reset_structlog fixture clears state between tests'
  - 'monkeypatch.setenv for env-var-driven tests'
---

# Tech-Spec: Console Logging as Default with JSON Toggle

**Created:** 2026-03-31

## Overview

### Problem Statement

The current logging pipeline uses `structlog.processors.JSONRenderer()` as the final output stage, producing JSON-formatted log lines. This was an intentional architectural choice (Story 1.7) to satisfy NFR-O3, which requires structured logging with consistent fields. However, JSON output is difficult to read during local development and debugging sessions.

### Solution

Add a `log_format` parameter to `configure_logging()` and read a `LOG_FORMAT` environment variable (consistent with the existing `POD_NAME`/`POD_NAMESPACE` env-var pattern in `configure_logging()`). Default to `structlog.dev.ConsoleRenderer` for human-readable output. Set `LOG_FORMAT=json` to restore the current JSON pipeline (for production / log-aggregation environments). The `_add_severity` processor (NFR-O3 field rename) stays in the JSON branch only, since `ConsoleRenderer` uses the `level` key natively.

### Scope

**In Scope:**
- `src/aiops_triage_pipeline/logging/setup.py` — add `log_format` param + `LOG_FORMAT` env var; split processor pipeline into console vs JSON branches
- `tests/unit/logging/conftest.py` — update `log_stream` fixture to explicitly pass `log_format="json"` so all 18 existing tests stay green
- `tests/unit/pipeline/conftest.py` — same fix; 5 pipeline test files use `json.loads()` on its `log_stream` fixture
- `tests/unit/logging/test_setup.py` — add 4 new tests covering the console renderer path

**Out of Scope:**
- `__main__.py` — no changes needed; defaults to console automatically
- `config/settings.py` — `LOG_FORMAT` is read directly in the logging module (same pattern as `POD_NAME`)
- All other callers of `get_logger()`, `bind_correlation_id()`, etc. — public API unchanged
- PRD / NFR-O3 update — JSON remains available via env var for production use

## Context for Development

### Codebase Patterns

- `configure_logging()` already reads env vars inside the function body (`os.getenv("POD_NAME")`, `os.getenv("POD_NAMESPACE")`) — follow the same pattern for `LOG_FORMAT`
- Parameter precedence pattern: `fmt = (log_format or os.getenv("LOG_FORMAT", "console")).lower()`
- `_add_severity` is only meaningful for JSON output (renames `level` → `severity` per NFR-O3); `ConsoleRenderer` uses `level` natively — so `_add_severity` must be excluded from the console pipeline branch
- `format_exc_info` processor stays in **both** pipelines — exception rendering is useful in both formats
- The `log_stream` fixture in `conftest.py` is the single control point for all tests that use `json.loads()` — updating it to pass `log_format="json"` preserves all existing tests without touching individual test bodies
- `structlog.dev.ConsoleRenderer` is already available via pinned `structlog==25.5.0` — no new dependency
- **CRITICAL**: `tests/unit/pipeline/conftest.py` also has a `log_stream` fixture calling `configure_logging("INFO")`, and 5 pipeline test files (`test_gating.py`, `test_scheduler.py`, `test_anomaly.py`, `test_evidence.py`, `test_peak.py`) use `json.loads()` on that stream — this fixture must also be updated

### Files to Reference

| File | Purpose |
| ---- | ------- |
| [src/aiops_triage_pipeline/logging/setup.py](src/aiops_triage_pipeline/logging/setup.py) | Primary target — 158 lines, structlog config |
| [tests/unit/logging/conftest.py](tests/unit/logging/conftest.py) | `log_stream` fixture line 34 — add `log_format="json"` |
| [tests/unit/pipeline/conftest.py](tests/unit/pipeline/conftest.py) | `log_stream` fixture line 30 — add `log_format="json"` |
| [tests/unit/logging/test_setup.py](tests/unit/logging/test_setup.py) | 18 existing tests; append 4 new console tests |
| [src/aiops_triage_pipeline/__main__.py](src/aiops_triage_pipeline/__main__.py) | Calls `configure_logging()` at line 305 — no changes needed |
| [archive/Iteration 1/implementation-artifacts/1-7-structured-logging-foundation.md](archive/Iteration%201/implementation-artifacts/1-7-structured-logging-foundation.md) | Historical processor pipeline rationale |

### Technical Decisions

- **Default format is `console`** — developers get readable output without any config; prod sets `LOG_FORMAT=json`
- **`log_format` parameter** — allows tests and callers to force a format without env var manipulation; new signature: `configure_logging(log_level: str = "INFO", log_format: str | None = None)`
- **`_add_severity` is JSON-only** — ConsoleRenderer uses `level` key natively; including `_add_severity` in the console pipeline would rename it and break colorization
- **`format_exc_info` stays in both pipelines** — exception tracebacks are needed in both human and machine output
- **Permissive format resolution** — any value other than `"json"` falls back to console (no `ValueError` for unknown format values; matches debug-oriented intent)
- **`__main__.py` requires no change** — `configure_logging()` with no args picks up `LOG_FORMAT` env var or falls back to console

## Implementation Plan

### Tasks

- [x] Task 1: Update `configure_logging()` in `setup.py` to support dual renderer pipelines
  - File: `src/aiops_triage_pipeline/logging/setup.py`
  - Action: Add `log_format: str | None = None` parameter. Inside the function, resolve format with `fmt = (log_format or os.getenv("LOG_FORMAT", "console")).lower()`. Build `processors` list conditionally: if `fmt == "json"` use the current 8-processor chain ending with `_add_severity` + `JSONRenderer`; otherwise use the 7-processor console chain (omit `_add_severity`, use `structlog.dev.ConsoleRenderer()` as final processor). Pass `processors` to `structlog.configure()`. Update the module docstring and `configure_logging()` docstring to document both pipelines and the `log_format` / `LOG_FORMAT` env var.
  - Notes: The console pipeline is: `merge_contextvars → filter_by_level → add_log_level → TimeStamper(fmt="iso", utc=True) → StackInfoRenderer → format_exc_info → ConsoleRenderer()`. The JSON pipeline is the existing 8-stage chain (unchanged). Keep `_VALID_LOG_LEVELS` validation unchanged.

- [x] Task 2: Update `log_stream` fixture in `tests/unit/logging/conftest.py`
  - File: `tests/unit/logging/conftest.py`
  - Action: Change line 34 from `configure_logging("INFO")` to `configure_logging("INFO", log_format="json")`.
  - Notes: This is the only change needed in this file. All 18 existing `test_setup.py` tests that use the `log_stream` fixture will continue to receive JSON output and pass unchanged.

- [x] Task 3: Update `log_stream` fixture in `tests/unit/pipeline/conftest.py`
  - File: `tests/unit/pipeline/conftest.py`
  - Action: Change line 30 from `configure_logging("INFO")` to `configure_logging("INFO", log_format="json")`.
  - Notes: Prevents breakage in 5 pipeline test files that call `json.loads()` on log output.

- [x] Task 4: Add console renderer tests to `tests/unit/logging/test_setup.py`
  - File: `tests/unit/logging/test_setup.py`
  - Action: Add a `log_stream_console` fixture and 4 new test functions after the existing tests. Add `import pytest` if not already present (it is not currently imported). The fixture and tests are described in detail in the Testing Strategy section below.
  - Notes: Do not modify any existing test bodies. Use `log_stream_console` (not `log_stream`) for the new tests to keep JSON and console test contexts independent.

### Acceptance Criteria

- [x] AC 1: Given `configure_logging()` is called with no arguments and `LOG_FORMAT` env var is unset, when any component calls `get_logger("x").info("event")`, then the output is **not** valid JSON (human-readable console format)

- [x] AC 2: Given `configure_logging(log_format="json")` is called, when any component logs an event, then the output is valid JSON containing fields `timestamp`, `severity`, `component`, and `event`

- [x] AC 3: Given `LOG_FORMAT=json` is set in the environment and `configure_logging()` is called with no explicit `log_format`, when any component logs an event, then the output is valid JSON (env var drives format selection)

- [x] AC 4: Given `configure_logging(log_format="console")` is called, when any component logs an event, then the output is human-readable text that contains both the event message string and the component name

- [x] AC 5: Given the `log_stream` fixture in `tests/unit/logging/conftest.py` now passes `log_format="json"`, when all 18 existing `tests/unit/logging/test_setup.py` tests are run, then all 18 pass without any changes to individual test bodies

- [x] AC 6: Given the `log_stream` fixture in `tests/unit/pipeline/conftest.py` now passes `log_format="json"`, when the full pipeline unit test suite is run, then all tests that use `json.loads()` on log output continue to pass

- [x] AC 7: Given `configure_logging()` is called with no arguments (console default), when `bind_correlation_id("case-123")` is called and an event is logged, then `correlation_id` is visible in the console output (context propagation unaffected by format)

## Additional Context

### Dependencies

- `structlog==25.5.0` (already pinned in `pyproject.toml`) — `structlog.dev.ConsoleRenderer` is bundled; no new dependencies required

### Testing Strategy

**Fixture to add in `tests/unit/logging/test_setup.py`** (after existing imports, before new tests):

```python
@pytest.fixture
def log_stream_console():
    """Configure logging with console format for test output inspection."""
    stream = io.StringIO()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    configure_logging("INFO", log_format="console")
    return stream
```

**Four new test functions to append:**

```python
def test_console_output_is_not_json(log_stream_console):
    """Console renderer produces non-JSON, human-readable output."""
    get_logger("test").info("test_event")
    lines = [l for l in log_stream_console.getvalue().strip().split("\n") if l.strip()]
    assert lines, f"Expected log output, got: {log_stream_console.getvalue()!r}"
    with pytest.raises(json.JSONDecodeError):
        json.loads(lines[-1])


def test_console_output_contains_event(log_stream_console):
    """Console renderer output includes the event message string."""
    get_logger("test").info("my_console_event")
    assert "my_console_event" in log_stream_console.getvalue()


def test_console_output_contains_component(log_stream_console):
    """Console renderer output includes the component field value."""
    get_logger("pipeline.scheduler").info("test_event")
    assert "pipeline.scheduler" in log_stream_console.getvalue()


def test_log_format_env_var_json_selects_json_renderer(monkeypatch):
    """LOG_FORMAT=json env var causes configure_logging() to use JSON renderer."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    stream = io.StringIO()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    structlog.reset_defaults()
    configure_logging("INFO")  # no explicit log_format — reads from env
    get_logger("test").info("json_via_env_var")
    lines = [l for l in stream.getvalue().strip().split("\n") if l.strip()]
    assert lines
    data = json.loads(lines[-1])
    assert data["event"] == "json_via_env_var"
```

**Quality gates:**
- `uv run ruff check src/aiops_triage_pipeline/logging/` — zero errors
- `uv run pytest tests/unit/logging/ -v` — all 22 tests pass (18 existing + 4 new)
- `uv run pytest tests/unit/pipeline/ -v` — no regressions in pipeline test suite

### Notes

- **NFR-O3 preserved**: JSON format remains available via `LOG_FORMAT=json`; production deployments are unaffected
- **ANSI escape codes**: `ConsoleRenderer` uses `colors=sys.stderr.isatty()` — ANSI codes are suppressed in non-TTY environments (CI, containers, log aggregators). Tests assert on substring presence to avoid fragility from escape sequences.
- **`cache_logger_on_first_use=True`**: If `configure_logging()` is called twice with different formats in the same process without `structlog.reset_defaults()`, already-cached loggers retain the first format. This is existing behavior and unchanged; the `reset_structlog` autouse fixture in tests handles this correctly.
- **Inline `configure_logging()` calls in `test_setup.py`**: Updated to pass `log_format="json"` explicitly to prevent mid-suite console reconfiguration.

## Review Notes
- Adversarial review completed
- Findings: 11 total, 11 fixed, 0 skipped
- Resolution approach: auto-fix
