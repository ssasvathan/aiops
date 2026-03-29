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
  - artifact/implementation-artifacts/4-1-add-distributed-cycle-lock-with-fail-open-behavior.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/config/settings.py
  - src/aiops_triage_pipeline/health/metrics.py
  - src/aiops_triage_pipeline/pipeline/scheduler.py
  - tests/unit/test_main.py
  - tests/unit/pipeline/test_scheduler.py
  - tests/unit/health/test_metrics.py
  - tests/unit/config/test_settings.py
  - tests/atdd/test_story_4_1_add_distributed_cycle_lock_with_fail_open_behavior_red_phase.py
  - tests/atdd/fixtures/story_4_1_test_data.py
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

# ATDD Checklist - Epic 4, Story 4.1: Add Distributed Cycle Lock with Fail-Open Behavior

**Date:** 2026-03-23
**Author:** Sas
**Primary Test Level:** Backend acceptance/unit (pytest)
**TDD Phase:** RED

## Story Summary

Story 4.1 introduces optional distributed interval ownership for hot-path scheduler cycles so only one
pod executes each interval when lock coordination is enabled.

**As an** SRE/platform engineer  
**I want** Redis-backed cycle lock coordination with explicit fail-open semantics  
**So that** multi-replica deployments prevent duplicate interval execution without halting during Redis failures

## Acceptance Criteria

1. Given `DISTRIBUTED_CYCLE_LOCK_ENABLED=true`, when a cycle starts across multiple pods, lock acquisition uses Redis `SET NX EX` with configured TTL margin and non-holders yield until next scheduler tick.
2. Given Redis is unavailable during lock attempt, when ownership cannot be resolved, hot-path fails open and still executes while degraded health/metrics are emitted.

## Stack Detection / Mode

- `detected_stack`: backend (Python service using pytest)
- `tea_execution_mode`: auto -> sequential (single-agent backend adaptation)
- Generation mode: AI generation (no browser recording)

## Test Strategy

- P0 tests pin required configuration surface (feature flag + lock margin), coordination protocol outcomes, and Redis lock semantics (`SET NX EX`, yield, fail-open).
- P0 tests pin fail-open requirement under Redis unavailability with explicit reason context.
- P1 tests pin observability/integration surfaces (metrics counters and scheduler feature-flag branch presence).
- Backend-only scope: no browser E2E tests.

## Failing Tests Created (RED Phase)

### Backend Acceptance Tests (7)

**File:** `tests/atdd/test_story_4_1_add_distributed_cycle_lock_with_fail_open_behavior_red_phase.py`

- `test_p0_settings_expose_distributed_cycle_lock_defaults_and_validation`
  - **Status:** RED
  - **Failure:** `Settings` lacks `DISTRIBUTED_CYCLE_LOCK_ENABLED` and `CYCLE_LOCK_MARGIN_SECONDS` fields.
- `test_p0_coordination_protocol_exposes_acquired_yielded_fail_open_statuses`
  - **Status:** RED
  - **Failure:** `aiops_triage_pipeline.coordination.protocol` module missing.
- `test_p0_cycle_lock_uses_set_nx_ex_with_interval_plus_margin_for_first_owner`
  - **Status:** RED
  - **Failure:** `aiops_triage_pipeline.coordination.cycle_lock` module missing.
- `test_p0_cycle_lock_returns_yielded_when_lock_is_held_by_another_pod`
  - **Status:** RED
  - **Failure:** lock implementation module missing; contention/yield path unavailable.
- `test_p0_cycle_lock_returns_fail_open_when_redis_is_unavailable`
  - **Status:** RED
  - **Failure:** lock implementation module missing; fail-open path unavailable.
- `test_p1_metrics_surface_exposes_cycle_lock_counters_for_observability`
  - **Status:** RED
  - **Failure:** health metrics lacks `record_cycle_lock_acquired`, `record_cycle_lock_yielded`, `record_cycle_lock_fail_open`.
- `test_p1_hot_path_scheduler_source_contains_feature_flag_and_fail_open_branching`
  - **Status:** RED
  - **Failure:** hot-path scheduler source lacks distributed lock feature-flag and yield/fail-open branch markers.

## Fixtures Created

- `tests/atdd/fixtures/story_4_1_test_data.py`
  - `RecordingRedisLockClient(...)`
  - `build_settings_kwargs(...)`
  - `to_status_value(...)`
  - `extract_holder(...)`
  - `load_module_or_fail(...)`

## Mock Requirements

- Redis lock semantics are modeled with `RecordingRedisLockClient` and include:
  - successful `SET NX EX` acquisition,
  - contention (`set_result=False`) with holder lookup,
  - failure (`raise_on_set=ConnectionError`) fail-open scenario.
- Scheduler lock integration assertion is source-level in red phase; later green phase should replace with runtime integration behavior checks once lock wiring exists.

## Implementation Checklist

### Test: `test_p0_settings_expose_distributed_cycle_lock_defaults_and_validation`

- [ ] Add `DISTRIBUTED_CYCLE_LOCK_ENABLED` to `Settings` with default `False`.
- [ ] Add `CYCLE_LOCK_MARGIN_SECONDS` to `Settings` with positive default (60).
- [ ] Add validation rejecting non-positive margin values.

### Test: `test_p0_coordination_protocol_exposes_acquired_yielded_fail_open_statuses`

- [ ] Add `src/aiops_triage_pipeline/coordination/protocol.py`.
- [ ] Define structured lock outcome/status model supporting `acquired`, `yielded`, `fail_open`.
- [ ] Export protocol symbols via `coordination/__init__.py`.

### Test: `test_p0_cycle_lock_uses_set_nx_ex_with_interval_plus_margin_for_first_owner`

- [ ] Add `src/aiops_triage_pipeline/coordination/cycle_lock.py` with Redis lock implementation.
- [ ] Use key `aiops:lock:cycle` and Redis `set(..., nx=True, ex=interval+margin)`.
- [ ] Return acquired outcome with TTL context.

### Test: `test_p0_cycle_lock_returns_yielded_when_lock_is_held_by_another_pod`

- [ ] Map Redis contention (`SET NX` false) to yielded outcome.
- [ ] Include holder context where available for logs/metrics.

### Test: `test_p0_cycle_lock_returns_fail_open_when_redis_is_unavailable`

- [ ] Catch Redis acquisition exceptions and return fail-open outcome.
- [ ] Include failure reason context for observability.

### Test: `test_p1_metrics_surface_exposes_cycle_lock_counters_for_observability`

- [ ] Add lock counters in `health/metrics.py` for acquired/yielded/fail-open outcomes.
- [ ] Ensure scheduler/coordination path emits these counters.

### Test: `test_p1_hot_path_scheduler_source_contains_feature_flag_and_fail_open_branching`

- [ ] Wire feature-flagged lock decision path into `_hot_path_scheduler_loop`.
- [ ] On yielded: skip stage execution for interval.
- [ ] On fail-open: continue cycle execution and emit degraded health/metrics/logging.
- [ ] Preserve exact existing behavior when lock feature flag is disabled.

## Running Tests

```bash
uv run pytest -q tests/atdd/test_story_4_1_add_distributed_cycle_lock_with_fail_open_behavior_red_phase.py
```

## Test Execution Evidence

**Command:** `uv run pytest -q tests/atdd/test_story_4_1_add_distributed_cycle_lock_with_fail_open_behavior_red_phase.py`

**Result:**

```text
FFFFFFF
7 failed in 0.73s
```

## Generated Artifacts

- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-23T12-07-14Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-23T12-07-14Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-23T12-07-14Z.json`
- `artifact/test-artifacts/atdd-checklist-4-1-add-distributed-cycle-lock-with-fail-open-behavior.md`

## Validation Notes

- Story acceptance criteria are explicit and testable for distributed lock ownership and fail-open resilience.
- Backend scope confirmed; no browser session artifacts were created.
- RED phase validated: all 7 tests fail against missing Story 4.1 implementation surfaces.
- Temp subagent outputs persisted in `/tmp` and copied into `artifact/test-artifacts/`.

## Completion Summary

ATDD RED phase for Story 4.1 is complete with 7 deterministic failing backend acceptance tests
covering settings, protocol/module surfaces, lock semantics, fail-open handling, and observability wiring.

Sprint status updated: `4-1-add-distributed-cycle-lock-with-fail-open-behavior: in-progress`
