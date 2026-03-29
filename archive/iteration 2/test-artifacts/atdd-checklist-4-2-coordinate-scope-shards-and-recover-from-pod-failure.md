---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-03-23'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/4-2-coordinate-scope-shards-and-recover-from-pod-failure.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/config/settings.py
  - src/aiops_triage_pipeline/health/metrics.py
  - src/aiops_triage_pipeline/cache/findings_cache.py
  - src/aiops_triage_pipeline/coordination/protocol.py
  - src/aiops_triage_pipeline/coordination/cycle_lock.py
  - tests/unit/cache/test_findings_cache.py
  - tests/unit/pipeline/test_scheduler.py
  - tests/integration/coordination/test_cycle_lock_contention.py
  - tests/atdd/test_story_4_2_coordinate_scope_shards_and_recover_from_pod_failure_red_phase.py
  - tests/atdd/fixtures/story_4_2_test_data.py
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

# ATDD Checklist - Epic 4, Story 4.2: Coordinate Scope Shards and Recover from Pod Failure

**Date:** 2026-03-23
**Author:** Sas
**Primary Test Level:** Backend acceptance/unit (pytest)
**TDD Phase:** RED

## Story Summary

Story 4.2 introduces shard-level coordination and lease recovery for findings execution so hot-path
work can scale across pods while preserving automatic recovery after pod failure.

**As a** platform operator  
**I want** scope shard assignment and lease recovery for findings work  
**So that** distributed execution scales and remains resilient to pod loss

## Acceptance Criteria

1. Given multiple hot-path pods are active, when shard coordination is enabled, scope workloads are assigned per shard and checkpointed per interval with batch-oriented writes.
2. Given a pod holding shard responsibility fails, when lease expiry elapses, another pod resumes shard processing without manual intervention.

## Stack Detection / Mode

- `detected_stack`: backend (Python service using pytest)
- `tea_execution_mode`: auto -> sequential (single-agent backend adaptation)
- Generation mode: AI generation (no browser recording)

## Test Strategy

- P0 tests pin settings/config surfaces, shard module primitives, deterministic assignment behavior, lease-expiry handoff semantics, and checkpoint API surfaces.
- P1 tests pin observability and scheduler wiring markers for shard gating + degraded full-scope fallback.
- Backend-only scope: no browser E2E tests.

## Failing Tests Created (RED Phase)

### Backend Acceptance Tests (7)

**File:** `tests/atdd/test_story_4_2_coordinate_scope_shards_and_recover_from_pod_failure_red_phase.py`

- `test_p0_settings_expose_shard_coordination_flags_and_ttls`
  - **Status:** RED
  - **Failure:** `Settings` lacks shard coordination feature flags/count/TTL fields.
- `test_p0_shard_module_exposes_key_builders_assignment_and_lease_primitives`
  - **Status:** RED
  - **Failure:** `aiops_triage_pipeline.coordination.shard_registry` module missing.
- `test_p0_assignment_is_deterministic_for_stable_scope_and_membership_inputs`
  - **Status:** RED
  - **Failure:** deterministic assignment function unavailable because shard module is missing.
- `test_p0_lease_expiry_allows_safe_handoff_to_recovery_pod`
  - **Status:** RED
  - **Failure:** lease acquisition/recovery primitives unavailable because shard module is missing.
- `test_p0_findings_cache_exposes_per_shard_checkpoint_write_surface`
  - **Status:** RED
  - **Failure:** findings cache lacks shard checkpoint key/write functions.
- `test_p1_metrics_surface_exposes_shard_checkpoint_and_recovery_counters`
  - **Status:** RED
  - **Failure:** metrics module lacks shard checkpoint/recovery instrumentation functions.
- `test_p1_hot_path_scheduler_source_contains_shard_gating_and_fallback_markers`
  - **Status:** RED
  - **Failure:** scheduler loop source lacks shard feature-flag and full-scope fallback markers.

## Fixtures Created

- `tests/atdd/fixtures/story_4_2_test_data.py`
  - `RecordingRedisShardClient(...)`
  - `build_settings_kwargs(...)`
  - `load_module_or_fail(...)`

## Mock Requirements

- In-memory Redis probe models `SET NX EX` semantics with TTL expiry (`RecordingRedisShardClient`) for lease-contention/recovery probing.
- Shard module import helper provides actionable RED-phase failure messages until shard coordination surface is implemented.
- Scheduler assertions are source-level markers in RED phase and should be upgraded to behavior-level tests in GREEN phase.

## Implementation Checklist

### Test: `test_p0_settings_expose_shard_coordination_flags_and_ttls`

- [ ] Add `SHARD_REGISTRY_ENABLED` to `Settings` with default `False`.
- [ ] Add `SHARD_COORDINATION_SHARD_COUNT` to `Settings` with positive default.
- [ ] Add `SHARD_LEASE_TTL_SECONDS` and `SHARD_CHECKPOINT_TTL_SECONDS` with positive defaults and validators.

### Test: `test_p0_shard_module_exposes_key_builders_assignment_and_lease_primitives`

- [ ] Create `src/aiops_triage_pipeline/coordination/shard_registry.py`.
- [ ] Add key builders for shard lease/checkpoint namespaces using `aiops:shard:...` naming.
- [ ] Expose coordinator class + assignment function from coordination package.

### Test: `test_p0_assignment_is_deterministic_for_stable_scope_and_membership_inputs`

- [ ] Implement deterministic scope-to-shard assignment from active pod membership.
- [ ] Ensure stable outputs for identical input sets and predictable pod ownership.

### Test: `test_p0_lease_expiry_allows_safe_handoff_to_recovery_pod`

- [ ] Implement shard lease acquire semantics on Redis (`SET NX EX`).
- [ ] Add lease expiry/recovery handoff so a second pod can resume shard ownership automatically.

### Test: `test_p0_findings_cache_exposes_per_shard_checkpoint_write_surface`

- [ ] Add shard checkpoint key builder in findings cache helpers.
- [ ] Add per-shard per-interval checkpoint write function (batch-oriented semantics).

### Test: `test_p1_metrics_surface_exposes_shard_checkpoint_and_recovery_counters`

- [ ] Add metrics functions for shard assignment/checkpoint/recovery outcomes in `health/metrics.py`.
- [ ] Wire calls from shard coordination path into these counters.

### Test: `test_p1_hot_path_scheduler_source_contains_shard_gating_and_fallback_markers`

- [ ] Wire `SHARD_REGISTRY_ENABLED` guard into hot-path scheduler loop.
- [ ] Add full-scope fallback branch for shard-coordination Redis failures.
- [ ] Ensure shard checkpoint flow is visible in scheduler implementation.

## Running Tests

```bash
uv run pytest -q tests/atdd/test_story_4_2_coordinate_scope_shards_and_recover_from_pod_failure_red_phase.py
```

## Test Execution Evidence

**Command:** `uv run pytest -q tests/atdd/test_story_4_2_coordinate_scope_shards_and_recover_from_pod_failure_red_phase.py`

**Result:**

```text
FFFFFFF
7 failed in 0.80s
```

## Generated Artifacts

- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-23T12-51-32Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-23T12-51-32Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-23T12-51-32Z.json`
- `artifact/test-artifacts/atdd-checklist-4-2-coordinate-scope-shards-and-recover-from-pod-failure.md`

## Validation Notes

- Story acceptance criteria are explicit and testable for shard assignment/checkpoint and lease recovery behavior.
- Backend scope confirmed; no browser sessions required.
- RED phase validated: all 7 tests fail due to missing Story 4.2 surfaces, not flaky runtime behavior.
- Temp worker outputs were generated in `/tmp` and persisted into `artifact/test-artifacts/`.

## Completion Summary

ATDD RED phase for Story 4.2 is complete with 7 deterministic failing backend acceptance tests
covering settings, shard coordination primitives, deterministic assignment, lease expiry recovery,
checkpoint write surfaces, observability hooks, and scheduler shard fallback integration markers.

Sprint status updated: `4-2-coordinate-scope-shards-and-recover-from-pod-failure: in-progress`
