---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-11'
story_id: '1-3'
tdd_phase: RED
inputDocuments:
  - artifact/implementation-artifacts/1-3-evidence-diagnosis-otlp-instruments.md
  - src/aiops_triage_pipeline/health/metrics.py
  - tests/unit/health/test_metrics.py
  - _bmad/tea/config.yaml
---

# ATDD Checklist — Story 1.3: Evidence & Diagnosis OTLP Instruments

## Step 1: Preflight & Context

### Stack Detection
- **Detected stack:** `backend` (pyproject.toml present; no package.json/playwright.config.ts)
- **Test framework:** pytest (conftest.py, pyproject.toml dev deps)

### Prerequisites
- [x] Story approved with clear acceptance criteria (status: ready-for-dev)
- [x] Test framework configured (`tests/unit/health/conftest.py`)
- [x] Development environment available (`uv run`)

### Story Context Loaded
- **Story:** 1.3 Evidence & Diagnosis OTLP Instruments
- **Acceptance Criteria:**
  - AC1: `aiops.evidence.status` up-down-counter with labels: `scope`, `metric_key`, `status`, `topic`; uppercase status values; reset-and-set delta lifecycle
  - AC2: Full label granularity preserved for PromQL aggregation (~hundreds of series)
  - AC3: `aiops.diagnosis.completed_total` counter with labels: `confidence`, `fault_domain_present`, `topic`; uppercase confidence; `fault_domain_present` as string "true"/"false"
  - AC4: Both instruments in `health/metrics.py`; unit tests assert metric name + label set; follow existing patterns (NFR14)

### Framework & Patterns Loaded
- `_RecordingInstrument` monkeypatch class already defined in test_metrics.py (do NOT redefine)
- `monkeypatch.setattr(metrics, "_instrument_name", ...)` pattern established
- State reset via `monkeypatch.setattr(metrics, "_state_dict", {})` pattern established

---

## Step 2: Generation Mode

**Mode selected:** AI Generation (backend stack — no browser recording needed)

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Scenarios

| AC | Scenario | Level | Priority |
|---|---|---|---|
| AC1, AC4 | evidence.status emits +1 with correct 4-label set | Unit | P0 |
| AC1 | status values are uppercase (PRESENT not present) | Unit | P0 |
| AC1 | all 4 EvidenceStatus enum values accepted | Unit | P0 |
| AC1 | delta accounting: -1 old + +1 new on status transition | Unit | P0 |
| AC1 | no-op when same status repeated (no ghost series) | Unit | P1 |
| AC2 | full label granularity: all 4 labels on every emission; no routing_key | Unit | P1 |
| AC3, AC4 | diagnosis.completed emits +1 with correct 3-label set | Unit | P0 |
| AC3 | all 3 DiagnosisConfidence values: LOW/MEDIUM/HIGH | Unit | P0 |
| AC3 | fault_domain_present is string "true"/"false" not bool | Unit | P0 |
| AC3 | diagnosis counter increments by exactly 1 per call | Unit | P1 |
| AC4 | _evidence_status instrument exists with .add() | Unit | P0 |
| AC4 | _diagnosis_completed_total instrument exists with .add() | Unit | P0 |
| AC4 | record_evidence_status() public function callable | Unit | P0 |
| AC4 | record_diagnosis_completed() public function callable | Unit | P0 |
| AC4 | _current_evidence_status state dict exists | Unit | P1 |

### TDD Red Phase Requirements
All 15 tests are designed to **fail before implementation** — they reference `_evidence_status`, `_diagnosis_completed_total`, `record_evidence_status`, `record_diagnosis_completed`, and `_current_evidence_status` attributes that do not yet exist in `health/metrics.py`.

---

## Step 4: Test Generation

### Tests Generated — RED PHASE

**File:** `tests/unit/health/test_metrics.py` (appended to existing file)

**New test functions (15 total):**

#### AC1 / AC4 — P0
1. `test_record_evidence_status_emits_expected_metric_name_and_labels` — verifies +1 with all 4 labels
2. `test_record_evidence_status_emits_uppercase_status_values` — verifies "PRESENT" not "present"
3. `test_record_evidence_status_accepts_all_four_status_values` — PRESENT/UNKNOWN/ABSENT/STALE
4. `test_record_evidence_status_emits_delta_on_status_transition` — -1 old + +1 new (3 calls total)

#### AC1 — P1
5. `test_record_evidence_status_no_emission_when_status_unchanged` — no-op on repeated same status

#### AC2 — P1
6. `test_record_evidence_status_preserves_full_label_granularity` — 4 labels only; no routing_key

#### AC3 / AC4 — P0
7. `test_record_diagnosis_completed_emits_expected_metric_name_and_labels` — +1 with 3 labels
8. `test_record_diagnosis_completed_accepts_all_confidence_values` — LOW/MEDIUM/HIGH
9. `test_record_diagnosis_completed_fault_domain_present_is_string` — "true"/"false" as str
10. `test_record_diagnosis_completed_increments_by_one` — exactly +1 per call

#### AC4 — P0
11. `test_evidence_status_instrument_is_defined_in_metrics_module` — _evidence_status has .add()
12. `test_diagnosis_completed_total_instrument_is_defined_in_metrics_module` — _diagnosis_completed_total has .add()
13. `test_record_evidence_status_function_is_callable` — public function exists
14. `test_record_diagnosis_completed_function_is_callable` — public function exists

#### AC4 — P1
15. `test_current_evidence_status_state_dict_exists_in_metrics_module` — state dict exists

---

## Step 5: Validate & Complete

### TDD Red Phase Verification

```
pytest tests/unit/health/test_metrics.py -v --tb=short
======================== 15 failed, 27 passed in 0.30s =========================
```

- [x] 15 new tests FAIL (red phase — implementation not yet done)
- [x] 27 existing tests PASS (no regressions)
- [x] All new tests reference non-existent attributes/functions
- [x] Failure messages are informative (AssertionError with clear message)
- [x] No orphaned browser sessions (backend-only tests)
- [x] No temp artifacts in random locations

### Checklist Validation

- [x] Prerequisites satisfied (story ready-for-dev, conftest.py present)
- [x] Test file appended to existing `tests/unit/health/test_metrics.py` (no new file created)
- [x] All 4 acceptance criteria covered by at least one test
- [x] Tests designed to fail before implementation (red phase)
- [x] `_RecordingInstrument` pattern reused (not redefined)
- [x] `monkeypatch.setattr` used for instrument injection
- [x] State reset via `monkeypatch.setattr(metrics, "_current_evidence_status", {})` in each evidence test
- [x] No `routing_key` in evidence or diagnosis instrument labels

### Key Risks / Assumptions

1. **Delta accounting lifecycle:** Tests assume the simpler composite-key approach (`_current_evidence_status: dict[tuple[str,str,str], str]`) — if dev chooses the `_prev_evidence_status: dict[tuple[str,str,str,str], int]` approach, the no-op test (test 5) may need adjustment.
2. **State isolation:** Each evidence test resets `_current_evidence_status` via monkeypatch — critical for test order independence.
3. **Instrument type:** Tests verify `.add()` method presence — both counter and up-down-counter share this interface in OpenTelemetry.

### Completion Summary

- **Test file modified:** `tests/unit/health/test_metrics.py`
- **Checklist output:** `artifact/test-artifacts/atdd-checklist-1-3.md`
- **Red phase:** 15 new tests FAILING; 27 existing tests PASSING
- **Next step:** `bmad-dev-story` — implement story 1-3 to make tests green
