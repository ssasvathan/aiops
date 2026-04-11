---
stepsCompleted: ['step-01-preflight-and-context', 'step-02-generation-mode', 'step-03-test-strategy', 'step-04-generate-tests', 'step-04c-aggregate', 'step-05-validate-and-complete']
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-04-05'
workflowType: 'testarch-atdd'
inputDocuments:
  - artifact/implementation-artifacts/4-1-otlp-counters-and-histograms.md
  - src/aiops_triage_pipeline/outbox/metrics.py
  - src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py
  - tests/unit/pipeline/stages/test_baseline_deviation.py
  - tests/unit/health/test_metrics.py
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
---

# ATDD Checklist - Epic 4, Story 4.1: OTLP Counters & Histograms

**Date:** 2026-04-05
**Author:** Sas
**Primary Test Level:** Unit (backend Python/pytest)

---

## Story Summary

Story 4.1 adds OTLP counters and histograms to the baseline deviation stage so SREs can monitor detection rates, suppression ratios, and computation latency in Dynatrace. A new dedicated module `src/aiops_triage_pipeline/baseline/metrics.py` provides the 4 counters (FR29) and 2 histograms (FR30), wired into `collect_baseline_deviation_stage_output()`. Tests verify each instrument is incremented correctly using the `_RecordingInstrument` monkeypatch pattern established in `tests/unit/health/test_metrics.py`.

**As a** SRE,
**I want** OTLP counters and histograms tracking baseline deviation detection effectiveness and performance,
**So that** I can monitor detection rates, suppression ratios, and computation latency in Dynatrace.

---

## Acceptance Criteria

1. `aiops.baseline_deviation.deviations_detected` counter incremented by number of deviations found per cycle (FR29)
2. `aiops.baseline_deviation.findings_emitted`, `suppressed_single_metric`, and `suppressed_dedup` counters incremented correctly per cycle (FR29)
3. `aiops.baseline_deviation.stage_duration_seconds` histogram records total stage duration (FR30)
4. `aiops.baseline_deviation.mad_computation_seconds` histogram records per-scope MAD computation time (FR30)
5. Instruments use `_meter.create_counter()` / `_meter.create_histogram()` matching outbox/metrics.py pattern (AC4)
6. Unit tests verify counter increments and histogram recordings with mock instruments via `monkeypatch` (AC5)
7. Instrument names match `aiops.baseline_deviation.` prefix (P7)

---

## Stack Detection Result

- **Detected Stack:** `backend`
- **Test Framework:** pytest (pyproject.toml present, conftest.py present)
- **Generation Mode:** AI generation (sequential)
- **Test Level:** Unit (pure function instrumentation testing, no DB/network)

---

## Test Strategy

| Acceptance Criterion | Test Level | Priority | Test Name |
|---|---|---|---|
| AC1: deviations_detected counter | Unit | P0 | test_deviations_detected_counter_incremented |
| AC2: findings_emitted counter | Unit | P0 | test_findings_emitted_counter_incremented |
| AC2: suppressed_single_metric counter | Unit | P0 | test_suppressed_single_metric_counter_incremented |
| AC2: suppressed_dedup counter | Unit | P0 | test_suppressed_dedup_counter_incremented |
| AC3: stage_duration_seconds histogram | Unit | P0 | test_stage_duration_histogram_recorded |
| AC4: mad_computation_seconds histogram | Unit | P0 | test_mad_computation_histogram_recorded_per_scope |
| AC5+AC7: P7 naming convention | Unit | P1 | test_instrument_names_match_p7_convention |

**TDD Phase:** RED — tests fail because `src/aiops_triage_pipeline/baseline/metrics.py` does not exist yet, and the recording calls are not wired into `baseline_deviation.py`.

---

## Failing Tests Created (RED Phase)

### Unit Tests (7 tests)

**File:** `tests/unit/pipeline/stages/test_baseline_deviation.py` (appended to existing file)

All tests target the new `baseline_metrics` module and the wired recording calls. They fail because:
1. `src/aiops_triage_pipeline/baseline/metrics.py` does not exist (ImportError on `from aiops_triage_pipeline.baseline import metrics as baseline_metrics`)
2. Recording calls are not present in `baseline_deviation.py`

- **Test:** `test_deviations_detected_counter_incremented`
  - **Status:** RED - `baseline_metrics._deviations_detected` not present; recording call missing in stage
  - **Verifies:** AC1 — counter incremented by count of deviating metrics (3 in test scenario)

- **Test:** `test_findings_emitted_counter_incremented`
  - **Status:** RED - `baseline_metrics._findings_emitted` not present; recording call missing
  - **Verifies:** AC2 — findings_emitted counter incremented once per emitted finding

- **Test:** `test_suppressed_single_metric_counter_incremented`
  - **Status:** RED - `baseline_metrics._suppressed_single_metric` not present; recording call missing
  - **Verifies:** AC2 — suppressed_single_metric counter incremented for single-metric suppression

- **Test:** `test_suppressed_dedup_counter_incremented`
  - **Status:** RED - `baseline_metrics._suppressed_dedup` not present; recording call missing
  - **Verifies:** AC2 — suppressed_dedup counter incremented for hand-coded dedup suppression

- **Test:** `test_stage_duration_histogram_recorded`
  - **Status:** RED - `baseline_metrics._stage_duration_seconds` not present; recording call missing
  - **Verifies:** AC3 — histogram records positive duration per cycle

- **Test:** `test_mad_computation_histogram_recorded_per_scope`
  - **Status:** RED - `baseline_metrics._mad_computation_seconds` not present; recording call missing
  - **Verifies:** AC4 — histogram records one entry per scope evaluated

- **Test:** `test_instrument_names_match_p7_convention`
  - **Status:** RED - module does not exist; cannot verify `.name` attribute
  - **Verifies:** AC5+AC7 — all 6 instrument names match `aiops.baseline_deviation.*` P7 prefix

---

## Implementation Checklist

### Test: test_deviations_detected_counter_incremented
**Tasks to make this test pass:**
- [ ] Create `src/aiops_triage_pipeline/baseline/metrics.py` with `_deviations_detected` counter
- [ ] Wire `baseline_metrics.record_deviations_detected(deviations_detected)` into `baseline_deviation.py`
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py::test_deviations_detected_counter_incremented -v`

### Test: test_findings_emitted_counter_incremented
**Tasks to make this test pass:**
- [ ] Add `_findings_emitted` counter to `metrics.py` with `record_finding_emitted()` function
- [ ] Wire `baseline_metrics.record_finding_emitted()` inside finding emission block
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py::test_findings_emitted_counter_incremented -v`

### Test: test_suppressed_single_metric_counter_incremented
**Tasks to make this test pass:**
- [ ] Add `_suppressed_single_metric` counter to `metrics.py` with `record_suppressed_single_metric()` function
- [ ] Wire `baseline_metrics.record_suppressed_single_metric()` inside suppression block
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py::test_suppressed_single_metric_counter_incremented -v`

### Test: test_suppressed_dedup_counter_incremented
**Tasks to make this test pass:**
- [ ] Add `_suppressed_dedup` counter to `metrics.py` with `record_suppressed_dedup()` function
- [ ] Wire `baseline_metrics.record_suppressed_dedup()` inside dedup suppression block
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py::test_suppressed_dedup_counter_incremented -v`

### Test: test_stage_duration_histogram_recorded
**Tasks to make this test pass:**
- [ ] Add `_stage_duration_seconds` histogram to `metrics.py` with `record_stage_duration()` function
- [ ] Wire `baseline_metrics.record_stage_duration(elapsed_ms / 1000)` after elapsed_ms computation
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py::test_stage_duration_histogram_recorded -v`

### Test: test_mad_computation_histogram_recorded_per_scope
**Tasks to make this test pass:**
- [ ] Add `_mad_computation_seconds` histogram to `metrics.py` with `record_mad_computation()` function
- [ ] Wrap `_evaluate_scope()` with `_scope_t0 = time.perf_counter()` timing and `baseline_metrics.record_mad_computation(...)` after
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py::test_mad_computation_histogram_recorded_per_scope -v`

### Test: test_instrument_names_match_p7_convention
**Tasks to make this test pass:**
- [ ] Verify all 6 instruments have correct P7 names set on `.name` attribute
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py::test_instrument_names_match_p7_convention -v`

---

## Running Tests

```bash
# Run all new ATDD tests for this story
uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -k "test_deviations_detected_counter_incremented or test_findings_emitted_counter_incremented or test_suppressed_single_metric_counter_incremented or test_suppressed_dedup_counter_incremented or test_stage_duration_histogram_recorded or test_mad_computation_histogram_recorded_per_scope or test_instrument_names_match_p7_convention" -v

# Run all tests in file
uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -v

# Run full unit suite (ATDD gate)
uv run pytest tests/unit/ -q

# Lint check
uv run ruff check src/aiops_triage_pipeline/baseline/metrics.py tests/unit/pipeline/stages/test_baseline_deviation.py
```

---

## Red-Green-Refactor Workflow

### RED Phase (Current - TEA Responsibility) ✅
- All 7 tests written and will fail (baseline/metrics.py does not exist)
- Tests monkeypatch module-level instruments matching health/test_metrics.py pattern
- No @pytest.mark.xfail — tests are proper failing tests (ImportError → AttributeError once module exists but wiring is missing)

### GREEN Phase (DEV Agent Next Steps)
1. Create `src/aiops_triage_pipeline/baseline/metrics.py` (Task 1 in story)
2. Wire OTLP recording calls into `baseline_deviation.py` (Task 2 in story)
3. Run `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -v` → all 7 new tests green
4. Run `uv run pytest tests/unit/ -q` → ~1326 tests passing

### REFACTOR Phase (After All Tests Pass)
1. Run `uv run ruff check src/ tests/` → 0 violations
2. Verify no regressions in existing 1319 tests

---

## Test Execution Evidence

### Initial Test Run (RED Phase Verification)

**Command:** `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -k "test_deviations_detected_counter_incremented or test_findings_emitted_counter_incremented or test_suppressed_single_metric_counter_incremented or test_suppressed_dedup_counter_incremented or test_stage_duration_histogram_recorded or test_mad_computation_histogram_recorded_per_scope or test_instrument_names_match_p7_convention" -v`

**Results:**

```
FAILED tests/unit/pipeline/stages/test_baseline_deviation.py::test_deviations_detected_counter_incremented
FAILED tests/unit/pipeline/stages/test_baseline_deviation.py::test_findings_emitted_counter_incremented
FAILED tests/unit/pipeline/stages/test_baseline_deviation.py::test_suppressed_single_metric_counter_incremented
FAILED tests/unit/pipeline/stages/test_baseline_deviation.py::test_suppressed_dedup_counter_incremented
FAILED tests/unit/pipeline/stages/test_baseline_deviation.py::test_stage_duration_histogram_recorded
FAILED tests/unit/pipeline/stages/test_baseline_deviation.py::test_mad_computation_histogram_recorded_per_scope
FAILED tests/unit/pipeline/stages/test_baseline_deviation.py::test_instrument_names_match_p7_convention
======================= 7 failed, 21 deselected in 0.60s =======================
```

**Summary:**
- Total new tests: 7
- Passing: 0 (expected — TDD red phase)
- Failing: 7 (expected — module not yet created)
- Status: RED phase verified

**Failure message (all 7 tests):**
```
ImportError: cannot import name 'metrics' from 'aiops_triage_pipeline.baseline'
```
Failures are due to missing implementation (`baseline/metrics.py` does not exist), NOT test bugs.

### Existing Tests (Regression Check)

**Command:** `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -k "not (test_deviations_detected... [new tests])" -v`

**Results:** 21 passed — zero regressions.

### Lint Check

**Command:** `uv run ruff check tests/unit/pipeline/stages/test_baseline_deviation.py`

**Results:** All checks passed — 0 violations.

---

## Notes

- Tests appended to existing `tests/unit/pipeline/stages/test_baseline_deviation.py` (not a new file)
- `_RecordingInstrument` class is defined at module level in the test file (already there or added)
- All imports of `baseline_metrics` are deferred inside test function bodies (Epic 2 Retro TD-3 pattern)
- TD-2 weekday assertion: `FIXED_EVAL_TIME = datetime(2026, 4, 5, 14, 0, tzinfo=UTC)` → Sunday → `weekday()=6` → bucket `(6, 14)` — already correct in existing test at line 206

---

**Generated by BMad TEA Agent** - 2026-04-05
