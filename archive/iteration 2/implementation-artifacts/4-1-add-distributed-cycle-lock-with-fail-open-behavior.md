# Story 4.1: Add Distributed Cycle Lock with Fail-Open Behavior

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/platform engineer,
I want only one hot-path pod to own each cycle interval when enabled,
so that multi-replica deployments avoid duplicate interval execution.

**Implements:** FR44, FR45

## Acceptance Criteria

1. **Given** `DISTRIBUTED_CYCLE_LOCK_ENABLED=true`
   **When** a cycle starts across multiple pods
   **Then** lock acquisition uses Redis `SET NX EX` with configured TTL margin
   **And** non-holders yield that interval and retry on next scheduler tick.

2. **Given** Redis is unavailable during lock attempt
   **When** cycle ownership cannot be resolved
   **Then** hot-path fails open and executes cycle with degraded state
   **And** degraded health/metrics are emitted without halting service.

## Tasks / Subtasks

- [x] Task 1: Implement distributed cycle lock component with explicit outcomes (AC: 1, 2)
  - [x] Add `src/aiops_triage_pipeline/coordination/` package with `protocol.py`, `cycle_lock.py`, and `__init__.py` public API exports.
  - [x] Implement lock keying per D1 (`aiops:lock:cycle`) and TTL computation `HOT_PATH_SCHEDULER_INTERVAL_SECONDS + CYCLE_LOCK_MARGIN_SECONDS` (default margin 60s).
  - [x] Use atomic Redis `SET key value NX EX` semantics only; do not add explicit unlock logic.
  - [x] Return structured lock outcomes for `acquired`, `yielded`, and `fail_open` (with holder/reason context for logs/metrics).

- [x] Task 2: Wire feature-flagged lock flow into hot-path scheduler loop (AC: 1, 2)
  - [x] Extend settings/env handling with `DISTRIBUTED_CYCLE_LOCK_ENABLED` (default `False`) and `CYCLE_LOCK_MARGIN_SECONDS` (>0).
  - [x] In `src/aiops_triage_pipeline/__main__.py`, gate cycle execution on lock outcome when feature flag is enabled.
  - [x] Preserve current behavior exactly when feature flag is disabled.
  - [x] On `yielded`, skip pipeline stage execution for that interval and sleep to next boundary.
  - [x] On `fail_open`, continue cycle execution while marking Redis/coordination degraded.

- [x] Task 3: Add lock observability and degraded signaling (AC: 1, 2)
  - [x] Add coordination counters in `src/aiops_triage_pipeline/health/metrics.py`: acquired, yielded, failed-open.
  - [x] Emit structured scheduler/coordination logs for acquisition, yield, and fail-open paths including pod identity and TTL context.
  - [x] Ensure degraded health updates are visible via existing health registry flow and do not halt loop progress.

- [x] Task 4: Add focused unit coverage for lock behavior and scheduler integration (AC: 1, 2)
  - [x] Add `tests/unit/coordination/test_cycle_lock.py` for atomic acquisition, contention/yield, fail-open on Redis exceptions, and TTL margin behavior.
  - [x] Extend `tests/unit/test_main.py` and/or `tests/unit/pipeline/test_scheduler.py` for feature-flag on/off behavior and yield/fail-open control flow.
  - [x] Extend `tests/unit/config/test_settings.py` for new settings defaults and validation.
  - [x] Extend `tests/unit/health/test_metrics.py` for coordination metric emission.

- [x] Task 5: Add integration contention test with real Redis (AC: 1)
  - [x] Add `tests/integration/coordination/test_cycle_lock_contention.py` using testcontainers Redis to verify two contenders produce one winner and one yielder per interval.
  - [x] Verify lock expiry enables reacquisition on subsequent interval without manual unlock.

- [x] Task 6: Update operator/deployment documentation for rollout safety (AC: 1, 2)
  - [x] Update `docs/architecture.md`, `docs/deployment-guide.md`, `docs/runtime-modes.md`, and `README.md` with feature flag semantics and fail-open behavior.
  - [x] Document new environment variables and safe default rollout (`DISTRIBUTED_CYCLE_LOCK_ENABLED=false`).

## Dev Notes

### Developer Context Section

- This is the first story in Epic 4 and is the foundation for multi-replica coordination safety; keep scope tight to cycle ownership and fail-open behavior.
- Current hot-path loop in `src/aiops_triage_pipeline/__main__.py` executes every interval unconditionally. Story 4.1 introduces optional lock gating without regressing single-instance behavior.
- Existing Redis degraded handling today is dedupe-centric (`emit_redis_degraded_mode_events` in `pipeline/scheduler.py`); cycle-lock degradation must integrate with the same operational posture: visible, capped, non-halting.
- Reuse the existing shared Redis client initialization pattern in `__main__.py`; do not create per-cycle Redis clients.

### Technical Requirements

- FR44: one pod owns the interval when distributed lock is enabled.
- FR45: Redis failure during lock attempt must fail open and preserve cycle execution.
- NFR-SC1: hot/hot deployments must avoid duplicate dispatch side effects.
- NFR-SC4: Redis remains the single shared coordination layer.
- NFR-R4: fail-open behavior is mandatory (degrade, never halt).
- NFR-P3: cycle completion rate remains 100% even under degradable failures.

### Architecture Compliance

- D1: use Redis namespace `aiops:{data_type}:{scope_key}` (`aiops:lock:cycle`).
- D2: Redis is ephemeral; correctness must not depend on lock persistence across restarts.
- D3: on Redis unavailability, cycle lock degrades fail-open with explicit degraded signaling.
- D5: protocol is `SET NX EX`, TTL-based expiry, no explicit unlock, feature-flag guarded.
- D13: continue using shared Redis connection model in composition root.
- Implementation patterns: wire dependencies in `__main__.py`; avoid module-level mutable singletons.

### Library / Framework Requirements

- Maintain project runtime stack and pins unless explicitly approved for change:
  - Python `>=3.13`
  - `redis==7.2.1` (project pin)
  - `pytest==9.0.2`, `testcontainers==4.14.1`
- Redis lock acquisition must use redis-py `set(..., nx=True, ex=...)` compatible with current pin.
- Do not use new Redis 8.4-only `SET` options (`IFEQ`/`IFNE`/etc.) in this story.

### File Structure Requirements

Primary implementation targets:
- `src/aiops_triage_pipeline/coordination/__init__.py` (new)
- `src/aiops_triage_pipeline/coordination/protocol.py` (new)
- `src/aiops_triage_pipeline/coordination/cycle_lock.py` (new)
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/health/metrics.py`

Primary test targets:
- `tests/unit/coordination/test_cycle_lock.py` (new)
- `tests/unit/test_main.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/health/test_metrics.py`
- `tests/integration/coordination/test_cycle_lock_contention.py` (new)

Documentation targets:
- `docs/architecture.md`
- `docs/deployment-guide.md`
- `docs/runtime-modes.md`
- `README.md`

### Testing Requirements

- Unit tests must verify:
  - deterministic lock outcome mapping (`acquired` / `yielded` / `fail_open`),
  - TTL margin computation correctness,
  - feature-flag behavior parity with current execution path,
  - yielded intervals skip stage execution,
  - fail-open executes full cycle and emits degraded observability.
- Integration tests must verify real Redis contention across concurrent contenders and TTL-based reacquisition.
- Regression commands for implementation:
  - `uv run ruff check`
  - `uv run pytest -q tests/unit`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Quality gate expectation: zero skipped tests in full regression.

### Latest Tech Information

External verification date: 2026-03-23.

- `redis` (redis-py) latest PyPI release is `7.3.0` (released 2026-03-06), while this repo is pinned to `7.2.1`.
- redis-py command reference confirms `set(..., nx=True, ex=...)` remains supported and documents additional newer options.
- Redis command docs show modern `SET` syntax includes newer conditional options (including 8.4-era options), but this story should stay with `NX + EX` only for compatibility and clarity.
- Redis download channel indicates active stable releases; no migration is required for this story because architecture lock and acceptance criteria are protocol-level, not upgrade-driven.

### Project Context Reference

Applied `archive/project-context.md` rules:
- preserve deterministic guardrail authority and hot/cold separation,
- avoid unsafe fallbacks (fail-open only where architecture explicitly permits it),
- keep structured logging and health signaling explicit,
- keep changes scoped, test-backed, and traceable to FR/NFR/decision IDs.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 4 / Story 4.1]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR44, FR45]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-SC1, NFR-SC4, NFR-R4, NFR-P3]
- [Source: `artifact/planning-artifacts/prd/event-driven-pipeline-specific-requirements.md` — Distributed Coordination Requirements]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` — Degraded Mode + Multi-Replica Coordination Safety]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D1, D2, D3, D5, D13]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/planning-artifacts/architecture/project-context-analysis.md`]
- [Source: `artifact/planning-artifacts/architecture/architecture-validation-results.md`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/health/metrics.py`]
- [Source: `tests/unit/test_main.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: `tests/unit/config/test_settings.py`]
- [Source: `tests/unit/health/test_metrics.py`]
- [Source: `tests/integration/conftest.py`]
- [Source: `https://redis.io/docs/latest/commands/set/`]
- [Source: `https://redis.readthedocs.io/en/stable/commands.html`]
- [Source: `https://pypi.org/project/redis/`]
- [Source: `https://download.redis.io/`]

## Dev Agent Record

### Agent Model Used

gpt-5-codex

### Debug Log References

- create-story workflow execution for explicit story key `4-1-add-distributed-cycle-lock-with-fail-open-behavior`
- artifact analysis: sprint status, epic/PRD/architecture/project-context sources, and current hot-path wiring/tests
- latest-tech verification: Redis command docs, redis-py docs, redis PyPI metadata, Redis download channel
- `uv run pytest -q tests/atdd/test_story_4_1_add_distributed_cycle_lock_with_fail_open_behavior_red_phase.py` (RED baseline: 7 failures)
- `uv run ruff check`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (full regression)

### Completion Notes List

- Implemented new `coordination` package with structured lock outcome protocol and Redis `SET NX EX` cycle lock.
- Added feature-flagged hot-path lock gating with yielded-interval skip and fail-open degraded execution paths.
- Added coordination observability counters and scheduler logs for acquired/yielded/fail-open outcomes.
- Added unit and integration coverage for lock semantics, scheduler flow branches, settings validation, and metrics.
- Updated architecture/deployment/runtime docs and README with rollout-safe lock configuration guidance.
- Completed full regression with zero skips.

### File List

- `src/aiops_triage_pipeline/coordination/__init__.py`
- `src/aiops_triage_pipeline/coordination/protocol.py`
- `src/aiops_triage_pipeline/coordination/cycle_lock.py`
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/health/metrics.py`
- `tests/unit/coordination/__init__.py`
- `tests/unit/coordination/test_cycle_lock.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/health/test_metrics.py`
- `tests/unit/test_main.py`
- `tests/integration/coordination/test_cycle_lock_contention.py`
- `tests/atdd/fixtures/story_4_1_test_data.py`
- `tests/atdd/test_story_4_1_add_distributed_cycle_lock_with_fail_open_behavior_red_phase.py`
- `docs/architecture.md`
- `docs/deployment-guide.md`
- `docs/runtime-modes.md`
- `README.md`
- `artifact/test-artifacts/atdd-checklist-4-1-add-distributed-cycle-lock-with-fail-open-behavior.md`
- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-23T12-07-14Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-23T12-07-14Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-23T12-07-14Z.json`
- `artifact/implementation-artifacts/4-1-add-distributed-cycle-lock-with-fail-open-behavior.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-03-23: Implemented Story 4.1 distributed cycle lock with fail-open behavior, tests, and rollout documentation.
- 2026-03-23: Senior code review fixes applied (integration no-skip prerequisite enforcement, lock input validation, file-list traceability sync).

### Story Completion Status

- Story status: `done`
- Completion note: Implementation complete; review fixes validated with targeted regression (`74` unit tests, `2` integration tests) for cycle-lock behavior and scheduler integration.

### Senior Developer Review (AI)

- Outcome: Changes requested then fixed in-place.
- Findings fixed:
  - [Medium] `tests/integration/coordination/test_cycle_lock_contention.py`: environment prerequisite path used `pytest.skip(...)`, which violates sprint quality expectation of zero skipped tests. Fixed by failing fast with `pytest.fail(...)`.
  - [Medium] `artifact/implementation-artifacts/4-1-add-distributed-cycle-lock-with-fail-open-behavior.md`: Dev Agent Record file list omitted actual changed files (ATDD source + generated ATDD artifacts). Fixed by synchronizing file list to git reality.
  - [Low] `src/aiops_triage_pipeline/coordination/cycle_lock.py`: `acquire()` accepted non-positive `interval_seconds` and silently coerced TTL; this could hide invalid scheduler inputs. Fixed with explicit `ValueError` validation and unit coverage.
