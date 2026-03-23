# Story 4.3: Roll Out Distributed Coordination Incrementally

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/platform engineer,
I want distributed coordination guarded by feature flag rollout controls,
so that production risk is minimized during activation.

**Implements:** FR48

## Acceptance Criteria

1. **Given** distributed coordination feature flag is disabled (default)
   **When** hot-path cycles execute
   **Then** behavior matches prior single-instance-compatible execution semantics
   **And** no coordination lock or shard lease operations are performed.

2. **Given** feature flag is enabled in controlled environments
   **When** rollout verification runs
   **Then** lock/yield/fail-open behaviors are observable and documented for operators
   **And** enablement can be reversed without data migration or schema changes.

## Tasks / Subtasks

- [x] Task 1: Add rollout flag-combination unit tests (AC: 1, 2)
  - [x] Add `tests/unit/coordination/test_rollout_flags.py` — verify that when `DISTRIBUTED_CYCLE_LOCK_ENABLED=False` and `SHARD_REGISTRY_ENABLED=False`, the scheduler performs zero Redis lock/shard calls (use call-recording fake Redis).
  - [x] Add test: `DISTRIBUTED_CYCLE_LOCK_ENABLED=True`, `SHARD_REGISTRY_ENABLED=False` → cycle lock metrics emitted, no shard checkpoint calls.
  - [x] Add test: both flags true → cycle lock and shard coordination both active.
  - [x] Add test: flag disabled after being enabled produces settings with default `False` and no validator errors.
  - [x] Extend `tests/unit/config/test_settings.py` with `SHARD_REGISTRY_ENABLED` default, validation, and `log_active_config` inclusion tests.

- [x] Task 2: Add rollout statelessness integration test (AC: 2)
  - [x] Add `tests/integration/coordination/test_coordination_rollout.py` using real Redis (testcontainers).
  - [x] Test: flags-off produces zero Redis coordination keys (`SCAN aiops:lock:*` and `SCAN aiops:shard:*` return empty after cycle execution).
  - [x] Test: flags-on then flags-off and cycle runs again → Redis keys from prior enabled cycle expire naturally; no manual cleanup required.
  - [x] Prerequisite enforcement: use `pytest.fail` (not `pytest.skip`) if Docker is unavailable.

- [x] Task 3: Add `SHARD_REGISTRY_ENABLED` to startup configuration logging (AC: 2)
  - [x] Verify `log_active_config` in `config/settings.py` includes `SHARD_REGISTRY_ENABLED`.
  - [x] If 4.2 did not add it, add it alongside `DISTRIBUTED_CYCLE_LOCK_ENABLED` (line ~231 of settings.py).
  - [x] Ensure `log_active_config` logs both flags together so operators can see the full coordination state in a single startup log event.

- [x] Task 4: Update operator rollout documentation (AC: 2)
  - [x] Update `docs/deployment-guide.md` with a "Distributed Coordination Rollout" section covering:
    - Phase 0 (default): both flags false, single-instance semantics, no Redis coordination keys written.
    - Phase 1: enable `DISTRIBUTED_CYCLE_LOCK_ENABLED=true`, verify `aiops.coordination.cycle_lock_acquired` / `cycle_lock_yielded` OTLP counters appear.
    - Phase 2: enable `SHARD_REGISTRY_ENABLED=true`, verify `aiops.coordination.shard_checkpoint_*` OTLP counters appear.
    - Rollback: set flag back to false; no Redis data migration or `DEL` commands needed; existing keys expire via TTL.
  - [x] Update `docs/runtime-modes.md` with coordination-state per mode table (flags off → single-instance, flags on → coordinated).
  - [x] Update `README.md` feature flag reference table to include both `DISTRIBUTED_CYCLE_LOCK_ENABLED` and `SHARD_REGISTRY_ENABLED` with their default values, scope, and recommended rollout order.

- [x] Task 5: Validate flag independence and reversibility in scheduler unit tests (AC: 1, 2)
  - [x] Extend `tests/unit/pipeline/test_scheduler.py`: when `DISTRIBUTED_CYCLE_LOCK_ENABLED=False`, scheduler executes cycle with zero interaction with the cycle lock object (assert no acquire/yield calls).
  - [x] Extend `tests/unit/pipeline/test_scheduler.py`: when `SHARD_REGISTRY_ENABLED=False` (even if shard coordinator is wired), scheduler does not invoke shard assignment.
  - [x] Confirm both flags can be independently toggled without affecting each other's code paths.

- [x] Task 6: Run full regression to confirm zero skipped tests and no regressions (AC: 1, 2)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q tests/unit`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### Developer Context Section

- Story 4.1 (done) implemented `coordination/cycle_lock.py`, `DISTRIBUTED_CYCLE_LOCK_ENABLED` (default `False`), coordination metrics, and integration tests. The feature flag is **already wired** in `__main__.py` and `scheduler.py`.
- Story 4.2 (in-progress before this story) implemented `coordination/shard_registry.py`, `SHARD_REGISTRY_ENABLED`, shard lease/checkpoint primitives, shard metrics, and integration tests.
- Story 4.3 does NOT re-implement either coordination mechanism. It adds rollout-safety tests, operator docs, and verifies that both flags operate independently and statelessly.
- **Critical constraint**: this story is purely additive — no changes to `cycle_lock.py`, `shard_registry.py`, or their protocol contracts.
- **The central invariant for this story**: `flag=False` must produce zero Redis coordination side effects. Tests must assert this, not just imply it.

### Technical Requirements

- FR48: The system can enable distributed coordination incrementally via feature flag (`DISTRIBUTED_CYCLE_LOCK_ENABLED`, default false).
- NFR-SC1: hot/hot deployments avoid duplicate dispatch — verified at each rollout phase via OTLP counters.
- NFR-R4: cycle lock fails open on Redis unavailability — documented in rollout guide as a safety property operators rely on.
- NFR-R7: degradable dependency failures update HealthRegistry, emit degraded events, and continue — explicitly mentioned in rollout phase 1 verification steps.
- NFR-A6: pod identity logged per-replica — operators use this to confirm which pod holds the lock via structured logs.
- The rollout must be reversible: `flag=False` is the complete rollback. No Redis `DEL`, no schema migration, no restart coordination.

### Architecture Compliance

- D1: Redis keys for coordination are `aiops:lock:cycle` (cycle lock) and `aiops:shard:checkpoint:{shard_id}:{interval}` (shard lease). SCAN patterns to verify empty state: `SCAN aiops:lock:*` and `SCAN aiops:shard:*`.
- D2: Redis is ephemeral — keys expire naturally via TTL. Rollback = set flag false; existing TTL-bounded keys drain automatically.
- D3: shard checkpoint failure degrades to full-scope fallback with HealthRegistry update (not halt) — this is the safety net, not the rollout mechanism.
- D5: `DISTRIBUTED_CYCLE_LOCK_ENABLED` default false, feature-flagged via `SET NX EX`. No explicit unlock. TTL expiry is the rollback mechanism between cycles.
- D11-D12: `SHARD_REGISTRY_ENABLED` default false, feature-flagged shard coordination. Flags are independent (cycle lock and shard can be enabled separately).
- D13: shared Redis connection pool in `__main__.py` — rollout tests must not create additional pools.

### Library / Framework Requirements

- Locked stack (do not change):
  - Python `>=3.13`
  - `redis==7.2.1` (repo pin) — PyPI latest is `7.3.0` (2026-03-06); stay on repo pin
  - `pytest==9.0.2`
  - `testcontainers==4.14.1`
- Integration tests use testcontainers Redis — ensure `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock` is in the regression command.
- Unit tests use per-file call-recording fake Redis (no shared fixture, per implementation patterns).

### File Structure Requirements

Primary implementation targets:
- `src/aiops_triage_pipeline/config/settings.py` — add `SHARD_REGISTRY_ENABLED` to `log_active_config` (if missing after 4.2)
- `tests/unit/coordination/test_rollout_flags.py` (new) — flag-combination unit tests
- `tests/unit/config/test_settings.py` — extend with `SHARD_REGISTRY_ENABLED` settings tests
- `tests/unit/pipeline/test_scheduler.py` — extend with flag-independence assertions
- `tests/integration/coordination/test_coordination_rollout.py` (new) — stateless rollout integration test

Documentation targets:
- `docs/deployment-guide.md` — add rollout section (phase 0/1/2 + rollback)
- `docs/runtime-modes.md` — coordination-state per mode
- `README.md` — feature flag table

Do NOT create new source packages. Do NOT modify `coordination/cycle_lock.py` or `coordination/shard_registry.py`.

### Testing Requirements

- Unit tests must verify:
  - `DISTRIBUTED_CYCLE_LOCK_ENABLED=False` → zero Redis lock calls in scheduler execution path.
  - `SHARD_REGISTRY_ENABLED=False` → zero shard coordinator calls in scheduler execution path.
  - Both flags independently togglable (enabling one does not silently enable the other).
  - `SHARD_REGISTRY_ENABLED` defaults to `False`, validates correctly, appears in `log_active_config`.
- Integration tests must verify:
  - With both flags false, no coordination keys written to Redis after a full cycle execution.
  - Flags can be toggled off after being on; subsequent cycle execution produces no new coordination keys.
  - `pytest.fail` (NOT `pytest.skip`) on missing Docker prerequisites — zero skipped tests quality gate.
- Preferred full regression command:
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Quality gate: zero skipped tests across all test suites.

### Previous Story Intelligence

**From Story 4.1 (cycle lock):**
- `DISTRIBUTED_CYCLE_LOCK_ENABLED` is already in `settings.py` (line 104) and `log_active_config` (line 231). Do not duplicate.
- `CYCLE_LOCK_MARGIN_SECONDS` validator (`> 0`) is already wired in the `validate_kerberos_files` validator (lines 175-176). Follow the same pattern for any new `SHARD_REGISTRY_ENABLED` validation needed.
- Integration test pattern from `test_cycle_lock_contention.py`: use `pytest.fail` for missing Docker; session-scoped Redis container; no `pytest.skip`.
- `coordination/protocol.py` houses the protocol types; any new outcome types for 4.2 will follow the same pattern.

**From Story 4.2 (shard coordination, in-progress):**
- `SHARD_REGISTRY_ENABLED: bool = False` will be added to `settings.py` by 4.2. Story 4.3 must add it to `log_active_config` if 4.2 did not.
- `coordination/shard_registry.py` is the shard module — import from there for type checks in tests, but do not modify it.
- Shard metrics are in `health/metrics.py` — story 4.3 references metric names for doc verification but does not add new metrics.
- Integration tests in `tests/integration/coordination/` already use a shared conftest Redis fixture — extend there, do not create a new conftest.

**Review feedback patterns from 4.1 (apply to 4.3):**
- Integration tests that used `pytest.skip` were changed to `pytest.fail` during review — use `pytest.fail` from the start.
- File list in Dev Agent Record must include ALL changed files (including test artifacts, docs, sprint-status.yaml).
- Lock cycle_lock.py: added `ValueError` for non-positive `interval_seconds`. For 4.3, validate any new settings fields (e.g., `SHARD_LEASE_TTL_SECONDS` if added) similarly.

### Git Intelligence Summary

Recent commit context:
- `3447ce6`: Story 4.1 touched `__main__.py`, `config/settings.py`, `coordination/`, `health/metrics.py`, docs (deployment-guide, runtime-modes, README), and targeted unit/integration tests.
- Doc updates and test updates always landed in the same commit as implementation.
- `tests/unit/coordination/` directory created in 4.1 with `__init__.py`; extend it without adding another `__init__.py`.
- `tests/integration/coordination/` created in 4.1 — add `test_coordination_rollout.py` there (sibling of `test_cycle_lock_contention.py`).

### Latest Tech Information

External verification date: 2026-03-23.

- `redis` (redis-py) latest PyPI is `7.3.0` (released 2026-03-06); repo pin is `7.2.1`. No upgrade in this story.
- `SCAN` command in redis-py 7.2.1: `redis_client.scan_iter("aiops:lock:*")` returns an iterator; `list(redis_client.scan_iter("aiops:lock:*"))` produces a list for assertion. Redis SCAN guarantees eventual consistency — in tests, use `redis_client.flushdb()` for clean-slate assertions rather than relying on SCAN-count ordering.
- `testcontainers==4.14.1`: Redis container started with `RedisContainer()` and `get_client()` — same pattern as `test_cycle_lock_contention.py` (already in the test suite).

### Project Context Reference

Applied `archive/project-context.md` and implementation patterns:
- Python 3.13 typing and frozen contract discipline.
- Composition-root wiring in `__main__.py`; no service locator / DI container.
- Single flat `Settings` class — no new settings sub-classes for this story.
- Feature flags follow `FEATURE_ENABLED: bool = False` pattern (no `AIOPS_` prefix).
- Full regression policy expects zero skipped tests.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 4 / Story 4.3]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR48]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-SC1, NFR-R4, NFR-R7, NFR-A6]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D1, D2, D3, D5, D11, D12, D13]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/implementation-artifacts/4-1-add-distributed-cycle-lock-with-fail-open-behavior.md`]
- [Source: `artifact/implementation-artifacts/4-2-coordinate-scope-shards-and-recover-from-pod-failure.md`]
- [Source: `src/aiops_triage_pipeline/config/settings.py` — lines 104-105, 231-232 (existing flag wiring)]
- [Source: `src/aiops_triage_pipeline/coordination/cycle_lock.py`]
- [Source: `src/aiops_triage_pipeline/coordination/protocol.py`]
- [Source: `src/aiops_triage_pipeline/health/metrics.py`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `tests/unit/coordination/test_cycle_lock.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: `tests/unit/config/test_settings.py`]
- [Source: `tests/integration/coordination/test_cycle_lock_contention.py`]
- [Source: `tests/integration/conftest.py`]
- [Source: `https://pypi.org/project/redis/`]
- [Source: `https://redis.io/docs/latest/commands/scan/`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- create-story workflow execution for auto-discovered story key `4-3-roll-out-distributed-coordination-incrementally`
- artifact analysis: sprint-status (auto-discovery), epics.md (epic 4 full context), architecture shards (core-architectural-decisions, implementation-patterns-consistency-rules, project-structure-boundaries), PRD functional/non-functional requirements
- previous story analysis: 4-1 (done), 4-2 (in-progress) — both loaded for forward/backward context
- source code analysis: `settings.py` (confirmed `DISTRIBUTED_CYCLE_LOCK_ENABLED` at line 104, `log_active_config` at line 231), `coordination/` package (cycle_lock, protocol, __init__), ATDD test 4.2 (confirmed `shard_registry` module target)
- latest-tech verification: redis-py 7.3.0 PyPI (repo stays at 7.2.1), SCAN command docs

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- Story scoped to rollout safety validation and documentation; no coordination primitive changes.
- All file targets verified against existing project structure and previous story patterns.
- Task 1: `tests/unit/coordination/test_rollout_flags.py` created with 4 flag-combination tests using call-recording fake Redis; verified zero Redis calls when both flags disabled.
- Task 1 (settings): `test_log_active_config_includes_shard_registry_enabled` added to `tests/unit/config/test_settings.py`; confirmed `SHARD_REGISTRY_ENABLED` was already in `log_active_config` (added by 4.2 at settings.py:247).
- Task 2: `tests/integration/coordination/test_coordination_rollout.py` created; 2 tests using real Redis via testcontainers; `pytest.fail` used for Docker prereq enforcement.
- Task 3: Verified `SHARD_REGISTRY_ENABLED` already present in `log_active_config` (settings.py line 247) — no source change required.
- Task 4: `docs/deployment-guide.md` updated with "Distributed Coordination Rollout" section (Phase 0/1/2 + rollback). `docs/runtime-modes.md` updated with coordination-state per flag combination table. `README.md` feature flag table updated with scope and recommended rollout order columns.
- Task 5: 5 flag-independence tests added to `tests/unit/pipeline/test_scheduler.py` using `_RecordingCycleLock` and `_RecordingShardCoordinator` fake objects.
- Task 6: `ruff check` clean (1 pre-existing atdd E501 unrelated to this story). `pytest -q tests/unit` → 1017 passed. Full regression → 1113 passed, 0 skipped, 0 failed.

### File List

- `artifact/implementation-artifacts/4-3-roll-out-distributed-coordination-incrementally.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `tests/unit/coordination/test_rollout_flags.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/unit/test_main.py`
- `tests/integration/coordination/test_coordination_rollout.py`
- `docs/deployment-guide.md`
- `docs/runtime-modes.md`
- `README.md`

### Story Completion Status

- Story status: `review`
- Completion note: `All tasks complete — flag-combination unit tests, stateless rollout integration tests, operator docs, and flag-independence scheduler tests implemented. Code review applied fixes: H1 integration test now exercises real coordination primitives; H2 shard gate tests added to test_main.py; M1 OTLP metric assertion added; M2 TTL margin increased; L1 fixture scope fixed to session; L2 false/true flag combination test added.`
