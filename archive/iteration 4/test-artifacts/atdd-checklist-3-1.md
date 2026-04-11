---
stepsCompleted: ['step-01-preflight-and-context', 'step-02-generation-mode', 'step-03-test-strategy', 'step-04-generate-tests', 'step-04c-aggregate', 'step-05-validate-and-complete']
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-04-05'
workflowType: 'testarch-atdd'
inputDocuments:
  - artifact/implementation-artifacts/3-1-baseline-deviation-llm-diagnosis-prompt-and-processing.md
  - src/aiops_triage_pipeline/diagnosis/prompt.py
  - src/aiops_triage_pipeline/contracts/triage_excerpt.py
  - src/aiops_triage_pipeline/contracts/gate_input.py
  - tests/unit/diagnosis/test_prompt.py
---

# ATDD Checklist - Epic 3, Story 3.1: BASELINE_DEVIATION LLM Diagnosis Prompt & Processing

**Date:** 2026-04-05
**Author:** Sas
**Primary Test Level:** Unit (backend Python — pytest)

---

## Story Summary

On-call engineers need each BASELINE_DEVIATION case file to include an LLM-generated hypothesis explaining the likely cause of correlated metric deviations, providing an actionable investigation starting point. This story extends `build_llm_prompt()` in `diagnosis/prompt.py` to handle `BASELINE_DEVIATION` cases and extends `TriageExcerptV1.anomaly_family` Literal to include the new family.

**As an** on-call engineer
**I want** each baseline deviation case file to include an LLM-generated hypothesis explaining the likely cause of correlated deviations
**So that** I have an actionable investigation starting point rather than raw statistics

---

## Acceptance Criteria

1. `_handle_cold_path_event()` invokes LLM diagnosis asynchronously for BASELINE_DEVIATION cases; `TriageExcerptV1.anomaly_family` Literal extended to include `"BASELINE_DEVIATION"` (additive-only, Procedure A)
2. `build_llm_prompt()` includes `BASELINE DEVIATION CONTEXT` section with metric names and directions extracted from `reason_codes`; includes topology context (`topic_role`, `routing_key`); includes hypothesis framing instruction; includes BASELINE_DEVIATION few-shot example
3. `DiagnosisReportV1` verdict is framed as a hypothesis; appended via `persist_casefile_diagnosis_write_once()`
4. Hash-chain integrity: `triage_hash` links correctly; `DiagnosisReportV1` valid; `diagnosis_hash` computed
5. Unit tests in `tests/unit/diagnosis/test_prompt.py` — 4 new tests verifying deviation context, hypothesis framing, topology context, and few-shot example

---

## Failing Tests Created (RED Phase)

### Unit Tests (4 new tests)

**File:** `tests/unit/diagnosis/test_prompt.py` (appended — existing 10 tests untouched)

- **Test:** `test_build_llm_prompt_baseline_deviation_includes_deviation_context`
  - **Status:** RED - `pydantic_core.ValidationError: Input should be 'CONSUMER_LAG', 'VOLUME_DROP' or 'THROUGHPUT_CONSTRAINED_PROXY'`
  - **Failure Reason:** `TriageExcerptV1.anomaly_family` Literal does not yet include `"BASELINE_DEVIATION"`
  - **After Task 1 fix:** Will fail at `assert "BASELINE DEVIATION CONTEXT" in result` (Task 2 not done)
  - **Verifies:** Prompt contains `BASELINE DEVIATION CONTEXT` section with `consumer_lag.offset`, `producer_rate`, `HIGH`, `LOW`
  - **AC:** AC2, AC5

- **Test:** `test_build_llm_prompt_baseline_deviation_hypothesis_framing`
  - **Status:** RED - `pydantic_core.ValidationError` (same root cause)
  - **After Task 1 fix:** Will fail at hypothesis framing assertion (Task 2 not done)
  - **Verifies:** Prompt contains hypothesis framing language (`possible interpretation`, `likely`, `hypothesis`, or `suspected`)
  - **AC:** AC2, AC5

- **Test:** `test_build_llm_prompt_baseline_deviation_topology_context`
  - **Status:** RED - `pydantic_core.ValidationError` (same root cause)
  - **After Task 1 fix:** Will pass (topology context already rendered by existing prompt code for any anomaly family)
  - **Verifies:** `topic_role` (value `SHARED_TOPIC`) and `routing_key` (value `OWN::Streaming::Metrics`) appear in prompt
  - **AC:** AC2, AC5

- **Test:** `test_build_llm_prompt_baseline_deviation_few_shot_example`
  - **Status:** RED - `pydantic_core.ValidationError` (same root cause)
  - **After Task 1 fix:** Will fail at `result.count("BASELINE_DEVIATION") >= 2` assertion (Task 2 not done)
  - **Verifies:** `BASELINE_DEVIATION` appears at least twice (once in case context, once in few-shot example)
  - **AC:** AC2, AC5

---

## Helper Created

`_make_baseline_deviation_excerpt()` — factory helper added to `test_prompt.py`:
- Creates `TriageExcerptV1` with `anomaly_family="BASELINE_DEVIATION"`
- Uses `gate_input.Finding` (not `AnomalyFinding`) per `TriageExcerptV1.findings` contract
- `reason_codes=("BASELINE_DEV:consumer_lag.offset:HIGH", "BASELINE_DEV:producer_rate:LOW")`
- `topic_role="SHARED_TOPIC"`, `routing_key="OWN::Streaming::Metrics"`

---

## Data Factories

No new factory files created. `_make_baseline_deviation_excerpt()` is a module-level helper function (following existing `_make_excerpt()` pattern in `test_prompt.py`). All imports are at module level per Epic 2 retro lesson L4.

---

## Implementation Checklist

### Task 1: Extend `TriageExcerptV1.anomaly_family` Literal

**File:** `src/aiops_triage_pipeline/contracts/triage_excerpt.py`

**Tasks to make tests unblock first failure:**
- [ ] Change `anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]` to `Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]`
- [ ] Run `uv run ruff check src/aiops_triage_pipeline/contracts/triage_excerpt.py`
- [ ] Run `uv run pytest tests/unit/diagnosis/test_prompt.py -v` → 3 tests should still fail (prompt assertions), `test_build_llm_prompt_baseline_deviation_topology_context` should now PASS

**Estimated Effort:** 0.1 hours

---

### Task 2: Extend `build_llm_prompt()` for BASELINE_DEVIATION

**File:** `src/aiops_triage_pipeline/diagnosis/prompt.py`

**Tasks to make remaining 3 tests pass:**
- [ ] Add conditional block: `if triage_excerpt.anomaly_family == "BASELINE_DEVIATION":`
- [ ] Extract metric/direction pairs from `reason_codes` using `rc.removeprefix("BASELINE_DEV:").rsplit(":", 1)` for codes starting with `"BASELINE_DEV:"`
- [ ] Build `BASELINE DEVIATION CONTEXT` block (metric name + direction per code)
- [ ] Add hypothesis framing instruction: text including `possible interpretation` or `LIKELY`/`SUSPECTED` language
- [ ] Add BASELINE_DEVIATION few-shot example block alongside (or replacing) CONSUMER_LAG example
- [ ] Append the deviation context block to `case_context`
- [ ] Run `uv run ruff check src/aiops_triage_pipeline/diagnosis/prompt.py`
- [ ] Run `uv run pytest tests/unit/diagnosis/test_prompt.py -v` → all 14 tests pass

**Estimated Effort:** 1.0 hours

---

## Running Tests

```bash
# Run all tests for this story (new + existing)
uv run pytest tests/unit/diagnosis/test_prompt.py -v

# Run only the 4 new BASELINE_DEVIATION tests
uv run pytest tests/unit/diagnosis/test_prompt.py -v -k "baseline_deviation"

# Run full unit diagnosis suite
uv run pytest tests/unit/diagnosis/ -v

# Full regression
uv run pytest tests/unit/ -q
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

- ✅ 4 failing tests written and appended to `tests/unit/diagnosis/test_prompt.py`
- ✅ `_make_baseline_deviation_excerpt()` helper created (module-level, all imports at top)
- ✅ Tests fail with clear, actionable error messages pointing to missing implementation
- ✅ 10 existing tests continue to PASS (no regressions)
- ✅ No `@pytest.mark.xfail` used — proper failing tests
- ✅ No imports inside test functions

### GREEN Phase (DEV Team — Next Steps)

1. **Task 1 first** — extend `TriageExcerptV1.anomaly_family` Literal (unblocks all 4 tests from ValidationError)
2. **Run tests** — `uv run pytest tests/unit/diagnosis/test_prompt.py -k baseline_deviation -v` — expect 3 still failing (prompt assertions), 1 passing (topology)
3. **Task 2** — extend `build_llm_prompt()` with BASELINE DEVIATION CONTEXT block, hypothesis framing, few-shot example
4. **Run tests** — all 4 new tests should pass; all 10 existing tests still pass
5. **Task 6.1** — full regression: `uv run pytest tests/unit/ -q`

### REFACTOR Phase (After All Tests Pass)

- Review prompt formatting for readability
- Ensure no duplication between few-shot examples
- Run `uv run ruff check src/` for lint hygiene

---

## Test Execution Evidence (RED Phase Verification)

**Command:** `uv run pytest tests/unit/diagnosis/test_prompt.py -v --tb=short`

**Results:**
```
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_returns_non_empty_string PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_contains_anomaly_family PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_contains_evidence_summary PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_instructs_json_output PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_instructs_unknown_propagation PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_instructs_evidence_citation PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_contains_evidence_status_map PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_contains_finding_id PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_contains_full_finding_fields PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_contains_routing_context_and_guidance_blocks PASSED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_baseline_deviation_includes_deviation_context FAILED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_baseline_deviation_hypothesis_framing FAILED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_baseline_deviation_topology_context FAILED
tests/unit/diagnosis/test_prompt.py::test_build_llm_prompt_baseline_deviation_few_shot_example FAILED
========================= 4 failed, 10 passed in 0.12s =========================
```

**Summary:**
- Total tests: 14
- Passing: 10 (all pre-existing tests — 0 regressions)
- Failing: 4 (all new BASELINE_DEVIATION tests — expected RED phase)
- Status: ✅ RED phase verified

**Expected Failure Messages (all 4):**
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for TriageExcerptV1
anomaly_family
  Input should be 'CONSUMER_LAG', 'VOLUME_DROP' or 'THROUGHPUT_CONSTRAINED_PROXY'
  [type=literal_error, input_value='BASELINE_DEVIATION', input_type=str]
```

---

## Notes

- Tests fail at `_make_baseline_deviation_excerpt()` due to `TriageExcerptV1` Literal validation — this is the correct first failure, pointing to Task 1
- After Task 1: `test_build_llm_prompt_baseline_deviation_topology_context` will immediately PASS (topology fields already rendered by existing prompt code); the other 3 will fail at prompt content assertions
- After Task 2: all 4 new tests pass
- No new files created — all changes are additive to existing files per project structure boundary rules
- `_make_baseline_deviation_excerpt()` follows the `gate_input.Finding` pattern (NOT `AnomalyFinding`) consistent with `TriageExcerptV1.findings` contract (Dev Notes §Critical Architecture Gap)

---

**Generated by BMad TEA Agent (testarch-atdd workflow)** — 2026-04-05
