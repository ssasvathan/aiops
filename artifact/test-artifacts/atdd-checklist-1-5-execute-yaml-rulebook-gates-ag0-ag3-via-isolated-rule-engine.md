---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-03-22T16-17-20Z'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/1-5-execute-yaml-rulebook-gates-ag0-ag3-via-isolated-rule-engine.md
  - pyproject.toml
  - tests/conftest.py
  - src/aiops_triage_pipeline/pipeline/stages/gating.py
  - src/aiops_triage_pipeline/contracts/rulebook.py
  - config/policies/rulebook-v1.yaml
  - tests/unit/pipeline/stages/test_gating.py
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

# ATDD Checklist - Epic 1, Story 5: Execute YAML Rulebook Gates AG0-AG3 via Isolated Rule Engine

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** API/Integration (backend)

---

## Story Summary

Story 1.5 isolates AG0-AG3 rule evaluation into a dedicated `rule_engine/` package driven by YAML-defined checks and a frozen handler registry. The RED-phase acceptance tests lock in startup fail-fast behavior for unknown check types, deterministic AG0..AG3 execution order, and AG1 safety invariants (monotonic caps + no `PAGE` outside `PROD + TIER_0`).

**As a** platform operator  
**I want** early-stage deterministic gating to run from YAML-defined checks in an isolated engine  
**So that** safety-critical action reduction behavior is testable and policy-driven

---

## Acceptance Criteria

1. **Given** rulebook gate definitions are loaded at startup  
   **When** gate evaluation starts  
   **Then** AG0 through AG3 are evaluated sequentially through the handler registry  
   **And** check type dispatch fails fast at startup if any configured type has no handler.

2. **Given** environment and tier caps apply  
   **When** AG1 evaluates the current action  
   **Then** action severity can only remain equal or be capped downward per environment policy  
   **And** post-condition safety assertions enforce that `PAGE` is impossible outside `PROD + TIER_0`.

---

## Workflow Execution Log

### Step 1 - Preflight & Context

- Detected stack: `backend` (`pyproject.toml`, pytest `conftest.py`, no Playwright/Cypress manifests).
- Prerequisites: satisfied (story has explicit/testable ACs; backend framework config exists; dev environment available).
- Existing pattern review: `tests/unit/pipeline/stages/test_gating.py` and Stage 6 gate evaluator behavior in `pipeline/stages/gating.py`.
- Knowledge profile loaded: core fragments + backend strategy fragments + Playwright utils API-only profile + Pact utility fragments (per TEA config flags).

### Step 2 - Generation Mode

- Mode selected: `AI generation` (backend project; browser recording not required).

### Step 3 - Test Strategy

- P0 scenarios:
  - Public isolated `rule_engine` API exists and is callable.
  - Unknown `check.type` in AG0 triggers startup fail-fast validation.
  - AG0..AG3 sequence executes deterministically through isolated engine path.
- P1 scenario:
  - AG1 cap remains monotonic with `uat`/`stage` compatibility and prevents `PAGE` outside `PROD + TIER_0`.
- Primary level: backend API/integration acceptance tests (`tests/atdd/`).

### Step 4 - Generate + Aggregate

- Execution mode resolution:
  - Requested mode: `auto` (from config)
  - Capability probe: `true`
  - Resolved mode: `sequential`
- Worker A output: `/tmp/tea-atdd-api-tests-2026-03-22T16-16-28Z.json`
- Worker B output: `/tmp/tea-atdd-e2e-tests-2026-03-22T16-16-28Z.json` (0 tests; backend stack)
- Aggregation summary: `/tmp/tea-atdd-summary-2026-03-22T16-16-28Z.json`
- Files written:
  - `tests/atdd/story_1_5_rule_engine_red_phase.py`
  - `tests/atdd/fixtures/story_1_5_test_data.py`

### Step 5 - Validate & Complete

- RED-phase verification command: `uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -q`
- Result: `4 failed` as designed (feature not implemented yet).
- Failure reason: isolated package `aiops_triage_pipeline.rule_engine` does not exist yet.

---

## Failing Tests Created (RED Phase)

### API/Integration Tests (4 tests)

**File:** `tests/atdd/story_1_5_rule_engine_red_phase.py` (94 lines)

- ✅ **Test:** `test_p0_rule_engine_public_api_is_exposed`
  - **Status:** RED - import fails (`No module named aiops_triage_pipeline.rule_engine`)
  - **Verifies:** isolated rule engine package exposes public evaluation entrypoint.
- ✅ **Test:** `test_p0_startup_validation_fails_fast_for_unknown_check_type`
  - **Status:** RED - startup validation API unavailable because isolated module is missing.
  - **Verifies:** unknown YAML `check.type` fails at startup, not at runtime.
- ✅ **Test:** `test_p0_ag0_ag3_are_evaluated_sequentially_in_isolated_engine`
  - **Status:** RED - isolated evaluation API unavailable.
  - **Verifies:** deterministic AG0..AG3 execution order in isolated engine path.
- ✅ **Test:** `test_p1_ag1_never_escalates_with_stage_alias_fallback_and_safety_invariant`
  - **Status:** RED - isolated evaluation API unavailable.
  - **Verifies:** monotonic AG1 cap with `stage` alias fallback and `PAGE` prohibition outside `PROD + TIER_0`.

### E2E Tests (0 tests)

**File:** `N/A (backend stack)`

- Browser-based E2E generation intentionally skipped for this backend story.

### Component Tests (0 tests)

**File:** `N/A`

- Component/UI-level scope is not applicable to Story 1.5 acceptance surface.

---

## Data Factories Created

### Story 1.5 Gate Input Factory

**File:** `tests/atdd/fixtures/story_1_5_test_data.py`

**Exports:**

- `build_gate_input(...)` - deterministic `GateInputV1` payload builder for AG0-AG3 tests.
- `build_rulebook_with_unknown_ag0_check_type(...)` - mutates AG0 checks with unknown handler type.
- `build_stage_alias_only_rulebook(...)` - drops canonical `uat` cap and preserves legacy `stage` alias.

---

## Fixtures Created

### Story 1.5 ATDD Support Fixture

**File:** `tests/atdd/fixtures/story_1_5_test_data.py` (91 lines)

**Fixtures/Helpers:**

- `build_gate_input` - deterministic test payload setup for backend gate evaluation.
  - **Setup:** builds typed `GateInputV1` with configurable env/tier/action.
  - **Provides:** stable inputs for isolated rule engine acceptance tests.
  - **Cleanup:** not required (in-memory objects only).

---

## Mock Requirements

N/A for this red-phase slice. Tests are pure in-process contract/engine assertions and do not require external service mocking.

---

## Required data-testid Attributes

N/A (backend-only story).

---

## Implementation Checklist

### Test: Isolated rule engine public API exists

**File:** `tests/atdd/story_1_5_rule_engine_red_phase.py`

**Tasks to make this test pass:**

- [ ] Create `src/aiops_triage_pipeline/rule_engine/__init__.py` with public `evaluate_gates` export.
- [ ] Ensure API signature supports `gate_input` + `rulebook` deterministic execution.
- [ ] Wire imports so package resolves from top-level runtime path.
- [ ] Run test: `uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -k public_api -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.0 hours

### Test: Startup handler validation fails fast for unknown check type

**File:** `tests/atdd/story_1_5_rule_engine_red_phase.py`

**Tasks to make this test pass:**

- [ ] Add frozen check-handler registry for AG0-AG3 in `rule_engine/handlers.py`.
- [ ] Implement startup validator (`validate_rulebook_handlers`) and typed startup error.
- [ ] Validate all configured `check.type` values from YAML before runtime evaluation starts.
- [ ] Run test: `uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -k unknown_check_type -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.5 hours

### Test: AG0..AG3 run sequentially through isolated engine

**File:** `tests/atdd/story_1_5_rule_engine_red_phase.py`

**Tasks to make this test pass:**

- [ ] Implement isolated AG0-AG3 evaluation loop in `rule_engine/engine.py`.
- [ ] Preserve deterministic gate order and reason-code ordering guarantees.
- [ ] Return decision payload exposing AG0..AG3 gate sequence used during evaluation.
- [ ] Run test: `uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -k ag0_ag3 -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 2.0 hours

### Test: AG1 monotonic cap + `stage` alias compatibility safety invariant

**File:** `tests/atdd/story_1_5_rule_engine_red_phase.py`

**Tasks to make this test pass:**

- [ ] Implement AG1 cap semantics with monotonic reduction guarantees.
- [ ] Keep `uat`/`stage` alias fallback behavior backward-compatible.
- [ ] Enforce post-condition invariant: `PAGE` impossible outside `PROD + TIER_0`.
- [ ] Run test: `uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -k stage_alias -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.5 hours

---

## Running Tests

```bash
# Run all RED-phase ATDD tests for this story
uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -q

# Run specific test by keyword
uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -k ag0_ag3 -q

# Debug with full traceback
uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -vv

# Run with coverage (post-implementation)
uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py --cov=aiops_triage_pipeline.rule_engine --cov-report=term-missing
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

- ✅ Story-specific acceptance tests created.
- ✅ Tests currently fail against baseline implementation.
- ✅ Failure signal is actionable (missing isolated `rule_engine` implementation path).

### GREEN Phase (DEV Team - Next Steps)

1. Implement isolated `rule_engine/` package and public API.
2. Add startup check-type registry validation with typed failure behavior.
3. Route AG0-AG3 execution through isolated engine from Stage 6.
4. Re-run story ATDD tests until all pass.

### REFACTOR Phase (After GREEN)

1. Consolidate duplicated AG0-AG3 logic between legacy and new paths.
2. Keep AG4-AG6 behavior unchanged and deterministic.
3. Re-run Stage 6 regression suite to confirm no contract regressions.

---

## Next Steps

1. Implement Story 1.5 code path to satisfy these RED tests.
2. Remove/adjust RED assumptions only when behavior is implemented and verified green.
3. Re-run full regression gate with zero skipped tests once implementation lands.

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

**Command:** `uv run pytest tests/atdd/story_1_5_rule_engine_red_phase.py -q`

**Results:**

```text
FFFF                                                                     [100%]
4 failed in 0.59s
```

**Expected Failure Messages:**

- `Story 1.5 RED phase: isolated package aiops_triage_pipeline.rule_engine does not exist yet.`

---

**Generated by BMad TEA Agent** - 2026-03-22
