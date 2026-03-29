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
  - artifact/implementation-artifacts/2-5-run-casefile-lifecycle-retention-purge.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/storage/lifecycle.py
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/health/metrics.py
  - tests/unit/storage/test_casefile_lifecycle.py
  - tests/integration/test_casefile_lifecycle.py
  - tests/unit/test_main.py
  - _bmad/tea/config.yaml
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/data-factories.md
---

# ATDD Checklist - Epic 2, Story 2.5: Run Casefile Lifecycle Retention Purge

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Backend acceptance/unit (pytest)
**TDD Phase:** RED

## Story Summary

Story 2.5 hardens casefile lifecycle retention behavior for compliant purge execution, case-scope
eligibility correctness, and explicit observability of purge success/failure outcomes.

**As a** platform operator  
**I want** expired casefiles purged by lifecycle policy  
**So that** storage retention remains compliant and bounded

## Acceptance Criteria

1. Given retention policy and object storage are configured, when lifecycle scans casefile objects,
   then expired artifacts are purged by policy and non-expired artifacts remain untouched.
2. Given purge execution completes, when metrics/logs are emitted, then purge counts/failures are
   observable and failures are surfaced for follow-up.

## Stack Detection / Mode

- `detected_stack`: backend
- `tea_execution_mode`: auto -> sequential (backend adaptation)
- Generation mode: AI generation (no browser recording)

## Test Strategy

- P0 red tests target lifecycle observability gaps around missing metric emission and missing failed
  object-key surfacing in lifecycle audit logs.
- P1 red test targets runtime startup observability gaps in lifecycle mode start logs.
- No browser E2E tests are produced for this backend-only story.

## Failing Tests Created (RED Phase)

### Backend Acceptance Tests (3)

**File:** `tests/atdd/test_story_2_5_casefile_lifecycle_retention_purge_red_phase.py`

- `test_p0_casefile_lifecycle_runner_emits_metrics_for_purge_outcomes`
  - **Status:** RED
  - **Failure:** runner emits lifecycle audit log but no lifecycle purge outcome metric hook is invoked.
- `test_p0_casefile_lifecycle_audit_logs_include_failed_object_keys_for_followup`
  - **Status:** RED
  - **Failure:** partial failure audit log lacks required `failed_keys` field.
- `test_p1_casefile_lifecycle_mode_start_log_exposes_governance_and_policy_path`
  - **Status:** RED
  - **Failure:** startup lifecycle mode log omits governance approval ref and retention policy path.

## Fixtures Created

- `tests/atdd/fixtures/story_2_5_test_data.py`
  - `InMemoryLifecycleObjectStore`
  - `RecordingLogger`
  - `build_retention_policy()`

## Mock Requirements

- Lifecycle storage behavior is simulated using deterministic in-memory object store fixture.
- Runtime mode startup test uses monkeypatched bootstrap/runner dependencies (no external services).

## Implementation Checklist

### Test: `test_p0_casefile_lifecycle_runner_emits_metrics_for_purge_outcomes`

- [ ] Add lifecycle purge outcome metric API in `health/metrics.py`.
- [ ] Call the metric API from `CasefileLifecycleRunner.run_once()` with scanned/eligible/purged/failed counts.

### Test: `test_p0_casefile_lifecycle_audit_logs_include_failed_object_keys_for_followup`

- [ ] Extend lifecycle audit log payload to include failed object keys (or equivalent deterministic failure detail).
- [ ] Ensure partial delete failures remain visible for operational triage.

### Test: `test_p1_casefile_lifecycle_mode_start_log_exposes_governance_and_policy_path`

- [ ] Extend `casefile_lifecycle_mode_started` log payload with governance approval reference.
- [ ] Include resolved lifecycle retention policy path/version metadata in startup log fields.

## Running Tests

```bash
uv run pytest -q tests/atdd/test_story_2_5_casefile_lifecycle_retention_purge_red_phase.py
```

## Test Execution Evidence

**Command:** `uv run pytest -q tests/atdd/test_story_2_5_casefile_lifecycle_retention_purge_red_phase.py`

**Result:**

```text
FFF
3 failed in 0.78s
```

**Failure indicators:**

- lifecycle metric call list remained empty
- lifecycle audit payload missing `failed_keys`
- lifecycle startup log missing `governance_approval_ref`

## Generated Artifacts

- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-22T21-08-58Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-22T21-08-58Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-22T21-08-58Z.json`
- `artifact/test-artifacts/atdd-checklist-2-5-run-casefile-lifecycle-retention-purge.md`

## Validation Notes

- Story ACs are explicit and testable.
- Backend pytest framework and existing lifecycle coverage are present.
- No browser sessions were created; no browser cleanup required.
- Temp ATDD artifacts were stored under `artifact/test-artifacts/`.

## Completion Summary

ATDD red phase is complete for Story 2.5 with 3 deterministic failing acceptance tests that pin the
remaining lifecycle observability/governance logging gaps before implementation.
