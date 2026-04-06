---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-05'
inputDocuments:
  - artifact/implementation-artifacts/3-2-deterministic-fallback-diagnosis.md
  - tests/unit/diagnosis/test_fallback.py
  - tests/unit/diagnosis/test_graph.py
  - src/aiops_triage_pipeline/diagnosis/fallback.py
  - src/aiops_triage_pipeline/diagnosis/graph.py
  - src/aiops_triage_pipeline/contracts/gate_input.py
  - src/aiops_triage_pipeline/contracts/triage_excerpt.py
  - _bmad/tea/config.yaml
---

# ATDD Checklist: Story 3-2 — Deterministic Fallback Diagnosis

## Overview

- **Story ID**: `3-2-deterministic-fallback-diagnosis`
- **Story Type**: VERIFICATION-ONLY (zero production code changes)
- **Stack**: Backend (Python / pytest / asyncio)
- **Execution Mode**: Sequential (single agent)
- **TDD Phase**: GREEN — tests pass immediately (code already correct)
- **Date**: 2026-04-05

---

## Step 1: Preflight & Context

### Stack Detection

- `pyproject.toml` present → `detected_stack = backend`
- No `package.json` with frontend dependencies
- No `playwright.config.ts` or `cypress.config.ts`
- Test framework: `pytest` with `anyio` + `asyncio` mode

### Prerequisites

- Story file loaded: `artifact/implementation-artifacts/3-2-deterministic-fallback-diagnosis.md`
- Story status: `ready-for-dev`
- Acceptance criteria: 5 ACs clearly defined
- Existing test files read: `test_fallback.py` (7 tests), `test_graph.py` (37 tests)
- Production code read: `fallback.py`, `graph.py`
- `BASELINE_DEVIATION` Literal confirmed live in `contracts/triage_excerpt.py` (Story 3-1 complete)

### Key Finding (Verification-Only)

`build_fallback_report()` in `fallback.py` is **fully family-agnostic** — no anomaly-family parameter, no branching. The fallback pipeline in `graph.py` handles ALL families identically via `_persist_fallback_and_record()` → `_make_and_persist_fallback()`. Zero production code changes required.

---

## Step 2: Generation Mode

- **Mode**: AI Generation (backend stack, no browser recording needed)
- **Test Type**: Unit tests using existing pytest patterns
- **Rationale**: Pure function under test (`build_fallback_report`) and async cold-path integration (`run_cold_path_diagnosis`) — unit level is correct

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Mapping

| AC | Test | Level | Priority | File |
|----|------|-------|----------|------|
| AC 1 — fallback handles BASELINE_DEVIATION generically | verified by AC 4 & 5 tests | Unit | P0 | both |
| AC 2 — `build_fallback_report()` returns correct shape | `test_build_fallback_report_baseline_deviation_timeout` | Unit | P0 | test_fallback.py |
| AC 2 — `build_fallback_report()` returns correct shape | `test_build_fallback_report_baseline_deviation_unavailable` | Unit | P0 | test_fallback.py |
| AC 2 — `build_fallback_report()` returns correct shape | `test_build_fallback_report_baseline_deviation_error` | Unit | P0 | test_fallback.py |
| AC 3 — D6 invariant (no hot-path coupling) | structural — confirmed by import analysis, no test needed | N/A | P2 | — |
| AC 4 — unit tests for build_fallback_report | 3 new tests in test_fallback.py | Unit | P0 | test_fallback.py |
| AC 5 — graph integration fallback tests | 2 new tests in test_graph.py | Unit/Integration | P0 | test_graph.py |

### Test Phase

**GREEN phase** (not RED) — this is verification-only. The production code is already correct, so tests are written to PASS immediately. No `@pytest.mark.xfail`, no `pytest.skip()`.

---

## Step 4: Test Generation (Sequential Mode)

### Worker A — `test_fallback.py` (3 new tests)

**Appended to**: `/home/sas/workspace/aiops/tests/unit/diagnosis/test_fallback.py`

Tests added:

1. **`test_build_fallback_report_baseline_deviation_timeout`**
   - Calls `build_fallback_report(("LLM_TIMEOUT",), case_id="bd-case-001")`
   - Asserts: `verdict == "UNKNOWN"`, `confidence == LOW`, `reason_codes == ("LLM_TIMEOUT",)`, `case_id == "bd-case-001"`, `triage_hash is None`, `fault_domain is None`
   - Round-trip `DiagnosisReportV1.model_validate(report.model_dump(mode="json"))` passes

2. **`test_build_fallback_report_baseline_deviation_unavailable`**
   - Calls `build_fallback_report(("LLM_UNAVAILABLE",))` (no case_id — tests default path)
   - Asserts: same invariants, `case_id is None`
   - Round-trip validation passes

3. **`test_build_fallback_report_baseline_deviation_error`**
   - Calls `build_fallback_report(("LLM_ERROR",))`
   - Asserts: same invariants
   - Round-trip validation passes

### Worker B — `test_graph.py` (2 new tests)

**Appended to**: `/home/sas/workspace/aiops/tests/unit/diagnosis/test_graph.py`

Helper added:

- **`_make_baseline_deviation_excerpt(case_id="bd-001")`** — mirrors `_make_eligible_excerpt()` with `anomaly_family="BASELINE_DEVIATION"` and one `Finding` with `reason_codes=("BASELINE_DEV:consumer_lag.offset:HIGH",)`

Tests added:

1. **`test_run_cold_path_diagnosis_baseline_deviation_timeout_produces_fallback`**
   - `mock_client.invoke = AsyncMock(side_effect=asyncio.TimeoutError())`
   - BASELINE_DEVIATION excerpt passed to `run_cold_path_diagnosis()`
   - Asserts: `report.reason_codes == ("LLM_TIMEOUT",)`, `report.triage_hash == _FAKE_TRIAGE_HASH`
   - Asserts: `mock_store.put_if_absent.assert_called_once()` (diagnosis.json persisted)

2. **`test_run_cold_path_diagnosis_baseline_deviation_unavailable_produces_fallback`**
   - `mock_client.invoke = AsyncMock(side_effect=httpx.ConnectError("simulated unavailability"))`
   - BASELINE_DEVIATION excerpt passed to `run_cold_path_diagnosis()`
   - Asserts: `report.reason_codes == ("LLM_UNAVAILABLE",)`, `report.triage_hash == _FAKE_TRIAGE_HASH`
   - Asserts: `mock_store.put_if_absent.assert_called_once()`

---

## Step 5: Validation & Completion

### TDD Phase Compliance

- **Phase**: GREEN (verification-only — code already correct)
- No `@pytest.mark.xfail` used
- No `pytest.skip()` used
- All 5 new tests PASS

### Test Results

```
tests/unit/diagnosis/test_fallback.py — 10 passed (7 existing + 3 new)
tests/unit/diagnosis/test_graph.py   — 39 passed (37 existing + 2 new)
Full unit suite                       — 1319 passed (1314 baseline + 5 new)
```

### Lint Results

```
uv run ruff check tests/unit/diagnosis/test_fallback.py tests/unit/diagnosis/test_graph.py
→ All checks passed!

uv run ruff check src/ tests/
→ All checks passed!
```

### Acceptance Criteria Coverage

- [x] AC 1 — Verified: `graph.py` fallback wiring handles BASELINE_DEVIATION without changes
- [x] AC 2 — Verified: `build_fallback_report()` returns `verdict="UNKNOWN"`, `confidence=LOW`, `triage_hash=None`, `fault_domain=None` for BASELINE_DEVIATION reason codes
- [x] AC 3 — Verified: `build_fallback_report()` is pure synchronous function, no imports from hot-path, no shared state (D6 invariant)
- [x] AC 4 — 3 new tests in `test_fallback.py` — all pass with round-trip schema validation
- [x] AC 5 — 2 new tests in `test_graph.py` — all pass with `triage_hash` injection and `put_if_absent` call count assertions

### Files Modified

| File | Action | Tests Added |
|------|--------|-------------|
| `tests/unit/diagnosis/test_fallback.py` | Appended 3 tests | 3 |
| `tests/unit/diagnosis/test_graph.py` | Added `Finding` import + helper + 2 tests | 2 |

### Files Verified (No Changes)

| File | Status |
|------|--------|
| `src/aiops_triage_pipeline/diagnosis/fallback.py` | No changes — already family-agnostic |
| `src/aiops_triage_pipeline/diagnosis/graph.py` | No changes — fallback wiring already handles all families |

### Summary

Story 3-2 is **complete**. All 5 new acceptance tests pass. Zero production code changes were made. The BASELINE_DEVIATION fallback path was already fully wired in `graph.py` and `fallback.py` — this story delivers test evidence confirming that invariant.
