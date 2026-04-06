# Story 4.2: Structured Logging & Health Registration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want structured log events for the baseline deviation stage lifecycle and HealthRegistry integration,
so that I can troubleshoot issues, trace suppression decisions, and verify system health via the health endpoint.

## Acceptance Criteria

1. **Given** the baseline deviation stage starts execution
   **When** the stage begins
   **Then** a `baseline_deviation_stage_started` structured log event is emitted (FR31)

2. **Given** the stage completes
   **When** results are available
   **Then** a `baseline_deviation_stage_completed` log event is emitted with `scopes_evaluated` and `findings` count (FR31)

3. **Given** a finding is emitted
   **When** the finding passes correlation and dedup checks
   **Then** a `baseline_deviation_finding_emitted` log event is emitted with scope and metric context (FR31)

4. **Given** suppression occurs
   **When** a single-metric deviation is suppressed
   **Then** a `baseline_deviation_suppressed_single_metric` DEBUG log is emitted with scope, metric, reason code, and cycle timestamp (NFR-A3)
   **And** when a hand-coded dedup suppression occurs
   **Then** a `baseline_deviation_suppressed_dedup` log is emitted with scope, metric, reason code, and cycle timestamp (NFR-A3)

5. **Given** Redis is unavailable during stage execution
   **When** fail-open is triggered
   **Then** a `baseline_deviation_redis_unavailable` log event is emitted (FR31)

6. **Given** the HealthRegistry
   **When** baseline deviation stage health is registered (FR32)
   **Then** it reports healthy/degraded status through the existing health endpoint
   **And** Redis unavailability triggers a degraded health event (NFR-R2)

7. **Given** all structured log events
   **When** they are emitted
   **Then** they use the `baseline_deviation_` prefix (P6)
   **And** include correlation context via structlog bindings
   **And** all 10 event types defined in P6 are implemented

8. **Given** unit tests
   **When** tests are executed
   **Then** all log event emissions are verified with captured log output
   **And** HealthRegistry integration is verified
   **And** `docs/component-inventory.md` is updated with the HealthRegistry component entry

## Tasks / Subtasks

- [x] Task 1: Audit and verify all 10 P6 structured log events are present (AC: 1, 2, 3, 4, 5, 7)
  - [x] 1.1 Open `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py` and verify all 6 stage-level events are present with correct names:
    - `baseline_deviation_stage_started` — at function top, before `started_at`
    - `baseline_deviation_stage_completed` — after `elapsed_ms`, with `scopes_evaluated`, `findings_emitted`, `suppressed_single_metric`, `suppressed_dedup`, `duration_ms`
    - `baseline_deviation_finding_emitted` — inside finding emission block, with `scope`, `deviating_metrics_count`, `finding_id`
    - `baseline_deviation_suppressed_single_metric` — inside `_evaluate_scope()`, DEBUG level, with `scope`, `metric_key`, `reason`
    - `baseline_deviation_suppressed_dedup` — inside dedup block, with `scope`, `reason`
    - `baseline_deviation_redis_unavailable` — inside outer except block, with `error`
  - [x] 1.2 Verify all 4 recompute/backfill events are present with correct names:
    - `baseline_deviation_recompute_started` — in `__main__.py` ~line 235
    - `baseline_deviation_recompute_completed` — in `__main__.py` ~line 272
    - `baseline_deviation_recompute_failed` — in `__main__.py` ~lines 255 and 263
    - `baseline_deviation_backfill_seeded` — **confirmed in `src/aiops_triage_pipeline/pipeline/baseline_backfill.py` line 278** (event_type="backfill.seasonal_seeded") — verify the event name matches exactly `"baseline_deviation_backfill_seeded"`
  - [x] 1.3 If any event from the P6 table is missing or has wrong name/fields, add or fix it; run `uv run ruff check src/` — 0 violations

- [x] Task 2: Wire HealthRegistry registration in `__main__.py` at the async call site (AC: 6, FR32)
  - [x] 2.1 Open `src/aiops_triage_pipeline/__main__.py`. Find the call to `run_baseline_deviation_stage_cycle()` at ~line 1069 inside `_hot_path_scheduler_loop()` (which is `async def` — confirmed).
  - [x] 2.2 Add the following `await` calls immediately after `run_baseline_deviation_stage_cycle()` returns, inside the `if settings.BASELINE_DEVIATION_STAGE_ENABLED:` block:
    ```python
    # FR32: HealthRegistry update — async-safe (inside _hot_path_scheduler_loop async def)
    _bd_registry = get_health_registry()
    if baseline_deviation_output.scopes_evaluated == 0 and len(evidence_output.rows) > 0:
        # Fail-open: had rows but evaluated 0 scopes → Redis unavailable
        await _bd_registry.update(
            "baseline_deviation", HealthStatus.DEGRADED, reason="redis_unavailable"
        )
    else:
        await _bd_registry.update("baseline_deviation", HealthStatus.HEALTHY)
    ```
  - [x] 2.3 Confirm `HealthStatus` is already imported at the top of `__main__.py` (it is — line ~88). Confirm `get_health_registry` is already imported (it is — line ~70). No new imports needed.
  - [x] 2.4 **Do NOT modify `pipeline/scheduler.py`** — the scheduler function signature stays unchanged. The HealthRegistry wiring is entirely in `__main__.py`.
  - [x] 2.5 Run `uv run ruff check src/` — 0 violations

- [x] Task 3: Add unit tests to `tests/unit/pipeline/stages/test_baseline_deviation.py` (AC: 8)
  - [x] 3.1 Add test `test_stage_started_log_event_emitted(log_stream)`:
    - Run stage with one scope producing 2 deviating metrics
    - Parse `log_stream` JSON lines
    - Assert at least 1 event with `event == "baseline_deviation_stage_started"`
    - Assert `scopes_count` field is present and > 0
  - [x] 3.2 Add test `test_stage_completed_log_event_emitted(log_stream)`:
    - Run stage with one scope producing a correlated finding
    - Assert at least 1 event with `event == "baseline_deviation_stage_completed"`
    - Assert `scopes_evaluated` and `findings_emitted` fields are present
  - [x] 3.3 Add test `test_finding_emitted_log_event(log_stream)`:
    - Run stage with one scope emitting a correlated finding
    - Assert at least 1 event with `event == "baseline_deviation_finding_emitted"`
    - Assert `scope` and `finding_id` fields are present
  - [x] 3.4 Add test `test_health_registry_healthy_registered_after_successful_cycle()` in `tests/unit/test_main.py`:
    - The HealthRegistry wiring lives in `_hot_path_scheduler_loop()` in `__main__.py` — tests go in `tests/unit/test_main.py`
    - Use `monkeypatch.setattr(__main__, "get_health_registry", lambda: registry)` with a fresh `HealthRegistry()` (see existing pattern at `test_main.py` line ~798)
    - Trigger a baseline deviation cycle with successful execution
    - Assert `registry.get("baseline_deviation") == HealthStatus.HEALTHY`
    - **Before writing this test:** Study the existing `_make_async_health_registry()` helper at `test_main.py` line ~280 and the test at line ~798 to understand the exact monkeypatch and async testing pattern used in that file. Follow it exactly.
  - [x] 3.5 Add test `test_health_registry_degraded_on_redis_unavailable()` in `tests/unit/test_main.py`:
    - Same approach as 3.4 — monkeypatch `get_health_registry` with fresh `HealthRegistry()`
    - Run cycle with baseline client raising `ConnectionError`
    - Assert `registry.get("baseline_deviation") == HealthStatus.DEGRADED`
  - [x] 3.6 Add test `test_health_registry_baseline_deviation_not_updated_when_stage_disabled()` in `tests/unit/test_main.py`:
    - Set `settings.BASELINE_DEVIATION_STAGE_ENABLED = False` (or monkeypatch)
    - Run cycle with fresh registry
    - Confirm `registry.get("baseline_deviation") is None` — no update when stage is disabled
  - [x] 3.7 Add test `test_all_p6_log_event_names_use_correct_prefix(log_stream, debug_log_stream)`:
    - Run stage in scenarios that trigger each of the 6 stage-level log events
    - Parse all log events
    - Assert every event name starts with `"baseline_deviation_"`
  - [x] 3.8 Run `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -v` — all existing + new tests pass
  - [x] 3.9 Run `uv run ruff check tests/unit/pipeline/stages/test_baseline_deviation.py` — 0 violations

- [x] Task 4: Update `docs/component-inventory.md` (AC: 8)
  - [x] 4.1 Add a new row to the Runtime Components table for the baseline deviation stage:
    | Baseline Deviation Stage | Pipeline | `pipeline/stages/baseline_deviation.py` | No | Correlated multi-metric baseline deviation detection with MAD z-score; emits BASELINE_DEVIATION findings; HealthRegistry key: `baseline_deviation` |
  - [x] 4.2 Save `docs/component-inventory.md`

- [x] Task 5: Full regression run (AC: inline)
  - [x] 5.1 **MANDATORY ATDD GATE (Epic 3 L1):** Run `uv run pytest tests/unit/ -q` — confirm all tests pass, 0 failures, 0 skipped. Target: ~1326 existing + ~6 new = ~1332 tests
  - [x] 5.2 Run `uv run ruff check src/ tests/` — 0 lint violations across entire source tree and test suite

## Dev Notes

### Critical Pre-Implementation Finding: Log Events Already Exist

**The 6 stage-level structured log events are already fully implemented in `baseline_deviation.py` (Story 2.3 delivered them).** Story 4-2's primary new work is:

1. **HealthRegistry integration** (FR32) — `baseline_deviation` component key in health registry
2. **Audit and verification** that all 10 P6 events exist (including 4 in `__main__.py`)
3. **Unit tests** for the log events and health registry (tests were deferred from Story 2.3)
4. **`docs/component-inventory.md` update** with the baseline_deviation entry

Do NOT re-implement or duplicate log events that already exist. Verify first (Task 1), then add HealthRegistry (Task 2).

### P6 Structured Log Events: Current State vs. Required

The P6 table defines 10 event types. Current implementation status:

| Event Name | Where | Status |
|---|---|---|
| `baseline_deviation_stage_started` | `baseline_deviation.py` line 70-75 | ✅ Present |
| `baseline_deviation_stage_completed` | `baseline_deviation.py` line 168-176 | ✅ Present |
| `baseline_deviation_finding_emitted` | `baseline_deviation.py` line 142-148 | ✅ Present |
| `baseline_deviation_suppressed_single_metric` | `baseline_deviation.py` (`_evaluate_scope`) line 252-258 | ✅ Present, DEBUG level |
| `baseline_deviation_suppressed_dedup` | `baseline_deviation.py` line 94-99 | ✅ Present |
| `baseline_deviation_redis_unavailable` | `baseline_deviation.py` line 151-155 | ✅ Present |
| `baseline_deviation_recompute_started` | `__main__.py` line ~235 | ✅ Present |
| `baseline_deviation_recompute_completed` | `__main__.py` line ~272 | ✅ Present |
| `baseline_deviation_recompute_failed` | `__main__.py` line ~255/263 | ✅ Present |
| `baseline_deviation_backfill_seeded` | `pipeline/baseline_backfill.py` line 278 | ✅ Present |

Task 1 is primarily a verification/audit pass. All 10 P6 events are expected to already be present. Task 1 confirms this and fixes any discrepancies found.

### HealthRegistry Async Pattern

`HealthRegistry.update()` is an `async def` method (uses `asyncio.Lock`). The stage function `collect_baseline_deviation_stage_output()` is **synchronous** — it cannot `await` directly.

The calling function `run_baseline_deviation_stage_cycle()` in `pipeline/scheduler.py` is also **synchronous**.

**CONFIRMED:** `run_baseline_deviation_stage_cycle()` is called from within `async def _hot_path_scheduler_loop()` in `__main__.py` (line 715). This means the call site IS async and we can `await registry.update(...)` there directly.

**DO NOT** use `asyncio.get_event_loop().run_until_complete()` — that would raise `RuntimeError: This event loop is already running` since we're already inside an async context.

**Correct implementation path** (update at the async call site in `__main__.py`):

```python
# In __main__.py _hot_path_scheduler_loop(), after run_baseline_deviation_stage_cycle() call (~line 1069):
baseline_deviation_output = run_baseline_deviation_stage_cycle(
    evidence_output=evidence_output,
    peak_output=peak_output,
    baseline_client=seasonal_baseline_client,
    evaluation_time=evaluation_time,
    alert_evaluator=alert_evaluator,
)
# FR32: HealthRegistry update (async-safe — we're inside _hot_path_scheduler_loop which is async def)
_bd_registry = get_health_registry()
if baseline_deviation_output.scopes_evaluated == 0 and len(evidence_output.rows) > 0:
    # Fail-open: had rows but evaluated 0 scopes → Redis error path
    await _bd_registry.update("baseline_deviation", HealthStatus.DEGRADED, reason="redis_unavailable")
else:
    await _bd_registry.update("baseline_deviation", HealthStatus.HEALTHY)
```

**Why `scopes_evaluated == 0 and len(evidence_output.rows) > 0`:** The fail-open path in `collect_baseline_deviation_stage_output()` returns early with `scopes_evaluated=0` when Redis raises an exception. If `evidence_output.rows` is empty (no evidence rows at all), `scopes_evaluated=0` is normal and not an error. The combined check detects the Redis failure case specifically.

This approach means `run_baseline_deviation_stage_cycle()` signature does NOT change — no new parameters needed. The health registry wiring is entirely in `__main__.py`.

### HealthRegistry Component Key Convention

From examining existing usages in `__main__.py`:
- `"redis"` — Redis connectivity
- `"prometheus"` — Prometheus scrape health
- `"llm"` — LLM cold-path health (from `diagnosis/graph.py`)
- `"kafka_cold_path_connected"`, `"kafka_cold_path_poll"`, `"kafka_cold_path_commit"` — Kafka cold-path

For Story 4-2, the component key for the baseline deviation stage is: **`"baseline_deviation"`**

This key will appear in the health endpoint's JSON response under `components.baseline_deviation.status`.

### HealthRegistry Test Pattern (test_main.py integration tests)

The HealthRegistry wiring is in `_hot_path_scheduler_loop()` in `__main__.py`. Tests for it belong in `tests/unit/test_main.py`.

**Established patterns in test_main.py:**
- `_make_async_health_registry()` helper at line ~280 creates a MagicMock that simulates async `update()` calls
- Line ~798: `monkeypatch.setattr(__main__, "get_health_registry", lambda: registry)` — exact pattern for replacing the singleton with a fresh registry
- HealthStatus assertions: `registry.get("component_name") == HealthStatus.HEALTHY`

**For Story 4-2 tests 3.4-3.6**, follow the existing pattern at line ~798 exactly. Use a real `HealthRegistry()` instance (not a MagicMock) if you need to assert on `.get()` — MagicMock won't store actual state.

The tests in `test_baseline_deviation.py` (Task 3 steps 3.1-3.3, 3.7) test the stage function log events. The HealthRegistry integration tests (3.4-3.6) go in `test_main.py`. Keep these separate to maintain clean test organization.

### `run_baseline_deviation_stage_cycle()` Location

The scheduler function is in `src/aiops_triage_pipeline/pipeline/scheduler.py` (line 314), NOT in `pipeline/stages/baseline_deviation.py`. Tests that test the health registry wiring will need to import from scheduler, not the stage module:

```python
from aiops_triage_pipeline.pipeline.scheduler import run_baseline_deviation_stage_cycle
```

### Structlog Lazy Instantiation Rule (Epic 2 TD-3, Applied)

The logger in `collect_baseline_deviation_stage_output()` is correctly instantiated **inside the function body**:
```python
logger = get_logger("pipeline.stages.baseline_deviation")
```
This is correct. Do NOT move it to module level. Any new functions that use logging must follow the same pattern.

### TD-2 Status: Already Fixed

The `test_finding_baseline_context_populated` test at line 206 already has:
```python
assert ctx.time_bucket == (6, 14)  # Sunday 14:00 UTC
```
This is correct — `datetime(2026, 4, 5, 14, 0, tzinfo=UTC)` is Sunday (weekday=6), hour=14. **TD-2 is already resolved; no fix needed.**

### Existing Log Event Tests in the File

The test file already has log event tests for some events (added in Story 2.3). Before adding new log tests, check for duplicates:

| Test | Line | Tests Which Event |
|---|---|---|
| `test_single_metric_suppressed_log_event` | ~232 | `baseline_deviation_suppressed_single_metric` |
| `test_redis_unavailable_log_event` | ~483 | `baseline_deviation_redis_unavailable` |
| `test_dedup_suppression_log_event` | ~721 | `baseline_deviation_suppressed_dedup` |

Story 4-2 adds tests for the **remaining 3** stage-level events not yet tested:
- `baseline_deviation_stage_started` (new test: 3.1)
- `baseline_deviation_stage_completed` (new test: 3.2)
- `baseline_deviation_finding_emitted` (new test: 3.3)

Plus 3 new HealthRegistry tests (3.4, 3.5, 3.6) and 1 prefix-audit test (3.7).

### `log_stream` and `debug_log_stream` Fixture Reference

The `log_stream` fixture (INFO level) is defined in `tests/unit/pipeline/conftest.py` — available automatically to all tests in `tests/unit/pipeline/stages/`. The `debug_log_stream` fixture (DEBUG level) is defined locally in `test_baseline_deviation.py` at line 110. Both are available for Story 4-2 tests without any new fixture creation.

For tests 3.1-3.3, use `log_stream` (INFO level — stage_started, stage_completed, finding_emitted are all INFO).

### Epic 3 Lesson L1: ATDD-Run-Before-Review Gate

**MANDATORY:** Run `uv run pytest tests/unit/ -q` and confirm ALL tests pass **before** marking the story ready for code review. This is Task 5.1. Do not skip it.

### Epic 3 Lesson L4: Consistency Audit

Before submitting for review: audit `test_baseline_deviation.py` to confirm new log event tests follow the same JSON parse + event filter pattern as existing log event tests (lines 232-259, 483-508, 721-749). The new tests must be internally consistent with this established pattern.

### Current Test Count and Target

After Story 4-1: **1,326 unit tests** passing. Story 4-2 adds approximately **6-7 new tests**:
- 3 log event emission tests (stage_started, stage_completed, finding_emitted)
- 3 HealthRegistry integration tests (healthy, degraded, none)
- 1 P6 prefix audit test

**Target: ~1,332-1,333 tests passing. Zero regressions required.**

### `baseline_deviation_backfill_seeded` Event — Verification Approach

To verify this event: search `__main__.py` for `"baseline_deviation_backfill_seeded"`. It should be in the cold-start seeding function. If missing, add it in the appropriate location after the backfill loop completes, with fields: `scopes_count`, `metrics_count`, `buckets_count` (or equivalent). Check what fields the existing recompute events use for consistency.

### Project Structure Notes

**Files that SHOULD require modification:**
- `src/aiops_triage_pipeline/__main__.py` — add HealthRegistry `await` calls at the `run_baseline_deviation_stage_cycle()` call site (~line 1069 inside `_hot_path_scheduler_loop`)
- `tests/unit/pipeline/stages/test_baseline_deviation.py` — add 3-4 new log event tests (3.1-3.3, 3.7)
- `tests/unit/test_main.py` — add 3 HealthRegistry integration tests (3.4-3.6)
- `docs/component-inventory.md` — add baseline_deviation row

**Files that SHOULD require modification only if gaps found:**
- `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py` — only if P6 event audit (Task 1) finds missing events or wrong field names
- `src/aiops_triage_pipeline/__main__.py` backfill section — `baseline_deviation_backfill_seeded` is already present in `pipeline/baseline_backfill.py` line 278; no change needed in `__main__.py` for this

**Files that MUST NOT be modified:**
- `src/aiops_triage_pipeline/pipeline/scheduler.py` — NO changes; HealthRegistry wiring is in `__main__.py` at the async call site
- `src/aiops_triage_pipeline/baseline/metrics.py` — OTLP instruments (Story 4-1 scope, complete)
- `src/aiops_triage_pipeline/baseline/client.py`, `computation.py`, `constants.py` — no changes
- `src/aiops_triage_pipeline/health/registry.py` — no changes (existing API is sufficient)
- `src/aiops_triage_pipeline/models/` — no model changes

**New files:** None expected.

**Alignment with project-structure-boundaries.md:**
- FR31 and FR32 map to `pipeline/stages/baseline_deviation.py` as primary file per architecture. For FR32, the health registry update belongs at the call site in `__main__.py` to maintain the sync nature of the stage function and avoid async promotion.
- `docs/component-inventory.md` update is explicitly required by AC 8.

### References

- Epic 4 Story 4.2 requirements: `artifact/planning-artifacts/epics.md` §Story 4.2
- FR31: Structured log events — `artifact/planning-artifacts/prd/functional-requirements.md`
- FR32: HealthRegistry integration — `artifact/planning-artifacts/prd/functional-requirements.md`
- NFR-A3: Suppression traceability — `artifact/planning-artifacts/prd/non-functional-requirements.md`
- NFR-R2: Redis unavailability degraded health — `artifact/planning-artifacts/prd/non-functional-requirements.md`
- P6: Structured log event naming table (10 events) — `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md` §P6
- P7: OTLP instrument naming — `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md` §P7
- Existing stage with all 6 current log events: `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py`
- HealthRegistry singleton: `src/aiops_triage_pipeline/health/registry.py`
- HealthRegistry usage pattern in diagnosis: `src/aiops_triage_pipeline/diagnosis/graph.py` lines ~174-191
- HealthRegistry usage in __main__.py: `src/aiops_triage_pipeline/__main__.py` lines ~751, ~842-966, ~1364-1497
- Scheduler function to extend: `src/aiops_triage_pipeline/pipeline/scheduler.py` lines 314-351
- Existing log event tests: `tests/unit/pipeline/stages/test_baseline_deviation.py` lines ~232, ~483, ~721
- log_stream fixture: `tests/unit/pipeline/conftest.py`
- debug_log_stream fixture: `tests/unit/pipeline/stages/test_baseline_deviation.py` line ~110
- HealthRegistry test pattern: `tests/unit/health/test_registry.py`
- Component inventory: `docs/component-inventory.md`
- Epic 3 Retrospective (L1 ATDD gate, L4 consistency audit): `artifact/implementation-artifacts/epic-3-retro-2026-04-05.md`
- Story 4-1 Dev Notes (established patterns for this test file): `artifact/implementation-artifacts/4-1-otlp-counters-and-histograms.md`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Task 2 implementation required two fixes to the pre-written test helper `_patch_baseline_deviation_loop_dependencies` in `test_main.py`: (1) `build_sustained_identity_keys` lambda needed to accept positional args (`lambda *_a, **_kw: ()` not `lambda **_: ()`); (2) `_load_peak_baseline_windows` needed to be patched to avoid real Redis call in unit tests. These were test infrastructure bugs, not production code bugs.

### Completion Notes List

- Task 1: Audit confirmed all 10 P6 structured log events present across `baseline_deviation.py`, `__main__.py`, and `baseline_backfill.py`. No changes required.
- Task 2: Wired HealthRegistry in `__main__.py` inside the `BASELINE_DEVIATION_STAGE_ENABLED` conditional, after `_update_baseline_buckets`. Uses `scopes_evaluated == 0 and len(evidence_output.rows) > 0` to distinguish Redis fail-open from empty evidence. Fixed two test infrastructure bugs in `_patch_baseline_deviation_loop_dependencies`.
- Task 3: Tests 3.1-3.7 were pre-written (part of TDD RED phase). All 7 new tests now pass (3 log event tests + 1 prefix-audit test in `test_baseline_deviation.py`, 3 HealthRegistry integration tests in `test_main.py`). Fixed lambda bugs in pre-written test helper.
- Task 4: Added `baseline_deviation` row to `docs/component-inventory.md` Runtime Components table.
- Task 5: 1335 tests pass (1326 baseline + 9 new). `ruff check src/ tests/` — 0 violations.

### File List

- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py`
- `tests/unit/test_main.py`
- `tests/unit/pipeline/stages/test_baseline_deviation.py`
- `docs/component-inventory.md`
- `artifact/test-artifacts/atdd-checklist-4-2-structured-logging-and-health-registration.md`

### Change Log

- 2026-04-05: Implemented HealthRegistry wiring for `baseline_deviation` component in `__main__.py` (FR32); verified all 10 P6 log events present; fixed 2 test infrastructure bugs in pre-written TDD helper; updated `docs/component-inventory.md`. Total: 1335 tests passing, 0 lint violations.
- 2026-04-05: Code review (bmad-bmm-code-review): Fixed H1 — added `cycle_timestamp` and `metric` fields to suppression log events per NFR-A3/AC4; fixed M1 — removed stale RED PHASE comments from HealthRegistry tests; fixed M2 — removed unused HealthStatus import with noqa suppression; fixed M3 — added `BASELINE_DEVIATION_STAGE_ENABLED` to `_hot_path_settings_for_shard_tests`; fixed M4 — updated File List; fixed L1-L3 — clarified fixture comments, updated module docstring, corrected Task 3 notes. Total: 1335 tests passing, 0 lint violations.
