---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-03-22'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/3-4-persist-diagnosis-artifact-with-fallback-guarantees.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/diagnosis/graph.py
  - src/aiops_triage_pipeline/diagnosis/fallback.py
  - src/aiops_triage_pipeline/contracts/diagnosis_report.py
  - tests/unit/diagnosis/test_graph.py
  - tests/atdd/fixtures/story_3_4_test_data.py
  - tests/atdd/test_story_3_4_persist_diagnosis_artifact_with_fallback_guarantees_red_phase.py
  - _bmad/tea/config.yaml
  - _bmad/tea/testarch/tea-index.csv
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

# ATDD Checklist - Epic 3, Story 3.4: Persist Diagnosis Artifact with Fallback Guarantees

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Backend acceptance/unit (pytest)
**TDD Phase:** RED

## Story Summary

Story 3.4 hardens diagnosis artifact persistence so success and fallback outcomes always produce
an auditable `diagnosis.json` state with explicit observability semantics.

**As an** SRE/platform engineer  
**I want** diagnosis persistence to stay deterministic across LLM/provider failure classes  
**So that** every case produces an observable and hash-chain-linked diagnosis artifact outcome

## Acceptance Criteria

1. Given LLM invocation succeeds, when diagnosis write executes, then `diagnosis.json` is stored
   with hash-chain linkage to `triage.json` and success telemetry/logging includes case
   correlation context.
2. Given LLM invocation times out, fails, or returns invalid schema, when fallback executes,
   then deterministic fallback diagnosis is generated/persisted and absence of primary diagnosis
   is explicit + observable.

## Stack Detection / Mode

- `detected_stack`: backend (Python service using pytest)
- `tea_execution_mode`: auto -> sequential (single-agent backend adaptation)
- Generation mode: AI generation (no browser recording)

## Test Strategy

- P0 tests pin success-path observability for hash-chain correlation context in persistence logs.
- P0 tests pin timeout, transport-unavailable, and schema-invalid fallback classes to explicit
  primary-diagnosis-absence semantics in persisted fallback reports.
- P1 test pins fallback persistence observability marker requirements at log event level.
- Backend-only scope: no browser E2E tests.

## Failing Tests Created (RED Phase)

### Backend Acceptance Tests (5)

**File:** `tests/atdd/test_story_3_4_persist_diagnosis_artifact_with_fallback_guarantees_red_phase.py`

- `test_p0_success_persistence_log_includes_diagnosis_hash_for_case_correlation`
  - **Status:** RED
  - **Failure:** success persistence log omits `diagnosis_hash` correlation field.
- `test_p0_timeout_fallback_marks_primary_diagnosis_absence_explicitly`
  - **Status:** RED
  - **Failure:** timeout fallback report does not include stable `PRIMARY_DIAGNOSIS_ABSENT` marker in `gaps`.
- `test_p0_transport_failure_fallback_marks_primary_diagnosis_absence_explicitly`
  - **Status:** RED
  - **Failure:** transport-unavailable fallback report does not include stable `PRIMARY_DIAGNOSIS_ABSENT` marker in `gaps`.
- `test_p0_schema_invalid_fallback_marks_primary_diagnosis_absence_explicitly`
  - **Status:** RED
  - **Failure:** schema-invalid fallback uses non-standard gap text and lacks stable `PRIMARY_DIAGNOSIS_ABSENT` marker.
- `test_p1_fallback_persistence_log_has_primary_absence_observability_flag`
  - **Status:** RED
  - **Failure:** fallback persistence log omits `primary_diagnosis_absent=true` observability flag.

## Fixtures Created

- `tests/atdd/fixtures/story_3_4_test_data.py`
  - `build_triage_excerpt(...)`
  - `build_empty_denylist()`
  - `build_health_registry()`
  - `build_object_store_client()`

## Mock Requirements

- `asyncio.wait_for` is patched to force timeout/transport/schema-invalid invocation branches.
- Diagnosis graph logger is patched for deterministic observability-field assertions.
- Object storage is mocked with write-once `put_if_absent=CREATED` semantics.

## Implementation Checklist

### Test: `test_p0_success_persistence_log_includes_diagnosis_hash_for_case_correlation`

- [ ] Include `diagnosis_hash` in `cold_path_diagnosis_json_written` success log payload.
- [ ] Keep existing case correlation keys (`case_id`, `triage_hash`) intact.

### Test: `test_p0_timeout_fallback_marks_primary_diagnosis_absence_explicitly`

- [ ] Add stable explicit primary-absence marker (for example `PRIMARY_DIAGNOSIS_ABSENT`) to timeout fallback `gaps`.
- [ ] Preserve reason code mapping `LLM_TIMEOUT`.

### Test: `test_p0_transport_failure_fallback_marks_primary_diagnosis_absence_explicitly`

- [ ] Add the same stable primary-absence marker for transport-unavailable fallback.
- [ ] Preserve reason code mapping `LLM_UNAVAILABLE`.

### Test: `test_p0_schema_invalid_fallback_marks_primary_diagnosis_absence_explicitly`

- [ ] Normalize schema-invalid fallback gap semantics to include stable primary-absence marker.
- [ ] Preserve reason code mapping `LLM_SCHEMA_INVALID`.

### Test: `test_p1_fallback_persistence_log_has_primary_absence_observability_flag`

- [ ] Add `primary_diagnosis_absent=true` to `cold_path_fallback_diagnosis_json_written` log payload.
- [ ] Keep current fallback event name and `reason_codes` payload.

## Running Tests

```bash
uv run pytest -q tests/atdd/test_story_3_4_persist_diagnosis_artifact_with_fallback_guarantees_red_phase.py
```

## Test Execution Evidence

**Command:** `uv run pytest -q tests/atdd/test_story_3_4_persist_diagnosis_artifact_with_fallback_guarantees_red_phase.py`

**Result:**

```text
FFFFF
5 failed in 0.49s
```

## Generated Artifacts

- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-23T03-22-27Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-23T03-22-27Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-23T03-22-27Z.json`
- `artifact/test-artifacts/atdd-checklist-3-4-persist-diagnosis-artifact-with-fallback-guarantees.md`

## Validation Notes

- Story acceptance criteria are explicit and testable for success + fallback persistence outcomes.
- Backend scope confirmed; no browser session artifacts were created.
- RED phase validated: tests fail for missing implementation/hardening behavior, not import or setup errors.
- All generated temp summaries stored in `artifact/test-artifacts/`.

## Completion Summary

ATDD RED phase for Story 3.4 is complete with 5 deterministic failing backend acceptance tests
covering hash-correlation log enrichment and explicit fallback primary-diagnosis-absence observability.

Sprint status updated: `3-4-persist-diagnosis-artifact-with-fallback-guarantees: in-progress`
