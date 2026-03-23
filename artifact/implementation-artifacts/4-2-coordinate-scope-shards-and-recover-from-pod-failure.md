# Story 4.2: Coordinate Scope Shards and Recover from Pod Failure

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want scope shard assignment and lease recovery for findings work,
so that distributed execution scales while remaining resilient to pod loss.

**Implements:** FR46, FR47

## Acceptance Criteria

1. **Given** multiple hot-path pods are active
   **When** shard coordination is enabled
   **Then** scope workloads are assigned per shard and checkpointed per interval
   **And** checkpoint writes are batch-oriented rather than per-scope writes.

2. **Given** a pod holding shard responsibility fails
   **When** lease expiry elapses
   **Then** another pod can safely resume shard processing
   **And** no manual intervention is required for recovery.

## Tasks / Subtasks

- [x] Task 1: Implement shard coordination and lease primitives on Redis (AC: 1, 2)
  - [x] Add shard lease/checkpoint key builders using D1 naming (`aiops:shard:...`) and TTL-based lease ownership.
  - [x] Implement deterministic shard assignment (consistent-hash path from D11-D12) from active pod membership.
  - [x] Add lease acquire/renew/expire behavior so a shard can be resumed automatically after pod failure.

- [x] Task 2: Integrate shard routing into findings-cache execution path (AC: 1, 2)
  - [x] Update findings-cache workflow so each pod processes only scopes mapped to its current shard set when enabled.
  - [x] Replace per-scope coordination writes with per-shard, per-interval checkpoint writes.
  - [x] Preserve existing cache read/write behavior when shard coordination is disabled.

- [x] Task 3: Wire runtime settings and composition-root dependencies (AC: 1, 2)
  - [x] Add shard feature flags/settings in `config/settings.py` (disabled-by-default rollout posture).
  - [x] Wire shard coordination dependencies in `__main__.py` using existing shared Redis client.
  - [x] Keep lock flow from Story 4.1 intact and avoid regressions in cycle lock behavior.

- [x] Task 4: Add degraded-mode and observability coverage for shard coordination (AC: 1, 2)
  - [x] Emit structured events for shard assignment, lease acquire/renew/yield/recovery.
  - [x] Add OTLP metrics in `health/metrics.py` for shard checkpoints and lease recovery outcomes.
  - [x] On Redis shard-coordination failures, follow D3 behavior: warn, mark degraded, and fall back to full-scope processing.

- [x] Task 5: Add unit and integration coverage for lease contention/recovery race paths (AC: 1, 2)
  - [x] Add unit tests for deterministic assignment, lease expiry handoff, and checkpoint batching.
  - [x] Add integration tests (real Redis via testcontainers) for two-pod contention and failed-holder recovery.
  - [x] Ensure tests enforce no-skip posture for missing prerequisites (fail fast, do not `pytest.skip`).

- [x] Task 6: Update operator documentation for shard rollout and recovery behavior (AC: 1, 2)
  - [x] Update `docs/runtime-modes.md`, `docs/deployment-guide.md`, `docs/architecture.md`, and `README.md`.
  - [x] Document feature flags, lease TTL behavior, recovery expectations, and rollback path.

## Dev Notes

### Developer Context Section

- Story 4.1 established distributed cycle lock as the first coordination layer; Story 4.2 adds shard-level throughput coordination for findings work without regressing lock/fail-open safety.
- Existing findings cache is scope-oriented (`cache/findings_cache.py`) and currently computes per scope; this story introduces shard assignment and per-shard interval checkpoints.
- Keep implementation aligned to the architecture’s deferred-sharding plan (D11-D12): lightweight consistent hash + Redis membership/lease primitives, feature-flagged rollout.
- This story is explicitly high-risk for failure-mode races (lease contention and holder-failure recovery), and tests must cover those race paths.

### Technical Requirements

- FR46: assign scope workloads per shard and checkpoint by shard per interval.
- FR47: recover shard processing automatically after holder failure via lease expiry.
- NFR-SC2: support even scope distribution and O(1) checkpoint writes per shard per interval.
- NFR-SC4: use Redis as shared coordination state (no in-process exclusivity assumptions).
- NFR-R7: degradable dependency failures update health and continue with capped/fallback behavior.
- NFR-P3: cycle progression must continue (no scheduler halt) under degradable coordination failures.

### Architecture Compliance

- D1: use Redis namespace `aiops:{data_type}:{scope_key}` for shard keys.
- D2: Redis is ephemeral; shard correctness must not depend on persistent Redis state.
- D3: shard checkpoint/coordination failure must degrade to full-scope fallback, not halt.
- D11-D12: follow consistent-hash shard design and keep rollout behind `SHARD_REGISTRY_ENABLED`.
- D13: reuse shared Redis connection pooling model; do not introduce per-component pools.
- Maintain 4.1 cycle-lock protocol (`SET NX EX`, no explicit unlock) unchanged.

### Library / Framework Requirements

- Maintain locked stack unless explicitly approved:
  - Python `>=3.13`
  - `redis==7.2.1` (repo pin)
  - `pytest==9.0.2`
  - `testcontainers==4.14.1`
- Redis coordination operations must use redis-py APIs compatible with current pin.
- Avoid introducing `redis.asyncio` in this story; follow existing sync Redis client pattern.

### File Structure Requirements

Primary implementation targets:
- `src/aiops_triage_pipeline/cache/findings_cache.py`
- `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/coordination/protocol.py` (extend only if needed)
- `src/aiops_triage_pipeline/coordination/` (new shard-specific module(s) only if required)

Primary test targets:
- `tests/unit/cache/test_findings_cache.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/health/test_metrics.py`
- `tests/unit/coordination/` (new shard-coordination tests)
- `tests/integration/coordination/` (new lease-recovery contention tests)

Documentation targets:
- `docs/runtime-modes.md`
- `docs/deployment-guide.md`
- `docs/architecture.md`
- `README.md`

### Testing Requirements

- Unit tests must verify:
  - deterministic scope-to-shard assignment for stable inputs,
  - lease acquisition/renew/expiry/recovery transitions,
  - per-shard checkpoint batching semantics,
  - fallback-to-full-scope behavior on Redis coordination failures.
- Integration tests must verify:
  - multi-pod lease contention results in single active holder per shard lease interval,
  - failed-holder recovery occurs after lease expiry without manual intervention,
  - no-skip quality gate behavior for missing Docker prerequisites.
- Preferred full regression command (per AGENTS.md):
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Sprint quality gate expectation remains zero skipped tests.

### Previous Story Intelligence

- Story 4.1 introduced `coordination/` package conventions (`protocol.py`, specific module names, public API exports via `__init__.py`).
- Cycle lock outcomes are modeled via explicit status enum and outcome dataclass; reuse this explicit-state pattern for shard lease outcomes.
- 4.1 wired coordination health updates through `HealthRegistry` in `__main__.py`; shard coordination should follow the same path.
- 4.1 added coordination metrics in `health/metrics.py`; extend metrics there instead of inline module instrumentation.
- Integration tests were hardened to fail fast on missing Docker/Redis prerequisites (`pytest.fail` instead of skip); preserve this standard.

### Git Intelligence Summary

Recent commit analysis highlights relevant patterns:
- `3447ce6`: Story 4.1 implementation touched `__main__.py`, `config/settings.py`, `coordination/`, `health/metrics.py`, docs, and targeted unit/integration tests.
- `3e1a085`, `7af970f`: cold-path stories consistently updated runtime docs plus tests in same change sets.
- Story workflows consistently update `artifact/implementation-artifacts/*.md` and `sprint-status.yaml` together.

Actionable guidance:
- Keep changes localized to coordination/cache/scheduler plumbing and associated tests.
- Preserve current doc + tests-in-same-CR discipline.
- Avoid introducing unrelated architectural refactors while implementing shard coordination.

### Latest Tech Information

External verification date: 2026-03-23.

- PyPI currently lists `redis` Python client `7.3.0` as latest (released 2026-03-06); repo pin remains `7.2.1`.
- Redis command docs confirm `SET` supports `NX`/`XX` and TTL options (`EX`/`PX`/etc.), which remains the required primitive family for coordination leases.
- redis-py command docs show `set(name, value, ex=..., nx=...)` support and additional newer condition arguments; this story should stay with compatibility-safe semantics aligned to repo pin.
- Redis downloads page currently surfaces Redis Open Source `8.6`; no version-upgrade work is required for this story.

### Project Context Reference

Applied `archive/project-context.md` and implementation patterns:
- Python 3.13 typing and frozen contract discipline.
- Composition-root wiring in `__main__.py`; no service locator / DI container.
- Shared cross-cutting primitives (health registry, structured logging, denylist rules) must be reused.
- Degradable Redis-path failures must be explicit, observable, and non-halting.
- Full regression policy expects zero skipped tests.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 4 / Story 4.2]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR46, FR47]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-SC2, NFR-SC4, NFR-R7, NFR-P3]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` — degraded mode and multi-replica invariants]
- [Source: `artifact/planning-artifacts/prd/event-driven-pipeline-specific-requirements.md` — distributed coordination requirements]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D1, D2, D3, D11, D12, D13]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/planning-artifacts/implementation-readiness-report-2026-03-21.md`]
- [Source: `artifact/implementation-artifacts/4-1-add-distributed-cycle-lock-with-fail-open-behavior.md`]
- [Source: `src/aiops_triage_pipeline/cache/findings_cache.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `src/aiops_triage_pipeline/coordination/cycle_lock.py`]
- [Source: `src/aiops_triage_pipeline/coordination/protocol.py`]
- [Source: `src/aiops_triage_pipeline/health/metrics.py`]
- [Source: `tests/unit/cache/test_findings_cache.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: `tests/unit/config/test_settings.py`]
- [Source: `tests/unit/coordination/test_cycle_lock.py`]
- [Source: `tests/integration/coordination/test_cycle_lock_contention.py`]
- [Source: `https://pypi.org/project/redis/`]
- [Source: `https://redis.io/docs/latest/commands/set/`]
- [Source: `https://redis.readthedocs.io/en/v7.1.0/commands.html`]
- [Source: `https://redis.io/downloads/`]

## Dev Agent Record

### Agent Model Used

gpt-5-codex

### Debug Log References

- create-story workflow execution for explicit story key `4-2-coordinate-scope-shards-and-recover-from-pod-failure`
- artifact analysis: epic/prd/architecture/project-context + previous story + recent git history
- latest-tech verification: Redis command docs, redis-py command docs, PyPI package metadata, Redis downloads page
- checklist validation fallback: `_bmad/core/tasks/validate-workflow.xml` path referenced by workflow is not present in repository
- dev-story implementation: all 6 tasks completed; full regression 1097 passed, zero skipped (2026-03-23)

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Story prepared for `dev-story` execution with concrete implementation guardrails and source-backed references.
- Implemented `coordination/shard_registry.py`: `build_shard_lease_key`, `build_shard_checkpoint_key`, `assign_scopes_to_pod` (SHA-256 consistent hash), `RedisShardCoordinator.acquire_lease` with fail-open semantics matching 4.1 pattern.
- Extended `cache/findings_cache.py` with `build_shard_checkpoint_key` re-export and `set_shard_interval_checkpoint` for O(1) per-shard-per-interval writes (NFR-SC2).
- Added `SHARD_REGISTRY_ENABLED`, `SHARD_COORDINATION_SHARD_COUNT`, `SHARD_LEASE_TTL_SECONDS`, `SHARD_CHECKPOINT_TTL_SECONDS` to `config/settings.py` with >0 validators; all disabled-by-default.
- Added `record_shard_checkpoint_written`, `record_shard_lease_recovered`, `record_shard_assignment` OTLP counters to `health/metrics.py`.
- Wired `RedisShardCoordinator` into `__main__._hot_path_scheduler_loop` behind `SHARD_REGISTRY_ENABLED`; fallback to full_scope processing on any coordination failure (D3).
- 16 unit tests in `tests/unit/coordination/test_shard_registry.py`: key builders, deterministic assignment, lease acquire/yield/recovery/fail-open, checkpoint batching.
- 4 integration tests in `tests/integration/coordination/test_shard_lease_contention.py`: two-pod contention, failed-holder recovery, independent shards, NX renew semantics.
- All 7 ATDD red-phase tests pass (green phase complete).
- Full regression: 1097 passed, 0 skipped. Story 4.1 cycle lock behavior preserved — no regressions.

### File List

- `artifact/implementation-artifacts/4-2-coordinate-scope-shards-and-recover-from-pod-failure.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `src/aiops_triage_pipeline/coordination/shard_registry.py` (new)
- `src/aiops_triage_pipeline/cache/findings_cache.py` (modified)
- `src/aiops_triage_pipeline/config/settings.py` (modified)
- `src/aiops_triage_pipeline/health/metrics.py` (modified)
- `src/aiops_triage_pipeline/__main__.py` (modified)
- `tests/unit/coordination/test_shard_registry.py` (new)
- `tests/integration/coordination/test_shard_lease_contention.py` (new)
- `tests/unit/test_main.py` (modified — added SHARD_REGISTRY_ENABLED to test helper SimpleNamespace)
- `tests/atdd/test_story_4_2_coordinate_scope_shards_and_recover_from_pod_failure_red_phase.py` (pre-existing ATDD)
- `tests/atdd/fixtures/story_4_2_test_data.py` (pre-existing ATDD fixture)
- `docs/runtime-modes.md` (modified)
- `docs/deployment-guide.md` (modified)
- `docs/architecture.md` (modified)
- `README.md` (modified)

### Story Completion Status

- Story status: `review`
- Completion note: `All 6 tasks complete; 1097 tests pass (0 skipped); ATDD green; 4.1 cycle lock regressions: none`

### Change Log

- 2026-03-23: Implemented Story 4.2 — shard coordination with Redis lease/checkpoint primitives, deterministic scope assignment, degraded-mode fallback, OTLP metrics, and documentation updates.
