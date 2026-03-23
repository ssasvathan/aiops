# Story 3.1: Implement Cold-Path Kafka Consumer Runtime Mode

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/platform engineer,
I want a dedicated cold-path consumer mode for case header events,
so that diagnosis processing is decoupled from hot-path execution.

**Implements:** FR36

## Acceptance Criteria

1. **Given** runtime mode is set to `cold-path`
   **When** the service starts
   **Then** it joins consumer group `aiops-cold-path-diagnosis` and subscribes to `aiops-case-header`
   **And** processes messages sequentially through a testable consumer adapter abstraction.

2. **Given** shutdown is requested
   **When** the consumer exits
   **Then** offsets are committed gracefully before close
   **And** health status reflects connected/lag/poll state transitions.

## Tasks / Subtasks

- [x] Task 1: Add cold-path Kafka consumer adapter boundary (AC: 1, 2)
  - [x] Add `src/aiops_triage_pipeline/integrations/kafka_consumer.py` with a thin protocol: `subscribe`, `poll`, `commit`, `close`.
  - [x] Implement `confluent-kafka`-backed adapter using `Settings`; require and validate `group.id` and topic wiring.
  - [x] Decode/validate consumed payloads as `CaseHeaderEventV1`; malformed messages are structured-log + continue.

- [x] Task 2: Replace cold-path runtime stub with sequential consume loop (AC: 1, 2)
  - [x] Update `src/aiops_triage_pipeline/__main__.py` `_run_cold_path()` to run a real poll-process-commit loop.
  - [x] Keep processing strictly sequential (no batching/concurrency in this story).
  - [x] Add a small processor boundary for Story 3.2 to plug in reconstruction/summary without refactor.
  - [x] Ensure shutdown path commits offsets and closes consumer.

- [x] Task 3: Add cold-path health state transitions (AC: 2)
  - [x] Update `HealthRegistry` entries for connected/disconnected, poll state, and commit success/failure.
  - [x] Preserve existing `/health` shape (component map); add cold-path component fields only.

- [x] Task 4: Extend configuration for consumer runtime mode (AC: 1, 2)
  - [x] Add settings for cold-path consumer group and poll timeout with safe defaults.
  - [x] Add settings validation (`>0` constraints and non-empty strings where required).
  - [x] Update runtime startup config log output (secret-safe).
  - [x] Update `config/.env.local`, `config/.env.dev`, `config/.env.docker`, `config/.env.uat.template`, `config/.env.prod.template`.

- [x] Task 5: Add unit and integration coverage (AC: 1, 2)
  - [x] Add `tests/unit/integrations/test_kafka_consumer.py` for adapter behavior, poll handling, commit/close paths.
  - [x] Update `tests/unit/test_main.py` to assert `cold-path` no longer exits as bootstrap stub.
  - [x] Add `tests/integration/cold_path/test_consumer_lifecycle.py` for real Kafka lifecycle: subscribe, sequential consume, graceful close.
  - [x] Keep sprint quality gate at zero skips.

- [x] Task 6: Update runtime-mode documentation (AC: 1, 2)
  - [x] Update `docs/runtime-modes.md` cold-path section from stub to live consumer runtime mode.
  - [x] Update `docs/local-development.md` runtime mode status and local run guidance.
  - [x] Update `README.md` runtime mode table for cold-path activation.

## Dev Notes

### Developer Context Section

- Story scope is runtime mode activation for cold-path Kafka consumption (CR-07 / D6), not full diagnosis pipeline redesign.
- Current implementation still logs a cold-path bootstrap warning and exits in `__main__.py`; this story removes that stub behavior.
- Strict scope boundary for this story:
  - Do not implement Story 3.2 context reconstruction/evidence summary construction details.
  - Do not implement Story 3.3 prompt enrichment/schema-validation workflow details.
  - Do not implement Story 3.4 diagnosis fallback persistence deltas.
- Preserve hot/cold separation invariant: no hot-path waits, imports, or shared mutable state with cold-path runtime.

### Technical Requirements

- Functional requirement: FR36.
- Cross-story context in Epic 3: FR37-FR43 are downstream and rely on this runtime mode activation.
- Reliability requirement: graceful offset commit on shutdown (`NFR-I4`).
- Health requirement: runtime mode pod health must expose component state transitions relevant to consumer lifecycle (`FR54` + D6 guidance).
- Degradation model: use existing exception taxonomy and health/degraded signaling behavior; no silent failures.

### Architecture Compliance

- Follow D6 exactly:
  - `confluent-kafka` consumer.
  - Sequential processing loop.
  - Thin adapter protocol for testability.
  - Consumer group `aiops-cold-path-diagnosis` on topic `aiops-case-header`.
- Follow structure boundaries:
  - Composition root/wiring in `__main__.py`.
  - Kafka consumer adapter in `integrations/kafka_consumer.py`.
  - No cross-mode import drift; preserve cold-path package boundary.
- Health behavior:
  - Keep existing `/health` envelope; add component-level consumer fields for connected/lag/last-poll semantics.

### Library / Framework Requirements

- Repository-pinned versions (from `pyproject.toml`):
  - `confluent-kafka==2.13.0`
  - `pydantic==2.12.5`
  - `pydantic-settings~=2.13.1`
  - `pytest==9.0.2`
  - `testcontainers==4.14.1`
- Keep runtime consumer implementation on `confluent-kafka`; do not introduce alternate Kafka client libraries.
- Keep consume loop synchronous for this story (consistent with architecture decision D6).
- Preserve Kerberos/SASL_SSL fail-fast config validation behavior in `Settings`.

### File Structure Requirements

Primary implementation files:
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/integrations/kafka_consumer.py` (new)
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/health/registry.py` (if state fields need extension)

Primary tests:
- `tests/unit/test_main.py`
- `tests/unit/integrations/test_kafka_consumer.py` (new)
- `tests/integration/cold_path/test_consumer_lifecycle.py` (new)
- `tests/integration/conftest.py` (only if shared fixtures are required)

Documentation/config:
- `docs/runtime-modes.md`
- `docs/local-development.md`
- `README.md`
- `config/.env.local`
- `config/.env.dev`
- `config/.env.docker`
- `config/.env.uat.template`
- `config/.env.prod.template`

### Testing Requirements

- Unit tests must cover:
  - adapter configuration and boundary protocol behavior
  - poll outcomes (`None`, error message, valid message)
  - schema validation path for consumed event payloads
  - commit and close behavior, including failure paths
- Main/runtime tests must cover:
  - `--mode cold-path` dispatch path in `main()`
  - `_run_cold_path()` wiring and non-stub lifecycle behavior
- Integration tests must cover:
  - consumer group/topic subscription against real Kafka testcontainer
  - sequential processing behavior and graceful shutdown commit path
- Regression gates:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - zero skipped tests required.

### Latest Tech Information

External verification date: 2026-03-22.

- Confluent Python client docs confirm consumer best practices still center on `subscribe()` + `poll()` loops and explicit `Consumer.close()` on shutdown to commit final offsets and trigger immediate group rebalance.
- Confluent docs explicitly call out `group.id` as mandatory consumer configuration.
- PyPI currently lists `confluent-kafka` `2.13.2` (uploaded 2026-03-02). This project intentionally pins `2.13.0`; keep upgrade work out of scope for this story.
- PyPI notes pre-built Linux `confluent-kafka` wheels do not include Kerberos/GSSAPI; preserve existing SASL_SSL/Kerberos fail-fast checks and environment prerequisites.
- PyPI currently lists `testcontainers` `4.14.2` (uploaded 2026-03-18). The project pin is `4.14.1`; no dependency bump in this story.

### Project Context Reference

Applied `archive/project-context.md` guidance:
- contract-first validation at I/O boundaries
- hot/cold separation and deterministic guardrail preservation
- shared logging/health/exception taxonomy (no parallel frameworks)
- no silent failure on critical paths and no skipped-test regressions.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 3, Story 3.1, FR36]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR36, FR54]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-I4]
- [Source: `artifact/planning-artifacts/prd/event-driven-pipeline-specific-requirements.md` — CR-07 requirements]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D6]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `archive/project-context.md`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `https://docs.confluent.io/kafka-clients/python/current/overview.html`]
- [Source: `https://pypi.org/project/confluent-kafka/`]
- [Source: `https://pypi.org/project/testcontainers/`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- ATDD red phase: 4 failing tests created by `bmad-tea-testarch-atdd` (2026-03-22)
- Implementation: `bmad-bmm-dev-story` (2026-03-22)
- Entry point: `ready-for-dev` with ATDD already complete

### Completion Notes List

- Created `src/aiops_triage_pipeline/integrations/kafka_consumer.py` with `KafkaConsumerAdapterProtocol` (runtime_checkable) and `ConfluentKafkaCaseHeaderConsumer` including SASL_SSL/GSSAPI support and graceful `_NO_OFFSET` handling in `commit()`.
- Replaced `_run_cold_path()` stub in `__main__.py` with full sequential consume loop. Added `_cold_path_consumer_loop()` async function, `_build_cold_path_consumer_adapter()` factory, `_process_cold_path_message()` decoder, and `_cold_path_process_event()` processor boundary for Story 3.2.
- Emits `kafka_cold_path_connected`, `kafka_cold_path_poll`, `kafka_cold_path_commit` health transitions at each lifecycle stage (AC 2 satisfied).
- Added `KAFKA_COLD_PATH_CONSUMER_GROUP` and `KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS` to `Settings` with `>0` validation and secret-safe `log_active_config` output.
- Updated all 5 env files (local, dev, docker, uat.template, prod.template).
- 11 new unit tests in `test_kafka_consumer.py`; 2 new tests replacing stub test in `test_main.py`; 4 integration tests in `cold_path/test_consumer_lifecycle.py`.
- All 4 ATDD red-phase tests now GREEN.
- Initial gate: 955 passed, 0 skipped, ruff clean.
- Code review (2026-03-22): Fixed 5 findings — added `pytestmark = pytest.mark.integration` to cold-path integration tests; fixed tautological assertion in `test_subscribe_and_poll_against_real_kafka`; added non-empty validation for `KAFKA_COLD_PATH_CONSUMER_GROUP` in Settings; removed dead `_FakeConsumer` class and `_make_adapter_with_fake_consumer` helper; added unit tests for `commit()` `_NO_OFFSET` suppression path and re-raise path; added settings validation unit tests for consumer group.
- Post-review gate: 926 unit/ATDD passed, 0 skipped, ruff clean.

### File List

- `src/aiops_triage_pipeline/integrations/kafka_consumer.py` (new)
- `src/aiops_triage_pipeline/__main__.py` (modified)
- `src/aiops_triage_pipeline/config/settings.py` (modified)
- `tests/unit/integrations/test_kafka_consumer.py` (new)
- `tests/unit/test_main.py` (modified)
- `tests/unit/config/test_settings.py` (modified — added consumer group validation tests)
- `tests/integration/cold_path/__init__.py` (new)
- `tests/integration/cold_path/test_consumer_lifecycle.py` (new)
- `tests/atdd/fixtures/story_3_1_test_data.py` (pre-existing ATDD fixture)
- `tests/atdd/test_story_3_1_implement_cold_path_kafka_consumer_runtime_mode_red_phase.py` (pre-existing ATDD test)
- `artifact/test-artifacts/atdd-checklist-3-1-implement-cold-path-kafka-consumer-runtime-mode.md` (pre-existing)
- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-22T22-28-03Z.json` (pre-existing)
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-22T22-28-03Z.json` (pre-existing)
- `artifact/test-artifacts/tea-atdd-summary-2026-03-22T22-28-03Z.json` (pre-existing)
- `config/.env.local` (modified)
- `config/.env.dev` (modified)
- `config/.env.docker` (modified)
- `config/.env.uat.template` (modified)
- `config/.env.prod.template` (modified)
- `docs/runtime-modes.md` (modified)
- `docs/local-development.md` (modified)
- `README.md` (modified)
- `artifact/implementation-artifacts/3-1-implement-cold-path-kafka-consumer-runtime-mode.md` (this file)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified)

## Change Log

- 2026-03-22: Implemented cold-path Kafka consumer runtime mode (Story 3.1). Replaced bootstrap stub with live sequential consumer loop, added adapter boundary, health transitions, configuration, tests, and documentation.
- 2026-03-22: Code review fixes — added integration test markers, fixed tautological assertion, added settings-level consumer group non-empty validation, removed dead test code, added commit() error path unit tests.

## Story Completion Status

- Story status: `done`
- Completion note: All 6 tasks complete. 4 ATDD tests GREEN, 926 unit/ATDD tests passed (0 skipped), ruff clean. Code review findings fixed: integration test markers, tautological assertion, settings validation, dead code, commit error path tests.
