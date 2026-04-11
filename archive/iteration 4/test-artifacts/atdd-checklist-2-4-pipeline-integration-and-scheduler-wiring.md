---
stepsCompleted: ['step-01-preflight-and-context', 'step-02-generation-mode', 'step-03-test-strategy', 'step-04-generate-tests', 'step-04c-aggregate', 'step-05-validate-and-complete']
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-04-05'
story_id: '2-4-pipeline-integration-and-scheduler-wiring'
inputDocuments:
  - artifact/implementation-artifacts/2-4-pipeline-integration-and-scheduler-wiring.md
  - src/aiops_triage_pipeline/pipeline/scheduler.py
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/baseline/models.py
  - src/aiops_triage_pipeline/baseline/client.py
  - src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py
  - src/aiops_triage_pipeline/pipeline/stages/anomaly.py
  - src/aiops_triage_pipeline/pipeline/stages/gating.py
  - src/aiops_triage_pipeline/contracts/gate_input.py
  - src/aiops_triage_pipeline/config/settings.py
  - src/aiops_triage_pipeline/models/anomaly.py
  - src/aiops_triage_pipeline/models/evidence.py
  - tests/unit/pipeline/test_scheduler.py
  - tests/unit/test_main.py
  - tests/unit/pipeline/stages/test_baseline_deviation.py
  - _bmad/tea/testarch/knowledge/data-factories.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-priorities-matrix.md
---

# ATDD Checklist: Story 2-4 Pipeline Integration & Scheduler Wiring

## Step 1: Preflight & Context Loading — COMPLETE

### Stack Detection
- **Detected Stack**: `backend`
- **Evidence**: `pyproject.toml` present; no frontend indicators
- **Test Framework**: `conftest.py` present at `tests/conftest.py`

### Story Summary
Story 2.4 wires `BaselineDeviationStageOutput` findings from the Story 2.3 stage into the full hot-path pipeline, enabling BASELINE_DEVIATION findings to flow through topology → gating → casefile → outbox → dispatch unchanged.

**Key changes required:**
1. `pipeline/scheduler.py` — NEW `run_baseline_deviation_stage_cycle()` function
2. `__main__.py` — wire stage, `_merge_baseline_deviation_findings()`, `_update_baseline_buckets()`
3. `contracts/gate_input.py` — extend `GateInputV1.anomaly_family` Literal
4. `pipeline/stages/gating.py` — extend `_anomaly_family_from_gate_finding_name()` + related Literals
5. `config/settings.py` — `BASELINE_DEVIATION_STAGE_ENABLED: bool = True`

### Prerequisites Check
- ✅ Story has clear acceptance criteria (AC 1–8)
- ✅ `conftest.py` present in tests/
- ✅ Development environment available (Python/uv project)
- ✅ Existing test patterns available in `tests/unit/pipeline/`

---

## Step 2: Generation Mode — COMPLETE

**Mode:** AI Generation (backend Python stack — no browser recording required)

---

## Step 3: Test Strategy — COMPLETE

### AC → Test Level Mapping

| AC | Test Scenario | Level | Priority |
|---|---|---|---|
| AC 1 | `run_baseline_deviation_stage_cycle()` calls stage fn with correct kwargs | Unit | P0 |
| AC 1 | Records `stage="stage2_5_baseline_deviation"` latency | Unit | P0 |
| AC 1 | Records latency in finally even on exception | Unit | P0 |
| AC 1 | Calls alert_evaluator when provided | Unit | P1 |
| AC 2 | `_merge_baseline_deviation_findings()` injects into correct scope | Unit | P0 |
| AC 2 | Merge preserves existing gate findings | Unit | P0 |
| AC 2 | Merge no-op when empty findings | Unit | P1 |
| AC 2 | Returns new EvidenceStageOutput (not mutation) | Unit | P1 |
| AC 2 | Multiple scopes merged correctly | Unit | P1 |
| AC 3 | `GateInputV1` accepts `anomaly_family="BASELINE_DEVIATION"` | Unit | P0 |
| AC 3 | `_anomaly_family_from_gate_finding_name("baseline_deviation")` → `"BASELINE_DEVIATION"` | Unit | P0 |
| AC 3 | Case-insensitive match for BASELINE_DEVIATION | Unit | P1 |
| AC 3 | `_sustained_identity_key` handles BASELINE_DEVIATION 3-element scope | Unit | P1 |
| AC 3 | `_sustained_identity_key` handles BASELINE_DEVIATION 4-element scope | Unit | P1 |
| AC 6 | Stage disabled → empty output, no stage call | Unit | P0 |
| AC 6 | Flag defaults to True | Unit | P1 |
| AC 7 | `_update_baseline_buckets()` calls `update_bucket` per scope/metric | Unit | P0 |
| AC 7 | Uses max value for dedup | Unit | P1 |
| AC 7 | Error isolation per scope (fail-open) | Unit | P1 |
| AC 7 | Correct (dow, hour) bucket from evaluation_time | Unit | P1 |
| AC 7 | No-op when no evidence rows | Unit | P2 |

---

## Step 4 + 4C: Test Generation — COMPLETE

### Generated Files

#### NEW: `tests/unit/pipeline/test_baseline_deviation_wiring.py`
- **17 unit tests** covering AC 1, AC 2, AC 6, AC 7
- Fails at collection time with `ImportError` (correct TDD red phase behavior):
  - `run_baseline_deviation_stage_cycle` not in `pipeline/scheduler.py`
  - `_merge_baseline_deviation_findings` not in `__main__.py`
  - `_update_baseline_buckets` not in `__main__.py`

#### NEW: `tests/unit/contracts/test_gate_input_baseline_deviation.py`
- **10 unit tests** covering AC 3
- 3 tests FAIL with correct errors (TDD red phase):
  - `test_gate_input_v1_accepts_baseline_deviation_family` → `pydantic ValidationError`
  - `test_anomaly_family_from_gate_finding_name_handles_baseline_deviation` → `ValueError`
  - `test_anomaly_family_from_gate_finding_name_case_insensitive` → `ValueError`
- 7 tests PASS (regression guards for existing families — correct behavior)

### TDD Red Phase Validation

- ✅ No `@pytest.mark.xfail` used (per story constraint)
- ✅ Tests assert EXPECTED behavior, not placeholder assertions
- ✅ Failures due to missing implementation, not test bugs
- ✅ Ruff linting: both files pass `ruff check` with zero errors
- ✅ No regressions: 1282 existing unit tests still pass

---

## Step 5: Validation & Completion — COMPLETE

### Checklist Against Story AC 5.3 (mandatory test names)

- ✅ `test_run_baseline_deviation_stage_cycle_calls_stage_function`
- ✅ `test_run_baseline_deviation_stage_cycle_records_latency`
- ✅ `test_merge_baseline_deviation_findings_injects_into_gate_scope`
- ✅ `test_merge_baseline_deviation_findings_preserves_existing_gate_findings`
- ✅ `test_merge_baseline_deviation_findings_no_op_when_empty`
- ✅ `test_update_baseline_buckets_calls_update_bucket_per_scope_metric`
- ✅ `test_update_baseline_buckets_uses_max_value_for_dedup`
- ✅ `test_update_baseline_buckets_error_isolation`
- ✅ `test_baseline_deviation_stage_disabled_returns_empty_output`

### AC 6.1 (mandatory test names)

- ✅ `test_gate_input_v1_accepts_baseline_deviation_family`
- ✅ `test_anomaly_family_from_gate_finding_name_handles_baseline_deviation`
- ✅ `test_anomaly_family_from_gate_finding_name_case_insensitive` (named `test_anomaly_family_from_gate_finding_name_case_insensitive`)
- ✅ `test_sustained_identity_key_handles_baseline_deviation` (covered by two tests: 3-element + 4-element variants)

### Summary

| Metric | Value |
|---|---|
| Test files created | 2 |
| Total new tests | 27 |
| Failing tests (TDD RED) | 20 (ImportError collection failure = 17 + 3 assertion failures) |
| Passing tests (regression guards) | 7 |
| Existing tests regression | 0 regressions (1282 pass) |
| Ruff lint | ✅ Clean |

### Next Steps for DEV

1. Implement `run_baseline_deviation_stage_cycle()` in `pipeline/scheduler.py` (Task 1)
2. Extend `GateInputV1.anomaly_family` Literal in `contracts/gate_input.py` (Task 2)
3. Update `_anomaly_family_from_gate_finding_name()` in `pipeline/stages/gating.py` (Task 2)
4. Implement `_merge_baseline_deviation_findings()` and `_update_baseline_buckets()` in `__main__.py` (Task 3)
5. Add `BASELINE_DEVIATION_STAGE_ENABLED: bool = True` to `config/settings.py` (Task 4)
6. Run `uv run pytest tests/unit/pipeline/test_baseline_deviation_wiring.py tests/unit/contracts/test_gate_input_baseline_deviation.py -v` to verify green phase

### Execution Commands

```bash
# Run new wiring tests (will fail until implemented)
uv run pytest tests/unit/pipeline/test_baseline_deviation_wiring.py -v

# Run gate input tests (3 will fail until implemented)
uv run pytest tests/unit/contracts/test_gate_input_baseline_deviation.py -v

# Full regression suite
uv run pytest tests/unit/ -q
```
