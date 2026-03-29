---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-03-22T17-19-39Z'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/1-6-complete-ag4-ag6-atomic-deduplication-and-decision-trail-output.md
  - pyproject.toml
  - tests/conftest.py
  - src/aiops_triage_pipeline/pipeline/stages/gating.py
  - src/aiops_triage_pipeline/cache/dedupe.py
  - src/aiops_triage_pipeline/contracts/action_decision.py
  - src/aiops_triage_pipeline/audit/replay.py
  - config/policies/rulebook-v1.yaml
  - tests/unit/pipeline/stages/test_gating.py
  - tests/unit/cache/test_dedupe.py
  - tests/unit/audit/test_decision_reproducibility.py
  - _bmad/tea/testarch/knowledge/data-factories.md
  - _bmad/tea/testarch/knowledge/component-tdd.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-healing-patterns.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-priorities-matrix.md
  - _bmad/tea/testarch/knowledge/ci-burn-in.md
  - _bmad/tea/testarch/knowledge/overview.md
  - _bmad/tea/testarch/knowledge/api-request.md
  - _bmad/tea/testarch/knowledge/auth-session.md
  - _bmad/tea/testarch/knowledge/recurse.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-overview.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-consumer-helpers.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-provider-verifier.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-request-filter.md
  - _bmad/tea/testarch/knowledge/pact-mcp.md
---

# ATDD Checklist - Epic 1, Story 6: Complete AG4-AG6, Atomic Deduplication, and Decision Trail Output

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** API/Integration (backend)

---

## Story Summary

Story 1.6 completes late-stage Stage 6 behavior by enforcing deterministic AG4-AG6 sequencing, a single authoritative atomic AG5 dedupe claim, and fully auditable decision-trail output. The RED-phase acceptance tests lock in atomic dedupe semantics so AG5 no longer uses a pre-read race window and the resulting `ActionDecisionV1` remains complete for downstream audit/replay.

**As a** on-call engineer
**I want** late-stage gating and decision outputs to be deterministic and auditable
**So that** every action has reproducible evidence and reason codes

---

## Acceptance Criteria

1. **Given** evidence, sustained state, and topology context are available
   **When** AG4 through AG6 execute
   **Then** sustained/confidence, atomic dedupe, and postmortem predicates are evaluated in sequence
   **And** AG5 uses single-step atomic set-if-not-exists with TTL as the authoritative dedupe check.

2. **Given** a gate evaluation completes
   **When** an action is finalized
   **Then** the pipeline outputs `ActionDecisionV1` with full reason codes and gate trail
   **And** unknown evidence semantics remain explicit end-to-end.

---

## Workflow Execution Log

### Step 1 - Preflight & Context

- Detected stack: `backend` (`pyproject.toml`, pytest `conftest.py`, no Playwright/Cypress manifests).
- Prerequisites: satisfied (story has explicit/testable ACs; backend test framework configured; development environment available).
- Existing pattern review: `tests/unit/pipeline/stages/test_gating.py`, `tests/unit/cache/test_dedupe.py`, `tests/unit/audit/test_decision_reproducibility.py`.
- Knowledge profile loaded: core + backend strategy fragments, Playwright utils API profile, Pact utility fragments per TEA config flags.

### Step 2 - Generation Mode

- Mode selected: `AI generation` (backend project; browser recording skipped).

### Step 3 - Test Strategy

- P0 scenarios:
  - AG5 must use a single atomic claim as dedupe source of truth (no read-then-write lookup).
  - Atomic claim returning `False` must suppress action as duplicate (`AG5_DUPLICATE_SUPPRESSED`).
- P1 scenario:
  - `ActionDecisionV1` keeps full AG0..AG6 gate trail and reason-code auditability when AG5 duplicate suppression fires.
- Primary level: backend ATDD acceptance tests in `tests/atdd/`.

### Step 4 - Generate + Aggregate

- Execution mode resolution:
  - Requested mode: `auto` (from config)
  - Capability probe: `true`
  - Resolved mode: `sequential`
- Worker A output: `/tmp/tea-atdd-api-tests-2026-03-22T17-19-39Z.json`
- Worker B output: `/tmp/tea-atdd-e2e-tests-2026-03-22T17-19-39Z.json` (0 tests; backend stack)
- Aggregation summary: `/tmp/tea-atdd-summary-2026-03-22T17-19-39Z.json`
- Persisted artifact copies:
  - `artifact/test-artifacts/tea-atdd-api-tests-2026-03-22T17-19-39Z.json`
  - `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-22T17-19-39Z.json`
  - `artifact/test-artifacts/tea-atdd-summary-2026-03-22T17-19-39Z.json`
- Files written:
  - `tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py`
  - `tests/atdd/fixtures/story_1_6_test_data.py`

### Step 5 - Validate & Complete

- RED-phase verification command: `uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -q`
- Result: `3 failed` as designed.
- Failure reason: AG5 still uses read-then-write dedupe lookup (`is_duplicate` then `remember`) instead of single authoritative atomic claim outcome.

---

## Failing Tests Created (RED Phase)

### API/Integration Tests (3 tests)

**File:** `tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py` (80 lines)

- ✅ **Test:** `test_p0_ag5_uses_single_atomic_claim_without_prelookup`
  - **Status:** RED - `is_duplicate` still invoked before atomic claim.
  - **Verifies:** AG5 no longer performs read-then-write dedupe lookup.
- ✅ **Test:** `test_p0_ag5_false_atomic_claim_suppresses_action_as_duplicate`
  - **Status:** RED - atomic claim `False` is currently ignored by gate logic.
  - **Verifies:** duplicate suppression is decided by one atomic NX claim outcome.
- ✅ **Test:** `test_p1_actiondecisionv1_retains_complete_gate_trail_on_atomic_duplicate`
  - **Status:** RED - AG5 duplicate suppression reason/action trail is not yet produced from atomic claim path.
  - **Verifies:** complete AG0..AG6 trail with duplicate suppression reason on `ActionDecisionV1`.

### E2E Tests (0 tests)

**File:** `N/A (backend stack)`

- Browser-based E2E generation intentionally skipped for this backend story.

### Component Tests (0 tests)

**File:** `N/A`

- Component/UI-level scope is not applicable to Story 1.6 acceptance surface.

---

## Data Factories Created

### Story 1.6 Gate Input Factory

**File:** `tests/atdd/fixtures/story_1_6_test_data.py`

**Exports:**

- `build_gate_input(...)` - deterministic `GateInputV1` factory for AG4-AG6/AG5 atomic dedupe acceptance tests.

---

## Fixtures Created

### Story 1.6 ATDD Support Fixture

**File:** `tests/atdd/fixtures/story_1_6_test_data.py` (52 lines)

**Fixtures/Helpers:**

- `build_gate_input` - deterministic backend payload setup for late-stage gate evaluation.
  - **Setup:** builds typed gate input with configurable env/tier/action/evidence/sustained/peak state.
  - **Provides:** stable inputs for AG5 atomic dedupe and decision-trail assertions.
  - **Cleanup:** not required (pure in-memory data).

---

## Mock Requirements

N/A for this red-phase slice. Tests are pure in-process gate-evaluation assertions.

---

## Required data-testid Attributes

N/A (backend-only story).

---

## Implementation Checklist

### Test: AG5 uses a single atomic claim without pre-lookup

**File:** `tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py`

**Tasks to make this test pass:**

- [ ] Update Stage 6 AG5 logic in `pipeline/stages/gating.py` to stop calling `is_duplicate` before `remember`.
- [ ] Use one atomic claim attempt (`remember`) as the authoritative dedupe decision.
- [ ] Preserve per-action TTL behavior by passing the capped current action into AG5 claim.
- [ ] Run test: `uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -k prelookup -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

### Test: AG5 atomic claim `False` suppresses duplicate actions

**File:** `tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py`

**Tasks to make this test pass:**

- [ ] Treat `remember(...)=False` as duplicate in AG5 and apply `on_duplicate` effect.
- [ ] Ensure duplicate path emits `AG5_DUPLICATE_SUPPRESSED` instead of store-error fallback.
- [ ] Keep degraded-mode fallback only for real dedupe store exceptions.
- [ ] Run test: `uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -k suppresses_action -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

### Test: ActionDecisionV1 trail completeness on AG5 duplicate suppression

**File:** `tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py`

**Tasks to make this test pass:**

- [ ] Ensure duplicate suppression path still yields full `gate_rule_ids` and reason-code trail on `ActionDecisionV1`.
- [ ] Keep AG6 postmortem fields deterministic after AG5 suppression outcome.
- [ ] Re-verify replay/audit downstream compatibility once AG5 semantics are updated.
- [ ] Run test: `uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -k gate_trail -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

---

## Running Tests

```bash
# Run all RED-phase ATDD tests for this story
uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -q

# Run specific test by keyword
uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -k suppresses_action -q

# Debug with full traceback
uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -vv

# Run with coverage (post-implementation)
uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py --cov=aiops_triage_pipeline.pipeline.stages.gating --cov-report=term-missing
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

- ✅ Story-specific acceptance tests created.
- ✅ Tests currently fail against baseline implementation.
- ✅ Failure signal is actionable and tied to AG5 atomic dedupe semantics.

### GREEN Phase (DEV Team - Next Steps)

1. Refactor AG5 in Stage 6 to use only atomic claim result as dedupe source of truth.
2. Map atomic-claim failure (`False`) to duplicate suppression effect and reason code.
3. Keep degraded-mode (`on_store_error`) behavior for Redis errors only.
4. Re-run Story 1.6 ATDD tests until all pass.

### REFACTOR Phase (After GREEN)

1. Remove/retire unused two-step dedupe interface surface if no longer needed.
2. Re-run unit + replay regression to confirm deterministic trail compatibility.
3. Verify no contract regressions in casefile/audit handoff.

---

## Next Steps

1. Implement Story 1.6 AG5 atomic dedupe behavior changes in gating path.
2. Re-run this ATDD file until green, then execute full regression gate (`0 skipped`).
3. Keep this checklist as the implementation handoff artifact for dev workflow.

---

## Knowledge Base References Applied

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

**Command:** `uv run pytest tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py -q`

**Results:**

```text
FFF                                                                      [100%]
3 failed in 0.60s
```

**Expected Failure Messages:**

- `AssertionError: AG5 should avoid read-then-write pre-lookup and use atomic claim path`
- `AssertionError: atomic claim False should suppress action as duplicate`

---

**Generated by BMad TEA Agent** - 2026-03-22
