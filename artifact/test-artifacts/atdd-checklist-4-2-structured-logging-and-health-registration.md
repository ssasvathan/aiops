---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
lastStep: step-04-generate-tests
lastSaved: '2026-04-05'
story_id: 4-2-structured-logging-and-health-registration
inputDocuments:
  - artifact/implementation-artifacts/4-2-structured-logging-and-health-registration.md
  - src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/health/registry.py
  - tests/unit/pipeline/stages/test_baseline_deviation.py
  - tests/unit/test_main.py
  - tests/unit/pipeline/conftest.py
  - _bmad/tea/testarch/knowledge/data-factories.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-priorities-matrix.md
tddPhase: RED
---

# ATDD Checklist: Story 4-2 Structured Logging & Health Registration

**Story**: 4-2-structured-logging-and-health-registration
**Date**: 2026-04-05
**Workflow**: `testarch-atdd`
**TDD Phase**: RED (failing tests generated for unimplemented features; GREEN tests generated for already-implemented log events)

---

## Step 1: Preflight & Context

### Stack Detection

- **Detected Stack**: `backend`
- **Detection Evidence**: `pyproject.toml` present, no `package.json`/`playwright.config.*`, Python test suite at `tests/`

### Prerequisites

- [x] Story approved with clear acceptance criteria (AC 1–8)
- [x] Test framework configured: `conftest.py` at `tests/unit/pipeline/conftest.py`
- [x] Development environment available

### Story Context Loaded

- **Primary file**: `4-2-structured-logging-and-health-registration.md`
- **ACs extracted**: 8 acceptance criteria (log events AC 1-5, HealthRegistry AC 6, prefix AC 7, test coverage AC 8)
- **Key finding**: All 6 stage-level log events already implemented in `baseline_deviation.py` (Story 2.3). **Only HealthRegistry wiring (FR32) is missing**.
- **Components affected**: `baseline_deviation.py` (log events), `__main__.py` (HealthRegistry wiring)

### Framework & Existing Patterns

- **Test runner**: pytest + `pytest-asyncio`
- **Log capture pattern**: `log_stream` fixture (INFO, JSON), `debug_log_stream` (DEBUG, JSON)
- **Log assertion pattern**: parse JSON lines, filter by `ev.get("event") == "event_name"`
- **HealthRegistry pattern**: `monkeypatch.setattr(__main__, "get_health_registry", lambda: registry)` with fresh `HealthRegistry()` instance
- **Async test pattern**: `@pytest.mark.asyncio`, `AsyncMock`, `asyncio.CancelledError` to terminate loop

### TEA Config Flags

- `tea_use_playwright_utils`: true (irrelevant for backend stack)
- `tea_browser_automation`: auto (irrelevant for backend)
- `test_stack_type`: auto → resolved `backend`

---

## Step 2: Generation Mode

**Mode selected**: AI Generation

**Rationale**: Backend Python stack. Acceptance criteria are clear. No browser recording needed. Tests use existing pytest patterns from the codebase.

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Scenarios Mapping

| AC | Scenario | Test Name | Level | Priority | Target File | Expected Phase |
|---|---|---|---|---|---|---|
| AC 1 | stage_started event emitted | `test_stage_started_log_event_emitted` | Unit | P1 | `test_baseline_deviation.py` | GREEN (impl exists) |
| AC 2 | stage_completed event with fields | `test_stage_completed_log_event_emitted` | Unit | P1 | `test_baseline_deviation.py` | GREEN (impl exists) |
| AC 3 | finding_emitted event with scope+finding_id | `test_finding_emitted_log_event` | Unit | P1 | `test_baseline_deviation.py` | GREEN (impl exists) |
| AC 6 | HealthRegistry HEALTHY after successful cycle | `test_health_registry_healthy_registered_after_successful_cycle` | Unit | P0 | `test_main.py` | **RED** (no impl) |
| AC 6 | HealthRegistry DEGRADED on Redis unavailability | `test_health_registry_degraded_on_redis_unavailable` | Unit | P0 | `test_main.py` | **RED** (no impl) |
| AC 6 | HealthRegistry not updated when stage disabled | `test_health_registry_baseline_deviation_not_updated_when_stage_disabled` | Unit | P1 | `test_main.py` | **RED** (no impl) |
| AC 7 | All P6 events use `baseline_deviation_` prefix | `test_all_p6_log_event_names_use_correct_prefix` | Unit | P2 | `test_baseline_deviation.py` | GREEN (impl exists) |

**Total new tests**: 7
**RED phase (will fail)**: 3 (HealthRegistry tests — wiring not yet in `__main__.py`)
**GREEN phase (will pass)**: 4 (log event tests — all 6 stage events already implemented)

### Test Level Selection

All tests are **unit level** — appropriate for:
- Pure function log event emission (isolated, no external deps)
- HealthRegistry wiring in `_hot_path_scheduler_loop` (monkeypatched dependencies)

No integration or E2E tests needed for this story (no new HTTP endpoints, no UI).

### Red Phase Requirements

HealthRegistry tests will FAIL because:
- `__main__.py` lines 1068–1095 do NOT contain `await _bd_registry.update("baseline_deviation", ...)` calls
- After `run_baseline_deviation_stage_cycle()`, no HealthRegistry update is performed
- Tests will fail with assertion errors: `registry.get("baseline_deviation")` returns `None`, not `HealthStatus.HEALTHY` or `HealthStatus.DEGRADED`

---

## Step 4: Generated Tests

### File 1: `tests/unit/pipeline/stages/test_baseline_deviation.py` (append)

Tests appended: `test_stage_started_log_event_emitted`, `test_stage_completed_log_event_emitted`, `test_finding_emitted_log_event`, `test_all_p6_log_event_names_use_correct_prefix`

### File 2: `tests/unit/test_main.py` (append)

Tests appended: `test_health_registry_healthy_registered_after_successful_cycle`, `test_health_registry_degraded_on_redis_unavailable`, `test_health_registry_baseline_deviation_not_updated_when_stage_disabled`

---

## ATDD Summary

| Metric | Value |
|---|---|
| Total new tests | 7 |
| RED (failing, unimplemented) | 2 |
| GREEN (passing, already implemented) | 5 |
| Test files modified | 2 |
| Execution mode | Sequential (backend) |
| TDD phase | RED for HealthRegistry HEALTHY/DEGRADED; GREEN for log events + disabled guard |
| Total suite after adding tests | 1333 (1326 prior + 7 new) |
| Ruff violations | 0 |

### RED Tests (2)
- `test_health_registry_healthy_registered_after_successful_cycle` — fails with `None == HEALTHY`
- `test_health_registry_degraded_on_redis_unavailable` — fails with `None == DEGRADED`

### GREEN Tests (5 new + 1326 existing = 1331 total passing)
- `test_stage_started_log_event_emitted` — log event already implemented
- `test_stage_completed_log_event_emitted` — log event already implemented
- `test_finding_emitted_log_event` — log event already implemented
- `test_all_p6_log_event_names_use_correct_prefix` — all 6 events already implemented
- `test_health_registry_baseline_deviation_not_updated_when_stage_disabled` — trivially passes (no wiring = no update = correct for disabled stage)

---

## Implementation Checklist (for developer)

- [ ] Add `await _bd_registry.update("baseline_deviation", HealthStatus.HEALTHY)` in `__main__.py` after `run_baseline_deviation_stage_cycle()` succeeds
- [ ] Add `await _bd_registry.update("baseline_deviation", HealthStatus.DEGRADED, reason="redis_unavailable")` when `scopes_evaluated == 0 and len(evidence_output.rows) > 0`
- [ ] Verify `get_health_registry` and `HealthStatus` are already imported (confirmed: lines ~70 and ~88)
- [ ] Run `uv run pytest tests/unit/ -q` → target ~1333 passing
- [ ] Run `uv run ruff check src/ tests/` → 0 violations
