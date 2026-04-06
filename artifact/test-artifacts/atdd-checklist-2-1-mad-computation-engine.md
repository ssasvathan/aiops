---
stepsCompleted: ['step-01-preflight-and-context', 'step-02-generation-mode', 'step-03-test-strategy', 'step-04c-aggregate', 'step-05-validate-and-complete']
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-04-05'
workflowType: 'testarch-atdd'
inputDocuments:
  - artifact/implementation-artifacts/2-1-mad-computation-engine.md
  - src/aiops_triage_pipeline/baseline/computation.py
  - src/aiops_triage_pipeline/baseline/constants.py
  - tests/unit/baseline/test_computation.py
  - _bmad/tea/config.yaml
---

# ATDD Checklist - Epic 2, Story 2.1: MAD Computation Engine

**Date:** 2026-04-05
**Author:** Sas
**Primary Test Level:** Unit (backend Python project)

---

## Step 1: Preflight & Context Loading

### Stack Detection

- **Detected Stack:** `backend`
- **Detection basis:** `pyproject.toml` present; no `package.json` with frontend dependencies, no `playwright.config.*`, no `vite.config.*`
- **Test framework:** pytest (confirmed via `conftest.py` and existing test structure)

### Prerequisites

- [x] Story approved with clear acceptance criteria (7 ACs documented)
- [x] Test framework configured: `conftest.py` and pytest structure confirmed
- [x] Development environment available

### Story Context Loaded

**Story:** 2-1-mad-computation-engine
**Status:** ready-for-dev

**As a** platform engineer
**I want** a MAD-based statistical computation engine that calculates modified z-scores against seasonal baselines
**So that** metric deviations can be identified with outlier-resistant statistics

### Acceptance Criteria Summary

1. `compute_modified_z_score()` computes median, MAD, applies `MAD_CONSISTENCY_CONSTANT` (0.6745), returns modified z-score
2. `abs(z_score) >= MAD_THRESHOLD` (4.0) → deviation (boundary inclusive)
3. `current > median` → `"HIGH"`, `current < median` → `"LOW"`
4. Result includes `deviation_magnitude`, `baseline_value`, `current_value`
5. `len < MIN_BUCKET_SAMPLES` (3) → returns `None`
6. MAD = 0 (all identical) → returns `None` (no division by zero)
7. Tests appended to existing `test_computation.py`, all paths covered, 0 skips

### TEA Config Flags

- `tea_use_playwright_utils`: true (N/A — backend stack, no browser)
- `tea_use_pactjs_utils`: true (N/A — no API contracts in this story)
- `tea_browser_automation`: auto (N/A — backend)
- `test_stack_type`: auto → resolved to `backend`

### Knowledge Fragments Loaded (Backend Profile)

- Core: `data-factories.md`, `test-quality.md`, `test-healing-patterns.md`
- Backend: `test-levels-framework.md`, `test-priorities-matrix.md`, `ci-burn-in.md`

---

## Step 2: Generation Mode

**Mode Selected:** AI Generation

**Rationale:** Backend Python project with pure function logic. Acceptance criteria are clear and testable. No browser recording needed. Sequential execution mode (single agent).

---

## Step 3: Test Strategy

### AC-to-Test Mapping

| AC | Test Scenario | Level | Priority |
|----|---------------|-------|----------|
| AC1 | Normal deviation above baseline | Unit | P0 |
| AC1+AC2+AC3 | Normal deviation below baseline | Unit | P0 |
| AC1+AC2 | No deviation (current close to median) | Unit | P0 |
| AC5 | Sparse data (< MIN_BUCKET_SAMPLES) → None | Unit | P0 |
| AC5 | Exactly MIN_BUCKET_SAMPLES → proceeds | Unit | P1 |
| AC6 | Zero MAD (all identical) → None | Unit | P0 |
| AC2 | Boundary threshold exactly == MAD_THRESHOLD → is_deviation | Unit | P1 |
| AC4 | baseline_value == median, current_value == input | Unit | P1 |
| AC4 | deviation_magnitude positive for HIGH | Unit | P1 |
| AC4 | deviation_magnitude negative for LOW | Unit | P1 |

### TDD Red Phase Requirements

All tests import `compute_modified_z_score` from `baseline.computation`. Since this function does not yet exist in `computation.py`, all tests will fail with `ImportError` (cannot import name 'compute_modified_z_score'). This is the proper Python TDD red phase — tests fail because the implementation is missing.

**No `@pytest.mark.xfail` or `@pytest.mark.skip`** — per project rules (0 skips policy).

---

## Step 4: Test Generation (Sequential Mode, Backend Unit Tests)

### Execution Mode Resolution

- `tea_execution_mode`: auto
- `detected_stack`: backend
- No subagent capability in current environment
- **Resolved mode:** sequential

### Worker 4A: Unit Test Generation (Python backend — equivalent to API test worker)

Since this is a pure Python backend computation story (no HTTP API endpoints), the subagent 4A scope maps to **unit tests** for the pure function `compute_modified_z_score`. No TypeScript API tests apply.

### Worker 4B: E2E/UI Test Generation

**SKIPPED** — `detected_stack` is `backend`. Per step-02 rules: "Skip this section entirely if `{detected_stack}` is `backend`." No browser/UI tests for a pure computation function.

---

## Failing Tests Created (RED Phase)

### Unit Tests (10 tests)

**File:** `tests/unit/baseline/test_computation.py` (APPENDED — existing `time_to_bucket` tests unchanged)

All tests will fail with `ImportError: cannot import name 'compute_modified_z_score' from 'aiops_triage_pipeline.baseline.computation'` until implementation is complete.

- **test_compute_mad_normal_deviation_above** — RED: ImportError (function not implemented)
  - Verifies: AC1, AC2, AC3 — HIGH deviation detected, `is_deviation=True`, `deviation_direction="HIGH"`, `deviation_magnitude > MAD_THRESHOLD`

- **test_compute_mad_normal_deviation_below** — RED: ImportError (function not implemented)
  - Verifies: AC1, AC2, AC3 — LOW deviation detected, `is_deviation=True`, `deviation_direction="LOW"`, `deviation_magnitude < -MAD_THRESHOLD`

- **test_compute_mad_no_deviation** — RED: ImportError (function not implemented)
  - Verifies: AC1, AC2 — no deviation when current is close to median, `is_deviation=False`

- **test_compute_mad_sparse_data_skip** — RED: ImportError (function not implemented)
  - Verifies: AC5 (FR6, NFR-R3) — returns `None` when `len(historical) < MIN_BUCKET_SAMPLES`

- **test_compute_mad_exactly_min_samples** — RED: ImportError (function not implemented)
  - Verifies: AC5 — exactly MIN_BUCKET_SAMPLES (3) → computation proceeds, returns non-None

- **test_compute_mad_zero_mad** — RED: ImportError (function not implemented)
  - Verifies: AC6 — all identical values → MAD=0 → returns `None`, no ZeroDivisionError

- **test_compute_mad_boundary_threshold_is_deviation** — RED: ImportError (function not implemented)
  - Verifies: AC2 — `abs(z_score) == MAD_THRESHOLD` exactly → `is_deviation=True` (>= boundary inclusive)

- **test_compute_mad_returns_correct_baseline_and_current** — RED: ImportError (function not implemented)
  - Verifies: AC4 — `result.baseline_value == median`, `result.current_value == current`

- **test_compute_mad_magnitude_signed_positive_for_high** — RED: ImportError (function not implemented)
  - Verifies: AC4 — `deviation_magnitude > 0` when `deviation_direction == "HIGH"`

- **test_compute_mad_magnitude_signed_negative_for_low** — RED: ImportError (function not implemented)
  - Verifies: AC4 — `deviation_magnitude < 0` when `deviation_direction == "LOW"`

---

## Implementation Checklist

### Task 1: Implement `compute_modified_z_score()` in `baseline/computation.py`

- [ ] Add `MADResult` frozen dataclass
- [ ] Add `_median()` private helper (sorted-list approach, no `statistics` module)
- [ ] Implement `compute_modified_z_score()` with sparse data guard, zero-MAD guard
- [ ] Import `MAD_CONSISTENCY_CONSTANT`, `MAD_THRESHOLD`, `MIN_BUCKET_SAMPLES` from `baseline.constants`
- [ ] Run: `uv run ruff check src/aiops_triage_pipeline/baseline/computation.py`
- [ ] Run: `uv run pytest tests/unit/baseline/test_computation.py -v` → all 22 tests pass

---

## Running Tests

```bash
# Run all tests for this story (unit tests only)
uv run pytest tests/unit/baseline/test_computation.py -v

# Run only the new MAD tests
uv run pytest tests/unit/baseline/test_computation.py -v -k "mad"

# Run full regression suite
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

- [x] All 10 new tests written and will fail (ImportError — function not implemented)
- [x] Existing 12 `time_to_bucket` tests untouched
- [x] No `@pytest.mark.xfail` or `@pytest.mark.skip` decorators (0-skip policy)
- [x] All imports at module level (ruff I001 compliance)
- [x] Tests appended to existing file (not replacing)

### GREEN Phase (DEV Agent — Next Steps)

1. Implement `MADResult` dataclass and `compute_modified_z_score()` in `computation.py`
2. Run tests → verify all 22 pass
3. Run ruff → confirm clean
4. Story 2.1 complete

---

## Test Execution Evidence

### Initial Test Run (RED Phase Verification)

**Command:** `uv run pytest tests/unit/baseline/test_computation.py -v 2>&1`

**Results:**

```
ERROR tests/unit/baseline/test_computation.py
ImportError while importing test module ...
tests/unit/baseline/test_computation.py:15: in <module>
    from aiops_triage_pipeline.baseline.computation import compute_modified_z_score, time_to_bucket
E   ImportError: cannot import name 'compute_modified_z_score' from
    'aiops_triage_pipeline.baseline.computation'

!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!!!!
```

**Summary:**

- Total tests attempted: 22 (12 existing + 10 new)
- Passing: 0 (collection blocked by ImportError)
- Failing: 22 (all blocked — ImportError at module level)
- Status: RED phase verified — `compute_modified_z_score` does not yet exist

**Expected Failure Mode:** `ImportError: cannot import name 'compute_modified_z_score'`
This is the correct TDD red phase failure — function does not exist until Task 1 is implemented.

---

## Notes

- This story is pure computation — no Redis, Kafka, or HTTP I/O
- `MADResult` uses `@dataclass(frozen=True)` (stdlib), NOT Pydantic
- `_median()` uses sorted-list approach (no `statistics` module — consistent with project patterns in `peak.py`)
- Zero-MAD guard prevents ZeroDivisionError (AC6)
- Boundary check uses `>=` not `>` (AC2 — exact boundary is a deviation)
- 4 pre-existing failures in `tests/unit/integrations/test_llm.py` are known/unrelated

---

**Generated by BMad TEA Agent** - 2026-04-05
