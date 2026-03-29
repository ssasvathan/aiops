---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-03-29'
workflowType: 'testarch-atdd'
inputDocuments:
  - /home/sas/workspace/aiops/artifact/implementation-artifacts/1-1-implement-deterministic-confidence-scoring-core.md
  - /home/sas/workspace/aiops/artifact/implementation-artifacts/sprint-status.yaml
  - /home/sas/workspace/aiops/pyproject.toml
  - /home/sas/workspace/aiops/tests/conftest.py
  - /home/sas/workspace/aiops/src/aiops_triage_pipeline/pipeline/stages/gating.py
  - /tmp/tea-atdd-story-1-1-knowledge-loaded.md
---

# ATDD Checklist - Epic 1, Story 1.1: Implement Deterministic Confidence Scoring Core

**Date:** 2026-03-29
**Author:** Sas
**Primary Test Level:** Backend API/Integration acceptance tests (pytest)

---

## Story Summary

Story 1.1 requires deterministic scoring of gate inputs in Stage 6 so `diagnosis_confidence` and candidate `proposed_action` are derived from evidence statuses, sustained state, and peak context. The scoring path must preserve deterministic behavior for identical inputs, including `is_sustained=None` semantics. Any internal scoring exception must fail-safe to `0.0/OBSERVE` and continue processing.

**As a** Platform SRE
**I want** confidence scores to be computed deterministically from evidence, sustained, and peak inputs
**So that** gate decisions are explainable and repeatable

---

## Acceptance Criteria

1. Given evidence status counts and sustained/peak context are available for a scope, when the scoring function executes in the gating stage, then it computes `diagnosis_confidence` in the `0.0..1.0` range using tiered logic and derives a candidate `proposed_action` from the same inputs.
2. Given `is_sustained=None` is present from degraded coordination context, when tier amplifiers are evaluated, then sustained amplification is not applied and behavior remains deterministic for identical inputs.
3. Given the scoring function raises an internal exception, when gating continues, then output falls back to `diagnosis_confidence=0.0` and `proposed_action=OBSERVE` and processing continues without unhandled exception.

---

## Failing Tests Created (RED Phase)

### E2E Tests (0 tests)

**File:** `N/A (backend stack detected)`

- Backend-only stack (`pyproject.toml` present, no frontend manifest/config found).
- No browser E2E tests generated for this story.

### API Tests (4 tests)

**File:** `tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py` (149 lines)

- ✅ **Test:** `test_p0_collect_gate_inputs_computes_deterministic_score_and_action_from_stage_inputs`
  - **Status:** RED - `diagnosis_confidence` remains `0.0` and no derived action/metadata exists.
  - **Verifies:** AC1 deterministic score/action derivation and score metadata population.
- ✅ **Test:** `test_p0_action_band_thresholds_map_exactly_to_story_contract`
  - **Status:** RED - expected private `_derive_*action*` helper is absent.
  - **Verifies:** AC1 score band mapping (`0.59 -> OBSERVE`, `0.60 -> TICKET`, `0.85 -> PAGE`).
- ✅ **Test:** `test_p1_sustained_none_applies_zero_boost_and_output_is_repeatable`
  - **Status:** RED - expected `_score_*sustained*` helper and sustained boost metadata are absent.
  - **Verifies:** AC2 no sustained boost for `None` and deterministic repeatability.
- ✅ **Test:** `test_p0_scoring_internal_exception_falls_back_to_observe_without_unhandled_raise`
  - **Status:** RED - expected `_score_*base*` helper fallback seam is absent.
  - **Verifies:** AC3 deterministic fallback to `0.0/OBSERVE` on internal scoring errors.

### Component Tests (0 tests)

**File:** `N/A (backend story; no UI components)`

- No component tests required for this story scope.

---

## Data Factories Created

### Story 1.1 Test Data Factory

**File:** `tests/atdd/fixtures/story_1_1_test_data.py`

**Exports:**

- `build_story_1_1_context(...)` - Builds deterministic `GateInputContext` seeds.
- `build_story_1_1_stage_inputs(...)` - Builds evidence + peak stage outputs for sustained/peak permutations.

**Example Usage:**

```python
from tests.atdd.fixtures.story_1_1_test_data import (
    build_story_1_1_context,
    build_story_1_1_stage_inputs,
)

evidence_output, peak_output, scope = build_story_1_1_stage_inputs(
    sustained_value=None,
    is_peak_window=True,
)
context = {scope: build_story_1_1_context()}
```

---

## Fixtures Created

### Story 1.1 Stage Fixture Helpers

**File:** `tests/atdd/fixtures/story_1_1_test_data.py`

**Fixtures:**

- `build_story_1_1_stage_inputs` - deterministic stage-output construction
  - **Setup:** Builds normalized evidence rows + peak output state for topic scope.
  - **Provides:** `EvidenceStageOutput`, `PeakStageOutput`, and scope tuple.
  - **Cleanup:** Not required (in-memory only).

---

## Mock Requirements

### External Service Mocking

**Endpoint:** `N/A`

**Success Response:**

```json
{
  "note": "No external API mocks required for Story 1.1 ATDD red phase"
}
```

**Failure Response:**

```json
{
  "note": "Scoring-failure path is exercised via monkeypatching scoring helpers"
}
```

**Notes:** Tests are local stage-level acceptance tests and do not call network services.

---

## Required data-testid Attributes

### Backend Story Scope

- `N/A` - Story 1.1 has no UI/data-testid requirements.

---

## Implementation Checklist

### Test: `test_p0_collect_gate_inputs_computes_deterministic_score_and_action_from_stage_inputs`

**File:** `tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py`

**Tasks to make this test pass:**

- [ ] Add `SCORE_V1_*` constants in `src/aiops_triage_pipeline/pipeline/stages/gating.py`.
- [ ] Implement deterministic score derivation from evidence status counts + sustained + peak.
- [ ] Populate `diagnosis_confidence`, derived candidate `proposed_action`, and `decision_basis` metadata keys.
- [ ] Ensure score is clamped to `[0.0, 1.0]`.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py::test_p0_collect_gate_inputs_computes_deterministic_score_and_action_from_stage_inputs -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 2.0 hours

---

### Test: `test_p0_action_band_thresholds_map_exactly_to_story_contract`

**File:** `tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py`

**Tasks to make this test pass:**

- [ ] Add `_derive_*action*` private helper with deterministic band mapping.
- [ ] Enforce exact boundaries: `<0.6 OBSERVE`, `0.6-<0.85 TICKET`, `>=0.85 PAGE`.
- [ ] Keep helper pure and side-effect free.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py::test_p0_action_band_thresholds_map_exactly_to_story_contract -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

---

### Test: `test_p1_sustained_none_applies_zero_boost_and_output_is_repeatable`

**File:** `tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py`

**Tasks to make this test pass:**

- [ ] Add `_score_*sustained*` helper that applies boost only when sustained is `True`.
- [ ] Preserve tri-state sustained semantics for scoring (`True | False | None`) before boolean cast.
- [ ] Ensure `decision_basis["sustained_boost"] == 0.0` when sustained input is unknown.
- [ ] Confirm deterministic output equality for identical inputs.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py::test_p1_sustained_none_applies_zero_boost_and_output_is_repeatable -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.5 hours

---

### Test: `test_p0_scoring_internal_exception_falls_back_to_observe_without_unhandled_raise`

**File:** `tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py`

**Tasks to make this test pass:**

- [ ] Wrap scoring path in deterministic exception handling in `collect_gate_inputs_by_scope`.
- [ ] On scoring exception, set `diagnosis_confidence=0.0` and `proposed_action=OBSERVE`.
- [ ] Emit warning log with `event_type="gating.scoring.fallback_applied"`.
- [ ] Set `decision_basis["fallback_applied"] = true` with stable score metadata keys.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py::test_p0_scoring_internal_exception_falls_back_to_observe_without_unhandled_raise -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.5 hours

---

## Running Tests

```bash
# Run all failing tests for this story
uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py -rs

# Run specific test file
uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py -rs

# Run tests in headed mode (see browser)
N/A (backend-only story)

# Debug specific test
uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py::test_p0_collect_gate_inputs_computes_deterministic_score_and_action_from_stage_inputs -rs -vv

# Run tests with coverage
uv run pytest --cov=src/aiops_triage_pipeline/pipeline/stages/gating.py -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py -rs
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

**TEA Agent Responsibilities:**

- ✅ Acceptance tests authored for AC1/AC2/AC3
- ✅ Story-scoped test-data fixture module created
- ✅ Implementation checklist mapped from failing tests
- ✅ Red-phase execution evidence captured

**Verification:**

- Test command executed and all 4 tests failed as expected
- Failures are tied to missing scoring implementation and helper seams
- No skipped tests used (repository enforces no-skip quality gate)

---

### GREEN Phase (DEV Team - Next Steps)

**DEV Agent Responsibilities:**

1. Implement deterministic scoring core in `gating.py` using story guardrails.
2. Add required private scoring/action helpers and metadata keys.
3. Re-run story ATDD tests until green.
4. Extend unit/scheduler tests to cover wiring and fallback behavior.
5. Keep `max_safe_action` cap chain and rulebook authority unchanged.

**Key Principles:**

- One failing test at a time
- Minimal code for each green step
- Deterministic, side-effect-free scoring path
- No hot-path dependency additions

---

### REFACTOR Phase (DEV Team - After All Tests Pass)

**DEV Agent Responsibilities:**

1. Consolidate duplicated scoring logic if any.
2. Confirm metadata/log naming consistency.
3. Re-run targeted and full regression gates (zero skipped tests).
4. Keep architecture boundaries intact (`gating.py` local scope only).

---

## Next Steps

1. Share this checklist + red-phase test files with implementation workflow.
2. Implement Story 1.1 deterministic scoring in `src/aiops_triage_pipeline/pipeline/stages/gating.py`.
3. Remove red-phase failure causes by completing AC1/AC2/AC3 behavior.
4. Re-run red-phase ATDD tests until all pass.
5. Run full suite with Docker-backed command and confirm `0 skipped`.

---

## Knowledge Base References Applied

This ATDD workflow used the following fragments for backend-mode strategy and quality constraints:

- `data-factories.md`
- `component-tdd.md`
- `test-quality.md`
- `test-healing-patterns.md`
- `test-levels-framework.md`
- `test-priorities-matrix.md`
- `ci-burn-in.md`
- `overview.md`
- `api-request.md`
- `auth-session.md`
- `recurse.md`
- `pactjs-utils-overview.md`
- `pactjs-utils-consumer-helpers.md`
- `pactjs-utils-provider-verifier.md`
- `pactjs-utils-request-filter.md`
- `pact-mcp.md`

---

## Test Execution Evidence

### Initial Test Run (RED Phase Verification)

**Command:** `uv run pytest -q tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py -rs`

**Results:**

```text
FFFF                                                                     [100%]
4 failed in 0.62s

Key failure anchors:
- diagnosis_confidence stayed 0.0 in collect_gate_inputs_by_scope
- expected _derive_*action* helper missing
- expected _score_*sustained* helper missing
- expected _score_*base* helper missing
```

**Summary:**

- Total tests: 4
- Passing: 0 (expected)
- Failing: 4 (expected)
- Status: ✅ RED phase verified

**Expected Failure Messages:**

- `AssertionError: assert 0.0 < 0.0`
- `Failed: expected private helper with prefix='_derive_' and name containing 'action'`
- `Failed: expected private helper with prefix='_score_' and name containing 'sustained'`
- `Failed: expected a private '_score_*base*' helper in gating`

---

## Notes

- Backend stack was detected in preflight; browser E2E artifacts were intentionally omitted.
- Generic ATDD `test.skip()` guidance was adapted to repository no-skip policy by using intentional failing assertions.
- Step 4 temp outputs were saved to both `/tmp` and `artifact/test-artifacts/tmp/` for traceability.

---

## Contact

**Questions or Issues?**

- Ask in team standup
- Refer to `./bmm/docs/tea-README.md` for workflow documentation
- Consult `./bmm/testarch/knowledge` for testing best practices

---

**Generated by BMad TEA Agent** - 2026-03-29
