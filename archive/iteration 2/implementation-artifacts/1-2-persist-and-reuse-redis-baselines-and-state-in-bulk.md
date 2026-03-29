# Story 1.2: Persist and Reuse Redis Baselines and State in Bulk

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want baseline and sustained-state Redis interactions to be persisted and batch-loaded,
so that triage decisions remain consistent across cycles and perform at scale.

**Implements:** FR3, FR4, FR5, FR6

## Acceptance Criteria

1. **Given** historical metric windows are available
   **When** baselines are computed for each scope/metric
   **Then** baseline values are persisted to Redis using environment-specific TTL policy
   **And** subsequent cycles read those persisted baselines before threshold evaluation.

2. **Given** sustained state and peak profile keys exist for many scopes
   **When** the hot-path loads required Redis data
   **Then** keys are fetched using batched operations rather than per-key sequential round trips
   **And** the implementation follows the approved Redis key namespace convention.

## Tasks / Subtasks

- [x] Task 1: Wire sustained-window state persistence through Redis, not in-process memory (AC: 2)
  - [x] Replace `prior_sustained_window_state_by_key` in-memory carryover in hot-path loop with Redis-backed load/persist per cycle.
  - [x] Load sustained states before peak/sustained evaluation and persist updated states after evaluation.
  - [x] Preserve conservative degradation behavior: Redis failure falls back to `None` state (no false sustained=true).

- [x] Task 2: Implement baseline persistence + retrieval for anomaly/peak evaluation (AC: 1)
  - [x] Add a Redis-backed baseline store module using D1 key pattern (`aiops:baseline:{source}:{scope_key}:{metric_key}`).
  - [x] Ensure anomaly/peak logic reads per-scope baselines from Redis before thresholding.
  - [x] Keep cold-start defaults when baseline history is insufficient or Redis is unavailable.

- [x] Task 3: Introduce batched Redis reads for sustained + peak profile retrieval (AC: 2)
  - [x] Replace sequential per-key GET loops with batched retrieval (`MGET` and/or pipelined GET execution).
  - [x] Keep deterministic key ordering so mapping from response index -> key remains stable.
  - [x] Keep warning-only cache-consumer failure handling (no hot-path halt).

- [x] Task 4: Align Redis keys with architecture namespace and preserve backward rollout safety (AC: 2)
  - [x] Migrate cache key builders to `aiops:{type}:{scope_key}` naming (D1).
  - [x] Keep legacy-key fallback reads where required for smooth in-place rollout.
  - [x] Ensure TTL application remains environment-specific via `redis-ttl-policy-v1.yaml`.

- [x] Task 5: Keep composition-root and dependency wiring consistent (AC: 1, 2)
  - [x] Reuse shared `redis.Redis.from_url(...)` client from `__main__.py`; do not introduce module-level Redis singletons.
  - [x] Pass Redis dependencies via constructor/function parameters following existing DI patterns.
  - [x] Do not introduce `redis.asyncio` in this story.

- [x] Task 6: Add/adjust focused tests and run quality gates (AC: 1, 2)
  - [x] Unit tests for baseline-store keying/TTL/fallback and sustained-state bulk load behavior.
  - [x] Unit tests proving batched Redis retrieval path is used and deterministic.
  - [x] Scheduler/stage tests for Redis degraded behavior and no-regression sustained semantics.
  - [x] Run full regression and lint with zero skipped tests.

## Dev Notes

### Developer Context Section

- This story is the first Redis state externalization step in Epic 1 and is load-bearing for later distributed/hot-hot work (FR9/FR44-48).
- Current implementation signals the exact gaps this story must close:
  - `__main__.py` hot-path loop currently passes `historical_windows_by_scope={}` and stores sustained state in process memory only.
  - `cache/evidence_window.py` bulk loader is still sequential (`for key -> get`) and uses non-D1 key prefix (`evidence:`).
  - `cache/peak_cache.py` uses non-D1 key prefix (`peak:`).
  - No `pipeline/baseline_store.py` exists yet in this branch despite architecture plan.
- Preserve deterministic hot-path behavior: no LLM work, no blocking architecture changes, no policy file I/O in per-cycle path.
- Treat Redis as accelerator, not source-of-truth (D2): correctness must hold through Redis restarts/failures.

### Technical Requirements

- FR3/FR4 baseline behavior:
  - Baselines must be per-scope/per-metric and persisted in Redis with env-specific TTL.
  - Threshold evaluation must consume persisted baselines before applying fallback defaults.
- FR5 sustained behavior:
  - Load sustained-window state from Redis before sustained computation.
  - Persist updated sustained state after computation.
  - On Redis failure, fallback to missing prior state (`None`) and continue safely.
- FR6 bulk-load behavior:
  - Required Redis reads for sustained state and peak profile retrieval must be batched.
  - Avoid N sequential round trips for N keys.
- D1 key namespace compliance (must use these patterns):
  - `aiops:sustained:{cluster}:{topic_or_group}:{anomaly_family}`
  - `aiops:peak:{cluster}:{topic}`
  - `aiops:baseline:{source}:{scope_key}:{metric_key}`
- D3 degradation requirements:
  - Cache consumers (baselines/sustained/peak cache) warn and continue with conservative fallback.
  - No pipeline halt for cache-miss/cache-read failures.
- D13 connection model:
  - Reuse shared Redis client/pool from composition root; do not create isolated pools per module.

### Architecture Compliance

- Keep composition-root dependency wiring in `src/aiops_triage_pipeline/__main__.py`.
- Keep two-tier Redis error handling pattern:
  - Critical Redis consumers: track health and re-raise for degraded-mode handling.
  - Cache Redis consumers: warn-log and continue with fallback values.
- Maintain hot/cold path separation; this story must only affect hot-path/cache/stage logic.
- Keep immutable contract/model behavior (`frozen=True` policy and contract models) unchanged.
- Preserve UNKNOWN semantics; missing data must not be silently coerced to present/zero.
- Keep stage orchestration order unchanged (evidence -> peak -> topology -> gate -> casefile -> dispatch).

### Library / Framework Requirements

- Runtime stack remains project-pinned for this story unless explicitly scoped for upgrade:
  - Python `>=3.13`
  - `redis==7.2.1` (project pin)
  - `pydantic==2.12.5`
  - `pydantic-settings~=2.13.1`
  - `SQLAlchemy==2.0.47`
  - `pytest==9.0.2`
- Redis client usage requirements:
  - Continue using sync `redis.Redis` client.
  - For bulk operations, use official Redis batching semantics (`MGET` and/or pipelined commands).
- Do not introduce new Redis client abstractions that hide key construction or error semantics.

### Project Structure Notes

- Existing files likely requiring modification for Story 1.2:
  - `src/aiops_triage_pipeline/__main__.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/pipeline/stages/peak.py`
  - `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
  - `src/aiops_triage_pipeline/cache/evidence_window.py`
  - `src/aiops_triage_pipeline/cache/peak_cache.py`
  - `src/aiops_triage_pipeline/contracts/redis_ttl_policy.py` (only if TTL-shape adjustments are required)
- Architecture-planned additions likely needed:
  - `src/aiops_triage_pipeline/pipeline/baseline_store.py`
  - `src/aiops_triage_pipeline/pipeline/baseline_collector.py` (if baseline computation contract is introduced in this story scope)
- Existing tests to extend first:
  - `tests/unit/cache/test_evidence_window.py`
  - `tests/unit/cache/test_peak_cache.py`
  - `tests/unit/pipeline/stages/test_peak.py`
  - `tests/unit/pipeline/test_scheduler.py`
- Add integration coverage if new Redis batch path or scheduler wiring cannot be trusted by unit tests alone.

### Testing Requirements

- Required behavior checks for this story:
  - Baseline Redis key generation + TTL by env + fallback defaults.
  - Sustained state load-before-evaluate and persist-after-evaluate.
  - Bulk read path executes batched retrieval, not sequential GET loop.
  - Redis failure paths preserve degraded/continue semantics.
  - Deterministic mapping from key set to loaded states in bulk mode.
- Quality gate commands:
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - `uv run ruff check`
- Sprint quality gate remains mandatory: zero skipped tests.

### Previous Story Intelligence

- Story 1.1 learnings to carry forward:
  - Prefer robust exception classification over brittle message matching.
  - Strengthen assertions so tests cannot pass on empty/degenerate data.
  - Keep offline/air-gapped CI paths explicit when tests rely on container/image availability.
  - Keep story completion notes traceable to actual changed files and scope.
- Current Story 1.1 artifact is marked `done`; Story 1.2 should preserve its Stage 1 semantics while adding Redis state persistence and bulk loading.

### Git Intelligence Summary

- Recent commit pattern (`9875fbd` -> `a1691ae` -> `4b6f3d3`) shows workflow discipline:
  - Story context creation and sprint tracking first.
  - Implementation/review hardening second.
  - Final status synchronization after validation.
- Most recent code changes touched:
  - `src/aiops_triage_pipeline/__main__.py`
  - `tests/integration/integrations/test_prometheus_local.py`
- Guidance:
  - Keep Story 1.2 changes localized to Redis/baseline/sustained concerns.
  - Preserve traceability in story file and sprint status updates.

### Latest Tech Information

- Snapshot date: 2026-03-22.
- PyPI latest package versions checked:
  - `redis`: `7.3.0` (uploaded 2026-03-06) while project pin is `7.2.1`.
  - `pydantic`: `2.12.5` (uploaded 2025-11-26) matches project pin.
  - `pydantic-settings`: `2.13.1` (uploaded 2026-02-19) matches project constraint `~=2.13.1`.
  - `pytest`: `9.0.2` (uploaded 2025-12-06) matches project pin.
  - `SQLAlchemy`: `2.0.48` (uploaded 2026-03-02) is newer than project pin `2.0.47`.
- Redis command/docs notes relevant to AC2 implementation:
  - `MGET` complexity is documented as O(N) for N keys (single round-trip read for multi-key string fetch).
  - redis-py pipeline/transaction docs remain the reference for grouped command execution semantics.
- Story implementation guidance from this update:
  - Do not upgrade dependencies in Story 1.2 unless explicitly scoped.
  - Implement batch read/write patterns compatible with `redis==7.2.1`.

### Project Context Reference

- Project-level AI guardrails and architecture constraints loaded from `archive/project-context.md`.
- Story-specific implementation must follow:
  - Python 3.13 typing style.
  - Shared cross-cutting primitives (logging, health registry, denylist where applicable).
  - No silent critical-path fallback; degradable dependencies continue with explicit degraded posture.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Epic 1, Story 1.2]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` - FR3, FR4, FR5, FR6]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-P5, NFR-R5, NFR-SC4]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` - degraded mode and UNKNOWN invariants]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` - D1, D2, D3, D8, D13]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `archive/project-context.md`]
- [Source: `artifact/implementation-artifacts/1-1-collect-telemetry-and-detect-core-anomalies.md`]
- [Source: `artifact/implementation-artifacts/sprint-status.yaml`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/peak.py`]
- [Source: `src/aiops_triage_pipeline/cache/evidence_window.py`]
- [Source: `src/aiops_triage_pipeline/cache/peak_cache.py`]
- [Source: `tests/unit/cache/test_evidence_window.py`]
- [Source: `tests/unit/cache/test_peak_cache.py`]
- [Source: `tests/unit/pipeline/stages/test_peak.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: https://pypi.org/pypi/redis/json]
- [Source: https://pypi.org/pypi/pydantic/json]
- [Source: https://pypi.org/pypi/pydantic-settings/json]
- [Source: https://pypi.org/pypi/pytest/json]
- [Source: https://pypi.org/pypi/SQLAlchemy/json]
- [Source: https://redis.io/docs/latest/commands/mget/]
- [Source: https://redis.io/docs/latest/develop/clients/redis-py/transpipe/]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Implemented Redis-backed sustained-state load/persist in hot-path cycle and removed in-process carryover.
- Added baseline Redis store + evidence/anomaly baseline reuse path with cold-start fallback behavior.
- Added batched MGET loaders for sustained and peak cache reads with deterministic key ordering and legacy-key fallback.
- Validation executed:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Completed FR3/FR4 baseline persistence by adding `pipeline/baseline_store.py` and integrating load/persist into evidence processing.
- Completed FR5 by loading sustained state from Redis before peak/sustained evaluation and persisting updated state after each cycle.
- Completed FR6 by replacing sequential sustained/peak cache reads with batched retrieval and deterministic mapping.
- Migrated sustained/peak Redis keys to D1-aligned `aiops:{type}:...` namespace with backward-compatible legacy fallbacks.
- Added/updated targeted unit and scheduler tests for baseline store behavior, batch loading, and cached-profile peak evaluation.
- Fixed hot-path sustained key candidate loading so persisted sustained state can be reused when no fresh anomalies exist for a scope.
- Fixed hot-path peak bootstrap wiring to hydrate `historical_windows_by_scope` from persisted Redis baselines.
- Full lint + regression gates passed with zero skipped tests.

### File List

- artifact/implementation-artifacts/1-2-persist-and-reuse-redis-baselines-and-state-in-bulk.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/__main__.py
- src/aiops_triage_pipeline/cache/__init__.py
- src/aiops_triage_pipeline/cache/evidence_window.py
- src/aiops_triage_pipeline/cache/peak_cache.py
- src/aiops_triage_pipeline/pipeline/baseline_store.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- src/aiops_triage_pipeline/pipeline/stages/anomaly.py
- src/aiops_triage_pipeline/pipeline/stages/evidence.py
- src/aiops_triage_pipeline/pipeline/stages/peak.py
- tests/unit/cache/test_evidence_window.py
- tests/unit/cache/test_peak_cache.py
- tests/unit/pipeline/stages/test_anomaly.py
- tests/unit/pipeline/test_baseline_store.py
- tests/unit/pipeline/test_scheduler.py
- tests/unit/test_main.py

## Story Completion Status

- Story status: `done`
- Completion note: Redis baseline/sustained persistence and batch retrieval implementation completed; hot-path sustained-key continuity and peak baseline bootstrap fixes applied; full quality gates passed with zero skips.

## Senior Developer Review (AI)

- Review date: 2026-03-22
- Outcome: Approved after fixes
- Resolved issues:
  - Hot-path now loads sustained-state candidates from findings + observed scopes + prior cycle keys, closing continuity gaps during non-anomalous cycles.
  - Hot-path peak stage now receives Redis baseline-derived historical windows, closing threshold bootstrap gaps when cached peak profiles are absent.
  - Story technical requirement updated to reflect implemented sustained key shape.
- Verification:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - Result: `838 passed`, `0 skipped`

## Change Log

- 2026-03-22: Story created via create-story workflow with exhaustive artifact/code analysis and ready-for-dev implementation context.
- 2026-03-22: Implemented Story 1.2 (FR3-FR6): Redis baseline store integration, sustained/peak batch reads, D1 key migration with fallback, and full quality gate validation.
- 2026-03-22: Code review fixes applied: sustained-state key candidate expansion, peak baseline-window bootstrap from Redis baselines, story status sync to done.
