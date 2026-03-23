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
  - artifact/implementation-artifacts/3-1-implement-cold-path-kafka-consumer-runtime-mode.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/config/settings.py
  - src/aiops_triage_pipeline/health/registry.py
  - tests/unit/test_main.py
  - tests/unit/integrations/test_kafka.py
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

# ATDD Checklist - Epic 3, Story 3.1: Implement Cold-Path Kafka Consumer Runtime Mode

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Backend acceptance/unit (pytest)
**TDD Phase:** RED

## Story Summary

Story 3.1 activates the `cold-path` runtime from bootstrap stub to live Kafka consumer mode. It
must bind to the canonical consumer group/topic, process events sequentially through a testable
adapter boundary, and shut down with commit/close plus health transitions.

**As an** SRE/platform engineer  
**I want** a dedicated cold-path consumer mode for case header events  
**So that** diagnosis processing is decoupled from hot-path execution

## Acceptance Criteria

1. Given runtime mode is set to `cold-path`, when service starts, then it joins consumer group
   `aiops-cold-path-diagnosis` and subscribes to `aiops-case-header`, and processes messages
   sequentially through a testable consumer adapter abstraction.
2. Given shutdown is requested, when consumer exits, then offsets are committed gracefully before
   close, and health status reflects connected/lag/poll state transitions.

## Stack Detection / Mode

- `detected_stack`: backend (`pyproject.toml` + pytest tree, no frontend browser framework)
- `tea_execution_mode`: auto -> sequential (backend adaptation)
- Generation mode: AI generation only (no browser recording)

## Test Strategy

- P0 tests assert the cold-path runtime contract is no longer a stub and surfaces canonical
  consumer binding in startup behavior.
- P0/P1 tests pin new configuration/adapter boundaries needed for Story 3.1 implementation.
- P1 tests pin health transition semantics for connected/poll/commit lifecycle signals.
- No browser E2E tests are produced for this backend-only story.

## Failing Tests Created (RED Phase)

### Backend Acceptance Tests (4)

**File:** `tests/atdd/test_story_3_1_implement_cold_path_kafka_consumer_runtime_mode_red_phase.py`

- `test_p0_settings_expose_cold_path_consumer_defaults_and_validation`
  - **Status:** RED
  - **Failure:** cold-path consumer settings/validation fields are not yet defined.
- `test_p0_cold_path_runtime_logs_consumer_group_and_topic_on_start`
  - **Status:** RED
  - **Failure:** `_run_cold_path()` still exits as bootstrap stub and does not emit startup
    consumer binding.
- `test_p1_cold_path_runtime_reports_connected_poll_and_commit_health_transitions`
  - **Status:** RED
  - **Failure:** cold-path runtime does not publish connected/poll/commit health transitions.
- `test_p1_kafka_consumer_adapter_module_exposes_protocol_and_confluent_adapter`
  - **Status:** RED
  - **Failure:** `integrations/kafka_consumer.py` adapter boundary module is missing.

## Fixtures Created

- `tests/atdd/fixtures/story_3_1_test_data.py`
  - `RecordingAsyncHealthRegistry`
  - `build_cold_path_settings()`
  - `expected_consumer_binding()`

## Mock Requirements

- Runtime bootstrap is monkeypatched to deterministic in-memory settings/logger objects.
- Health updates are captured via async in-memory registry probe fixture.
- No Docker/Kafka runtime needed for this RED-phase ATDD gate (integration verification is
  deferred to implementation and integration steps).

## Implementation Checklist

### Test: `test_p0_settings_expose_cold_path_consumer_defaults_and_validation`

- [ ] Add `KAFKA_COLD_PATH_CONSUMER_GROUP` setting with default
      `aiops-cold-path-diagnosis`.
- [ ] Add `KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS` setting with `>0` validation.
- [ ] Include these fields in startup config logging (secret-safe).

### Test: `test_p0_cold_path_runtime_logs_consumer_group_and_topic_on_start`

- [ ] Replace `_run_cold_path()` bootstrap stub with real consumer lifecycle wiring.
- [ ] Emit startup log containing mode, consumer group, topic, and poll timeout.
- [ ] Ensure runtime uses sequential consume/process/commit path.

### Test: `test_p1_cold_path_runtime_reports_connected_poll_and_commit_health_transitions`

- [ ] Update health registry with connected/disconnected transition states.
- [ ] Add poll lifecycle transition signal(s) for cold-path consumer.
- [ ] Add commit success/failure transition signal(s) during shutdown path.

### Test: `test_p1_kafka_consumer_adapter_module_exposes_protocol_and_confluent_adapter`

- [ ] Add `src/aiops_triage_pipeline/integrations/kafka_consumer.py`.
- [ ] Define thin adapter protocol with `subscribe`, `poll`, `commit`, `close`.
- [ ] Provide confluent-kafka-backed adapter implementation with required consumer config
      validation.

## Running Tests

```bash
uv run pytest -q tests/atdd/test_story_3_1_implement_cold_path_kafka_consumer_runtime_mode_red_phase.py
```

## Test Execution Evidence

**Command:** `uv run pytest -q tests/atdd/test_story_3_1_implement_cold_path_kafka_consumer_runtime_mode_red_phase.py`

**Result:**

```text
FFFF
4 failed in 0.65s
```

**Failure indicators:**

- `Settings` missing `KAFKA_COLD_PATH_CONSUMER_GROUP`
- no `cold_path_mode_started` startup log emitted
- no connected/poll/commit health transitions recorded
- missing `aiops_triage_pipeline.integrations.kafka_consumer` module

## Generated Artifacts

- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-22T22-28-03Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-22T22-28-03Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-22T22-28-03Z.json`
- `artifact/test-artifacts/atdd-checklist-3-1-implement-cold-path-kafka-consumer-runtime-mode.md`

## Validation Notes

- Story ACs are explicit and testable.
- Backend pytest framework and ATDD folder conventions are present.
- No browser CLI/MCP sessions were used; cleanup not required.
- Temp ATDD artifacts were stored under `artifact/test-artifacts/`.

## Completion Summary

ATDD red phase is complete for Story 3.1 with 4 deterministic failing backend acceptance tests
that pin cold-path consumer runtime activation, adapter boundary creation, configuration
validation, and shutdown/health lifecycle requirements.
