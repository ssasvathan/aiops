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
  - /home/sas/workspace/aiops/artifact/implementation-artifacts/1-2-enrich-gate-inputs-and-enforce-ag4-confidence-sustained-rules.md
  - /home/sas/workspace/aiops/artifact/implementation-artifacts/sprint-status.yaml
  - /home/sas/workspace/aiops/pyproject.toml
  - /home/sas/workspace/aiops/tests/conftest.py
  - /home/sas/workspace/aiops/src/aiops_triage_pipeline/pipeline/stages/gating.py
  - /home/sas/workspace/aiops/src/aiops_triage_pipeline/pipeline/scheduler.py
  - /home/sas/workspace/aiops/tests/unit/pipeline/stages/test_gating.py
  - /home/sas/workspace/aiops/tests/unit/pipeline/test_scheduler.py
  - /tmp/tea-atdd-story-1-2-knowledge-loaded.md
---

# ATDD Checklist - Epic 1, Story 1.2: Enrich Gate Inputs and Enforce AG4 Confidence/Sustained Rules

**Date:** 2026-03-29
**Author:** Sas
**Primary Test Level:** Backend API/Integration acceptance tests (pytest)

---

## Story Summary

Story 1.2 requires gate-input context enrichment to happen before `collect_gate_inputs_by_scope` so AG4 evaluates deterministic candidate actions with precomputed `diagnosis_confidence` and `proposed_action`. AG4 behavior must preserve confidence floor and sustained checks while keeping environment/tier caps as final authority. This story must preserve deterministic reason-code ordering when both AG4 checks fail.

**As a** Platform SRE  
**I want** AG4 to evaluate both confidence and sustained conditions with clear capping behavior  
**So that** escalations only occur for strong, sustained signals

---

## Acceptance Criteria

1. Given scoring outputs are produced for a scope, when gate inputs are assembled, then `GateInputContext` is enriched with both `diagnosis_confidence` and `proposed_action`, and enrichment occurs before `collect_gate_inputs_by_scope`.
2. Given AG4 evaluates a scope with `diagnosis_confidence < 0.6`, when candidate action is `TICKET` or `PAGE`, then AG4 caps the action to `OBSERVE`, independent of other positive gate signals.
3. Given AG4 evaluates a scope with `diagnosis_confidence >= 0.6` and `is_sustained=True`, when environment caps permit the candidate action, then AG4 allows `TICKET`/`PAGE` progression, and PAGE outside `PROD+TIER_0` remains blocked by existing cap authority.
4. Given AG4 evaluates a scope with `diagnosis_confidence >= 0.6` and `is_sustained=False`, when candidate action is `TICKET` or `PAGE`, then AG4 suppresses escalation to `OBSERVE`, and suppression reasoning is captured as sustained-condition failure.

---

## Failing Tests Created (RED Phase)

### E2E Tests (0 tests)

**File:** `N/A (backend stack detected)`

- Backend-only stack (`pyproject.toml` + pytest suite; no browser UI flow in story scope).
- No browser E2E tests generated for this story.

### API Tests (4 tests)

**File:** `tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py` (151 lines)

- ✅ **Test:** `test_p0_scheduler_enriches_gate_input_context_before_collect`
  - **Status:** RED - scheduler passes default `0.0/OBSERVE` context to `collect_gate_inputs_by_scope` (no pre-collection enrichment yet).
  - **Verifies:** AC1 pre-collection enrichment order and presence.
- ✅ **Test:** `test_p0_ag4_caps_low_confidence_ticket_or_page_candidates_to_observe`
  - **Status:** RED - expected enriched confidence `0.59`, observed `1.0` because collection recomputes score/action instead of consuming enriched context.
  - **Verifies:** AC2 low-confidence cap behavior must apply to enriched candidate action.
- ✅ **Test:** `test_p0_ag4_allows_boundary_confidence_when_sustained_and_caps_still_apply`
  - **Status:** RED - expected enriched confidence boundary `0.60`, observed `1.0` from in-collector recomputation.
  - **Verifies:** AC3 boundary confidence progression and AG1 env-cap authority.
- ✅ **Test:** `test_p1_ag4_suppresses_not_sustained_even_when_confidence_meets_floor`
  - **Status:** RED - expected enriched confidence `0.60`, observed `1.0` from in-collector recomputation.
  - **Verifies:** AC4 sustained failure suppression semantics with enriched confidence input.

### Component Tests (0 tests)

**File:** `N/A (backend story; no UI components)`

- No component tests required for this story scope.

---

## Data Factories Created

### Story 1.2 Test Data Factory

**File:** `tests/atdd/fixtures/story_1_2_test_data.py`

**Exports:**

- `build_story_1_2_context(...)` - Builds deterministic `GateInputContext` seeds with explicit confidence/action.
- `build_story_1_2_stage_inputs(...)` - Builds evidence+peak outputs with controlled sustained and peak-window state.

**Example Usage:**

```python
from aiops_triage_pipeline.contracts.enums import Action
from tests.atdd.fixtures.story_1_2_test_data import (
    build_story_1_2_context,
    build_story_1_2_stage_inputs,
)

evidence_output, peak_output, scope = build_story_1_2_stage_inputs(
    sustained_value=False,
    is_peak_window=True,
)
context = {
    scope: build_story_1_2_context(
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.60,
    )
}
```

---

## Fixtures Created

### Story 1.2 Stage Fixture Helpers

**File:** `tests/atdd/fixtures/story_1_2_test_data.py`

**Fixtures:**

- `build_story_1_2_stage_inputs` - deterministic evidence+peak stage-output construction
  - **Setup:** Builds normalized evidence rows, peak classification context, and sustained status permutations.
  - **Provides:** `EvidenceStageOutput`, `PeakStageOutput`, and scope tuple.
  - **Cleanup:** Not required (in-memory only).

---

## Mock Requirements

### External Service Mocking

**Endpoint:** `N/A`

**Success Response:**

```json
{
  "note": "No external API mocks required for Story 1.2 ATDD red phase"
}
```

**Failure Response:**

```json
{
  "note": "Red phase targets missing scheduler/context enrichment behavior in local stage logic"
}
```

**Notes:** Tests are local scheduler/gating acceptance checks with no network dependencies.

---

## Required data-testid Attributes

### Backend Story Scope

- `N/A` - Story 1.2 has no UI/data-testid requirements.

---

## Implementation Checklist

### Test: `test_p0_scheduler_enriches_gate_input_context_before_collect`

**File:** `tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py`

**Tasks to make this test pass:**

- [ ] Add explicit pre-collection enrichment step in scheduler/gating path that computes confidence/action per scope before collect.
- [ ] Ensure enriched `GateInputContext` (not default `0.0/OBSERVE`) is passed into `collect_gate_inputs_by_scope`.
- [ ] Keep enrichment deterministic and local to stage/scheduler code paths.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py::test_p0_scheduler_enriches_gate_input_context_before_collect -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.5 hours

---

### Test: `test_p0_ag4_caps_low_confidence_ticket_or_page_candidates_to_observe`

**File:** `tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py`

**Tasks to make this test pass:**

- [ ] Wire `collect_gate_inputs_by_scope` to consume enriched context values for `diagnosis_confidence` and `proposed_action`.
- [ ] Preserve fail-safe fallback semantics (`0.0/OBSERVE`) for missing/invalid enrichment paths.
- [ ] Confirm AG4 confidence floor (`0.6`) applies to enriched candidate action.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py::test_p0_ag4_caps_low_confidence_ticket_or_page_candidates_to_observe -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

---

### Test: `test_p0_ag4_allows_boundary_confidence_when_sustained_and_caps_still_apply`

**File:** `tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py`

**Tasks to make this test pass:**

- [ ] Preserve boundary behavior for `diagnosis_confidence == 0.60` with `sustained=True`.
- [ ] Keep AG1 env/tier caps as final authority (e.g., DEV still caps PAGE to NOTIFY).
- [ ] Maintain deterministic rule ordering and reason-code semantics.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py::test_p0_ag4_allows_boundary_confidence_when_sustained_and_caps_still_apply -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

---

### Test: `test_p1_ag4_suppresses_not_sustained_even_when_confidence_meets_floor`

**File:** `tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py`

**Tasks to make this test pass:**

- [ ] Ensure enriched `diagnosis_confidence` is preserved at collect stage for not-sustained scenarios.
- [ ] Enforce AG4 sustained check (`equals true`) with `NOT_SUSTAINED` reason code on failure.
- [ ] Keep deterministic reason ordering when AG4 checks fail together.
- [ ] Run test: `uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py::test_p1_ag4_suppresses_not_sustained_even_when_confidence_meets_floor -rs`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

---

## Running Tests

```bash
# Run all failing tests for this story
uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py -rs

# Run specific test file
uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py -rs

# Run tests in headed mode (see browser)
N/A (backend-only story)

# Debug specific test
uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py::test_p0_scheduler_enriches_gate_input_context_before_collect -rs -vv

# Run tests with coverage
uv run pytest --cov=src/aiops_triage_pipeline/pipeline/stages/gating.py --cov=src/aiops_triage_pipeline/pipeline/scheduler.py -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py -rs
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

**TEA Agent Responsibilities:**

- ✅ Acceptance tests authored for AC1/AC2/AC3/AC4
- ✅ Story-scoped test-data fixture module created
- ✅ Implementation checklist mapped from failing tests
- ✅ Red-phase execution evidence captured

**Verification:**

- Test command executed and all 4 tests failed as expected
- Failures are tied to missing pre-collection enrichment and collect-stage context consumption behavior
- No skipped tests used (repository quality gate requires zero skipped)

---

### GREEN Phase (DEV Team - Next Steps)

**DEV Agent Responsibilities:**

1. Add deterministic context enrichment before `collect_gate_inputs_by_scope`.
2. Consume enriched confidence/action in collect path without breaking fallback or cap-down logic.
3. Re-run Story 1.2 ATDD tests until green.
4. Keep AG4 rule semantics and reason-code ordering stable.
5. Keep env/tier caps as final authority.

**Key Principles:**

- One failing test at a time
- Minimal code for each green step
- Deterministic, side-effect-free hot-path behavior
- No contract/schema changes

---

### REFACTOR Phase (DEV Team - After All Tests Pass)

**DEV Agent Responsibilities:**

1. Remove duplication between scheduler enrichment and gating helpers if introduced.
2. Confirm guardrail logging and metadata consistency.
3. Run targeted and full regression gates with zero skipped tests.
4. Keep architecture boundaries intact (`scheduler.py` + `gating.py` only).

---

## Next Steps

1. Share this checklist and red-phase tests with implementation workflow.
2. Implement Story 1.2 enrichment before collect in scheduler/gating path.
3. Re-run Story 1.2 ATDD tests until all four tests pass.
4. Run full regression with Docker-backed command and confirm `0 skipped`.

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
- `api-testing-patterns.md`
- `pactjs-utils-overview.md`
- `pactjs-utils-consumer-helpers.md`
- `pactjs-utils-provider-verifier.md`
- `pactjs-utils-request-filter.md`
- `pact-mcp.md`

---

## Test Execution Evidence

### Initial Test Run (RED Phase Verification)

**Command:** `uv run pytest -q tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py -rs`

**Results:**

```text
FFFF                                                                     [100%]
4 failed in 0.66s

Key failure anchors:
- scheduler passed default GateInputContext values (0.0/OBSERVE) to collect_gate_inputs_by_scope
- expected enriched diagnosis_confidence 0.59, observed 1.0
- expected enriched diagnosis_confidence 0.60, observed 1.0 (sustained=True path)
- expected enriched diagnosis_confidence 0.60, observed 1.0 (sustained=False path)
```

**Summary:**

- Total tests: 4
- Passing: 0 (expected)
- Failing: 4 (expected)
- Status: ✅ RED phase verified

**Expected Failure Messages:**

- `AssertionError: Story 1.2 RED phase: expected scheduler to enrich diagnosis_confidence before collect_gate_inputs_by_scope.`
- `assert 1.0 == 0.59 ± 5.9e-07`
- `assert 1.0 == 0.6 ± 6.0e-07` (AC3)
- `assert 1.0 == 0.6 ± 6.0e-07` (AC4)

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
