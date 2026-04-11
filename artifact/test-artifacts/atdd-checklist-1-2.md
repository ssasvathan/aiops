---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-11'
story_id: '1-2'
story_file: artifact/implementation-artifacts/1-2-findings-gating-otlp-instruments.md
detected_stack: backend
generation_mode: AI generation
tdd_phase: RED
inputDocuments:
  - artifact/implementation-artifacts/1-2-findings-gating-otlp-instruments.md
  - src/aiops_triage_pipeline/health/metrics.py
  - tests/unit/health/test_metrics.py
  - _bmad/tea/config.yaml
---

# ATDD Checklist — Story 1.2: Findings & Gating OTLP Instruments

## Step 1: Preflight & Context

| Item | Status |
|------|--------|
| Story approved with clear acceptance criteria | ✅ |
| Test framework configured (pytest + conftest.py) | ✅ |
| Development environment available | ✅ |
| Detected stack | backend |
| TEA execution mode | auto → sequential |

### Acceptance Criteria Extracted

| AC | Summary |
|----|---------|
| AC1 | `aiops.findings.total` counter with 5 labels, uppercase values, defined in `health/metrics.py` |
| AC2 | `aiops.gating.evaluations_total` counter with 3 labels (`gate_id`, `outcome`, `topic`), defined in `health/metrics.py` |
| AC3 | Both instruments use `create_counter`, emit within same cycle (NFR8), follow existing patterns (NFR14) |
| AC4 | Unit tests in `tests/unit/health/test_metrics.py` assert on metric name + label set |

---

## Step 2: Generation Mode

- **Mode:** AI Generation (backend stack — no browser recording needed)
- **Rationale:** All acceptance criteria are unit-testable against a Python module. No UI interaction.

---

## Step 3: Test Strategy

| AC | Test Scenario | Level | Priority | Red Phase Failure Reason |
|----|---------------|-------|----------|--------------------------|
| AC1, AC4 | `record_finding` emits correct metric name + all 5 labels | Unit | P0 | `AttributeError: module has no attribute '_findings_total'` |
| AC1, AC4 | `record_finding` emits uppercase label values | Unit | P0 | Same — function doesn't exist |
| AC1 | `record_finding` accepts all 4 Action enum values | Unit | P0 | Same |
| AC1, NFR8 | Multiple `record_finding` calls each emit independently | Unit | P1 | Same |
| AC2, AC4 | `record_gating_evaluation` emits correct metric name + 3 labels | Unit | P0 | `AttributeError: module has no attribute '_gating_evaluations_total'` |
| AC2 | `record_gating_evaluation` accepts pass/fail/skip outcomes | Unit | P0 | Same |
| AC2 | `record_gating_evaluation` does NOT include `routing_key` label | Unit | P1 | Same |
| AC2 | `record_gating_evaluation` emits `topic` for all gate IDs AG0–AG6 | Unit | P1 | Same |
| AC3 | `_findings_total` module attribute exists and has `.add()` | Unit | P0 | `hasattr(metrics, '_findings_total')` is False |
| AC3 | `_gating_evaluations_total` module attribute exists and has `.add()` | Unit | P0 | Same for gating |
| AC3 | `record_finding` is callable | Unit | P0 | `callable(None)` is False |
| AC3 | `record_gating_evaluation` is callable | Unit | P0 | Same |

---

## Step 4: Generated Tests (TDD Red Phase)

### Test File Modified

**`tests/unit/health/test_metrics.py`** — 12 new tests appended (Story 1.2 section)

### Tests Generated

| Test Name | AC | Priority |
|-----------|-----|----------|
| `test_record_finding_emits_expected_metric_name_and_labels` | AC1, AC4 | P0 |
| `test_record_finding_emits_uppercase_label_values` | AC1 | P0 |
| `test_record_finding_accepts_all_action_values` | AC1 | P0 |
| `test_record_finding_multiple_calls_each_emit_independently` | AC1, NFR8 | P1 |
| `test_record_gating_evaluation_emits_expected_metric_name_and_labels` | AC2, AC4 | P0 |
| `test_record_gating_evaluation_accepts_fail_and_skip_outcomes` | AC2 | P0 |
| `test_record_gating_evaluation_does_not_include_routing_key_label` | AC2 | P1 |
| `test_record_gating_evaluation_emits_topic_for_all_gate_ids` | AC2 | P1 |
| `test_findings_total_instrument_is_defined_in_metrics_module` | AC3 | P0 |
| `test_gating_evaluations_total_instrument_is_defined_in_metrics_module` | AC3 | P0 |
| `test_record_finding_function_is_callable` | AC3 | P0 |
| `test_record_gating_evaluation_function_is_callable` | AC3 | P0 |

### Red Phase Results

```
12 failed, 15 passed in 0.21s
```

All 12 new tests **FAIL** because `record_finding`, `record_gating_evaluation`,
`_findings_total`, and `_gating_evaluations_total` do not yet exist in
`src/aiops_triage_pipeline/health/metrics.py`.

All 15 pre-existing tests **PASS** (no regressions).

---

## Step 5: Validation

| Checklist Item | Status |
|----------------|--------|
| Prerequisites satisfied | ✅ |
| Test file created/modified correctly | ✅ |
| Tests assert on metric name + label set (not raw strings) | ✅ |
| Tests designed to fail before implementation | ✅ (all 12 fail) |
| No orphaned temp artifacts | ✅ |
| No regression in pre-existing tests | ✅ (15 passed) |
| Monkeypatching pattern matches existing `_RecordingInstrument` convention | ✅ |
| `routing_key` absent from gating labels | ✅ (asserted in test) |
| Uppercase label values asserted | ✅ |

### Key Risks / Assumptions

1. `record_gating_evaluation` outcome values assumed to be `"pass"` / `"fail"` / `"skip"` (lowercase). Dev must confirm exact strings from `_apply_gate_effect` in `gating.py` before implementing — if different, update test and implementation together.
2. `routing_key` for `record_finding` is not on `GateInputV1` directly — dev notes offer two wiring options (scheduler loop vs dispatch.py). Either is valid; tests are agnostic to wiring location.
3. `_findings_total` and `_gating_evaluations_total` must use `create_counter` (not `create_up_down_counter`) — enforced by the `.add()` callable check which both instrument types share, but the distinction matters for Prometheus semantics.

### Next Recommended Workflow

**Implementation:** Run `bmad-dev-story` on story 1-2 to implement:
1. Add `_findings_total` counter + `record_finding()` to `health/metrics.py`
2. Add `_gating_evaluations_total` counter + `record_gating_evaluation()` to `health/metrics.py`
3. Wire call sites in `scheduler.py` and/or `gating.py`

Then re-run `uv run python -m pytest tests/unit/health/test_metrics.py -v` — all 27 tests should pass (green phase).
