---
stepsCompleted:
  [
    'step-01-preflight-and-context',
    'step-02-generation-mode',
    'step-03-test-strategy',
    'step-04-generate-tests',
    'step-04c-aggregate',
    'step-05-validate-and-complete',
  ]
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-04-05'
workflowType: 'testarch-atdd'
inputDocuments:
  - artifact/implementation-artifacts/1-1-baseline-constants-and-time-bucket-derivation.md
  - _bmad/tea/config.yaml
  - _bmad/tea/testarch/knowledge/data-factories.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-healing-patterns.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-priorities-matrix.md
---

# ATDD Checklist - Epic 1, Story 1.1: Baseline Constants & Time Bucket Derivation

**Date:** 2026-04-05
**Author:** Sas
**Primary Test Level:** Unit (pure functions, no I/O)

---

## Story Summary

This story creates the `baseline/` Python package as the single source of truth for all baseline
deviation constants and time bucket derivation logic. It delivers exactly two functional files:
`baseline/constants.py` (5 numerical constants) and `baseline/computation.py` (one pure function:
`time_to_bucket`). All future baseline stories (1.2, 1.3, 2.1, 2.x) depend on these artifacts.

**As a** platform engineer
**I want** baseline deviation constants and time bucket logic defined in a single source of truth
**So that** all baseline components use consistent threshold values and bucket derivation logic

---

## Acceptance Criteria

1. `baseline/__init__.py` and `baseline/constants.py` are created; importing `constants.py`
   exposes 5 SCREAMING_SNAKE_CASE module-level constants: `MAD_CONSISTENCY_CONSTANT=0.6745`,
   `MAD_THRESHOLD=4.0`, `MIN_CORRELATED_DEVIATIONS=2`, `MIN_BUCKET_SAMPLES=3`,
   `MAX_BUCKET_VALUES=12`.
2. `time_to_bucket(datetime(2026,1,7,14,0,0,tzinfo=timezone.utc))` returns `(2, 14)`.
3. Non-UTC datetimes are normalized to UTC before bucket derivation (e.g., UTC+5 Wed 19:00
   → UTC Wed 14:00 → `(2, 14)`).
4. `dow` is always in range 0–6 (Mon=0, Sun=6) and `hour` in range 0–23; `weekday()` (not
   `isoweekday()`) is used; `time_to_bucket` is the sole conversion source of truth.
5. Unit tests in `tests/unit/baseline/test_constants.py` and
   `tests/unit/baseline/test_computation.py` pass; docs updated.

---

## Step 1: Preflight & Context

### Stack Detection

- **Detected Stack:** `backend`
- **Detection evidence:** `pyproject.toml` present; no `package.json` with frontend deps; no
  `playwright.config.*` or `vite.config.*`; `conftest.py` and pytest config found.

### Prerequisites Verified

- [x] Story has clear, testable acceptance criteria
- [x] Test framework configured: pytest (`pyproject.toml` `[tool.pytest.ini_options]`)
- [x] `conftest.py` exists: `tests/conftest.py` and `tests/unit/pipeline/conftest.py`
- [x] Development environment available

### Knowledge Fragments Loaded

**Core (backend):**

- `data-factories.md` — factory patterns for pure-function tests (minimal relevance here)
- `test-quality.md` — deterministic, isolated, explicit assertions
- `test-healing-patterns.md` — failure pattern catalog
- `test-levels-framework.md` — unit test selection criteria
- `test-priorities-matrix.md` — P0–P3 priority assignment

**Playwright utils:** NOT loaded (backend stack, no browser testing)
**Pact utils:** NOT loaded (no contract testing in this story)

---

## Step 2: Generation Mode

**Mode selected:** AI generation (backend stack; no browser recording needed)

**Rationale:** All acceptance criteria test pure functions and module-level constants. Standard
pytest unit tests are the correct and only level required. No API endpoints, no UI flows, no
browser interaction.

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Scenarios Mapping

| AC | Test Level | Priority | Scenario |
|----|-----------|----------|---------|
| AC1 | Unit | P1 | Each constant has the exact expected value |
| AC1 | Unit | P1 | All 5 constants are module-level attributes |
| AC1 | Unit | P1 | Direct import syntax (`from ... import X`) works |
| AC2 | Unit | P1 | Wednesday 14:00 UTC → `(2, 14)` |
| AC2 | Unit | P1 | Monday midnight UTC → `(0, 0)` |
| AC2 | Unit | P1 | Saturday 23:00 UTC → `(5, 23)` |
| AC2 | Unit | P1 | Sunday midnight UTC → `(6, 0)` |
| AC3 | Unit | P1 | UTC+5 Wednesday 19:00 local → UTC Wednesday 14:00 → `(2, 14)` |
| AC3 | Unit | P1 | UTC+5 Thursday 01:00 local → UTC Wednesday 20:00 → `(2, 20)` |
| AC3 | Unit | P1 | UTC-5 Sunday 22:00 local → UTC Monday 03:00 → `(0, 3)` |
| AC4 | Unit | P1 | dow in 0–6 for all weekdays |
| AC4 | Unit | P1 | hour in 0–23 for all hours of day |
| AC4 | Unit | P1 | Return type is `tuple[int, int]` |
| AC4 | Unit | P2 | `weekday()` used (Mon=0, Sun=6), NOT `isoweekday()` (Mon=1, Sun=7) |

**No E2E or API tests generated.** This is a pure scaffolding story with no endpoints or UI.

**TDD Red Phase Requirement:** All tests decorated with `@pytest.mark.xfail(strict=True)` until
implementation files are created. Once `baseline/constants.py` and `baseline/computation.py`
exist, remove the `@pytest.mark.xfail` decorators and the tests should turn green.

---

## Failing Tests Created (RED Phase)

### Unit Tests (18 tests — all XFAIL)

#### `tests/unit/baseline/test_constants.py` (7 tests)

- **Test:** `test_mad_consistency_constant_value`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC1 — `MAD_CONSISTENCY_CONSTANT == 0.6745`

- **Test:** `test_mad_threshold_value`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC1 — `MAD_THRESHOLD == 4.0`

- **Test:** `test_min_correlated_deviations_value`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC1 — `MIN_CORRELATED_DEVIATIONS == 2`

- **Test:** `test_min_bucket_samples_value`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC1 — `MIN_BUCKET_SAMPLES == 3`

- **Test:** `test_max_bucket_values_value`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC1 — `MAX_BUCKET_VALUES == 12`

- **Test:** `test_constants_are_module_level_attributes`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC1 — all 5 names present in `dir(constants)`

- **Test:** `test_constants_direct_import`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC1 — canonical `from aiops_triage_pipeline.baseline.constants import ...` pattern

#### `tests/unit/baseline/test_computation.py` (11 tests)

- **Test:** `test_time_to_bucket_wednesday_14_utc`
  - **Status:** RED — `ImportError: No module named 'aiops_triage_pipeline.baseline'`
  - **Verifies:** AC2 — Wednesday UTC 14:00 → `(2, 14)`

- **Test:** `test_time_to_bucket_monday_midnight_utc`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC2 — Monday UTC 00:00 → `(0, 0)`

- **Test:** `test_time_to_bucket_saturday_23_utc`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC2 — Saturday UTC 23:00 → `(5, 23)`

- **Test:** `test_time_to_bucket_sunday_midnight_utc`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC2 — Sunday UTC 00:00 → `(6, 0)`

- **Test:** `test_time_to_bucket_non_utc_converts_to_utc`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC3 — UTC+5 Wed 19:00 → UTC Wed 14:00 → `(2, 14)`

- **Test:** `test_time_to_bucket_timezone_boundary_thursday_to_wednesday_utc`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC3 — UTC+5 Thu 01:00 local → UTC Wed 20:00 → `(2, 20)` (day boundary cross)

- **Test:** `test_time_to_bucket_negative_offset_advances_day`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC3 — UTC-5 Sun 22:00 → UTC Mon 03:00 → `(0, 3)` (negative offset, day advance)

- **Test:** `test_time_to_bucket_dow_in_valid_range`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC4 — dow ∈ [0,6] and hour ∈ [0,23] for all days of week

- **Test:** `test_time_to_bucket_hour_in_valid_range`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC4 — hour ∈ [0,23] for all 24 hours

- **Test:** `test_time_to_bucket_return_type_is_tuple_of_ints`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC4 — return type is `tuple[int, int]`

- **Test:** `test_time_to_bucket_uses_weekday_not_isoweekday`
  - **Status:** RED — `ImportError`
  - **Verifies:** AC4 — Monday=0, Sunday=6 (weekday convention, not isoweekday)

---

## Data Factories Created

**Not applicable.** Pure function tests with datetime literals — no factories needed.
All test inputs are constructed inline using `datetime(...)` with explicit `tzinfo` values.

---

## Fixtures Created

**Not applicable.** Pure functions with no side effects — no pytest fixtures required beyond
what is already provided by `tests/unit/pipeline/conftest.py` (reset_structlog).

---

## Mock Requirements

**None.** `time_to_bucket` is a pure function. `constants.py` has no I/O. No external
services to mock.

---

## Required data-testid Attributes

**Not applicable.** Backend-only story, no UI.

---

## Implementation Checklist

### Task 1: Create `tests/unit/baseline/__init__.py`

**File:** `tests/unit/baseline/__init__.py` ← ALREADY DONE by this ATDD workflow

- [x] `tests/unit/baseline/__init__.py` created (empty, marks package)

---

### Task 2: Create `src/aiops_triage_pipeline/baseline/__init__.py`

**File:** `src/aiops_triage_pipeline/baseline/__init__.py`

**Tasks to make `test_constants.py` tests pass:**

- [ ] Create `src/aiops_triage_pipeline/baseline/` directory
- [ ] Create empty `src/aiops_triage_pipeline/baseline/__init__.py`
- [ ] Verify: `python -c "from aiops_triage_pipeline import baseline"` succeeds

---

### Task 3: Create `src/aiops_triage_pipeline/baseline/constants.py`

**File:** `src/aiops_triage_pipeline/baseline/constants.py`

**Tasks:**

- [ ] Create `constants.py` with module docstring
- [ ] Add `MAD_CONSISTENCY_CONSTANT = 0.6745`
- [ ] Add `MAD_THRESHOLD = 4.0`
- [ ] Add `MIN_CORRELATED_DEVIATIONS = 2`
- [ ] Add `MIN_BUCKET_SAMPLES = 3`
- [ ] Add `MAX_BUCKET_VALUES = 12`
- [ ] Remove `@pytest.mark.xfail` decorators from `test_constants.py`
- [ ] Run test: `uv run pytest tests/unit/baseline/test_constants.py -v`
- [ ] All 7 tests pass (green phase for constants)

**Estimated Effort:** 0.25 hours

---

### Task 4: Create `src/aiops_triage_pipeline/baseline/computation.py`

**File:** `src/aiops_triage_pipeline/baseline/computation.py`

**Tasks:**

- [ ] Create `computation.py` with module docstring
- [ ] Implement `time_to_bucket(dt: datetime) -> tuple[int, int]`
  - [ ] Use `from datetime import datetime, timezone`
  - [ ] Body: `utc_dt = dt.astimezone(timezone.utc); return (utc_dt.weekday(), utc_dt.hour)`
  - [ ] Do NOT use `isoweekday()` — use `weekday()`
  - [ ] Do NOT use local time — always normalize to UTC first
- [ ] Remove `@pytest.mark.xfail` decorators from `test_computation.py`
- [ ] Run test: `uv run pytest tests/unit/baseline/test_computation.py -v`
- [ ] All 11 tests pass (green phase for computation)

**Estimated Effort:** 0.25 hours

---

### Task 5: Create stub `src/aiops_triage_pipeline/baseline/models.py`

**File:** `src/aiops_triage_pipeline/baseline/models.py`

**Tasks:**

- [ ] Create `models.py` with a module-level docstring only:
  ```python
  """Placeholder for BaselineDeviationContext and BaselineDeviationStageOutput (Story 1.2+)."""
  ```
- [ ] Do NOT implement any models (depends on Story 1.2+ context)

**Estimated Effort:** 0.1 hours

---

### Task 6: Full Regression

- [ ] Run: `TESTCONTAINERS_RYUK_DISABLED=true uv run pytest tests/unit/ -q -rs`
- [ ] Confirm 0 skipped tests and no regressions
- [ ] All 18 new tests now PASS (green phase)

---

## Running Tests

```bash
# Run all failing ATDD tests for this story (red phase)
uv run pytest tests/unit/baseline/ -v

# Run only constant tests
uv run pytest tests/unit/baseline/test_constants.py -v

# Run only computation tests
uv run pytest tests/unit/baseline/test_computation.py -v

# Full unit regression (confirm no regressions)
uv run pytest tests/unit/ -q -rs

# Full suite (with integration, requires Docker)
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

**TEA Agent Responsibilities:**

- [x] All 18 unit tests written and marked XFAIL (failing before implementation)
- [x] Tests cover all 5 ACs from story spec
- [x] Tests are pure pytest — no fixtures, factories, or mocks needed
- [x] Edge cases covered: midnight, end-of-week (Sat 23:00), timezone boundaries (day-crossings,
  negative offsets)
- [x] Deterministic test data (explicit `datetime(...)` literals with `tzinfo`)
- [x] `@pytest.mark.xfail(strict=True)` used — tests must FAIL now, will XPASS after impl
- [x] `tests/unit/baseline/__init__.py` created
- [x] ATDD checklist created at `artifact/test-artifacts/atdd-checklist-1-1-...md`

**Verification:**

```
18 xfailed in 0.12s
```

All 18 tests fail as expected. Failures due to missing implementation
(`ImportError: No module named 'aiops_triage_pipeline.baseline'`), not test bugs.

---

### GREEN Phase (DEV Agent — Next Steps)

**DEV Agent Responsibilities:**

1. Create `src/aiops_triage_pipeline/baseline/__init__.py` (empty)
2. Create `src/aiops_triage_pipeline/baseline/constants.py` with all 5 constants
3. Remove `@pytest.mark.xfail` from `test_constants.py`; run and verify all 7 pass
4. Create `src/aiops_triage_pipeline/baseline/computation.py` with `time_to_bucket`
5. Remove `@pytest.mark.xfail` from `test_computation.py`; run and verify all 11 pass
6. Create `src/aiops_triage_pipeline/baseline/models.py` (stub docstring only)
7. Run full regression; confirm 0 skipped, 0 regressions

**Key Principles:**

- One file at a time; run tests after each file to verify incrementally
- Exact canonical implementation already specified in dev notes (P2, P3 patterns)
- No magic numbers anywhere outside `constants.py`
- `weekday()` NOT `isoweekday()`

---

### REFACTOR Phase (After All Tests Pass)

- Review for any style issues (ruff lint: `uv run ruff check src/aiops_triage_pipeline/baseline/`)
- Ensure module docstrings follow existing pattern (one-line)
- Verify no `__all__` added (not used in this project)
- Confirm `from datetime import datetime, timezone` style matches project

---

## Next Steps

1. **Share this checklist** with the dev workflow
2. **Implement Task 2–5** following the Implementation Checklist above
3. **Run failing tests** to confirm RED phase: `uv run pytest tests/unit/baseline/ -v`
4. **Remove `@pytest.mark.xfail` decorators** after creating implementation files
5. **Re-run tests** to verify GREEN phase
6. **Run full regression**: `uv run pytest tests/unit/ -q -rs`
7. **Update documentation** (Task 5 in story: docs/project-structure.md, component-inventory.md,
   data-models.md)
8. When all tests pass and docs updated, mark story status to `done`

---

## Test Execution Evidence

### Initial Test Run (RED Phase Verification)

**Command:** `uv run pytest tests/unit/baseline/ -v`

**Results:**

```
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.0.2, pluggy-1.6.0
asyncio: mode=Mode.AUTO
collecting ... collected 18 items

tests/unit/baseline/test_computation.py::test_time_to_bucket_wednesday_14_utc XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_monday_midnight_utc XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_saturday_23_utc XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_sunday_midnight_utc XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_non_utc_converts_to_utc XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_timezone_boundary_thursday_to_wednesday_utc XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_negative_offset_advances_day XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_dow_in_valid_range XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_hour_in_valid_range XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_return_type_is_tuple_of_ints XFAIL
tests/unit/baseline/test_computation.py::test_time_to_bucket_uses_weekday_not_isoweekday XFAIL
tests/unit/baseline/test_constants.py::test_mad_consistency_constant_value XFAIL
tests/unit/baseline/test_constants.py::test_mad_threshold_value XFAIL
tests/unit/baseline/test_constants.py::test_min_correlated_deviations_value XFAIL
tests/unit/baseline/test_constants.py::test_min_bucket_samples_value XFAIL
tests/unit/baseline/test_constants.py::test_max_bucket_values_value XFAIL
tests/unit/baseline/test_constants.py::test_constants_are_module_level_attributes XFAIL
tests/unit/baseline/test_constants.py::test_constants_direct_import XFAIL

18 xfailed in 0.12s
```

**Summary:**

- Total tests: 18
- Passing: 0 (expected — feature not implemented)
- XFAIL: 18 (all fail due to `ImportError: No module named 'aiops_triage_pipeline.baseline'`)
- Status: ✅ RED phase verified

---

## Knowledge Base References Applied

- **test-levels-framework.md** — Unit test selection (pure functions, no I/O, fast feedback)
- **test-priorities-matrix.md** — P1 priority (foundation dependency; all 1.2/1.3/2.x stories blocked)
- **test-quality.md** — Deterministic, isolated, explicit inline assertions; no factories needed
- **data-factories.md** — Consulted; factory pattern not needed (datetime literals are sufficient)
- **test-healing-patterns.md** — `@pytest.mark.xfail(strict=True)` prevents accidental pass-through

---

**Generated by BMad TEA Agent** — 2026-04-05
