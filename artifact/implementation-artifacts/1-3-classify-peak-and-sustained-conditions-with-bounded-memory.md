# Story 1.3: Classify Peak and Sustained Conditions with Bounded Memory

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want peak-window and sustained-anomaly classification to be accurate and efficient,
so that severity decisions reflect real conditions without memory or latency regression.

**Implements:** FR8, FR9, FR10, FR11

## Acceptance Criteria

1. **Given** cached peak profile data is available
   **When** anomaly findings are evaluated
   **Then** each scope is classified as `PEAK`, `NEAR_PEAK`, or `OFF_PEAK`
   **And** the previous always-`UNKNOWN` peak behavior is removed.

2. **Given** large scope sets are processed
   **When** sustained status is computed
   **Then** sustained evaluation is parallelized
   **And** peak-profile retention is bounded to a configurable limit that constrains memory growth.

## Tasks / Subtasks

- [ ] Task 1: Finalize deterministic peak classification from cached/computed profiles (AC: 1)
  - [ ] Ensure `run_peak_stage_cycle` and `collect_peak_stage_output` classify to `PEAK|NEAR_PEAK|OFF_PEAK` whenever required evidence is present.
  - [ ] Keep `UNKNOWN` only for evidence-insufficient or profile-missing cases and preserve reason-code semantics.
  - [ ] Confirm cached profile reuse has precedence over recompute when valid cached data exists.

- [ ] Task 2: Parallelize sustained-status computation for large key sets (AC: 2)
  - [ ] Introduce bounded parallel execution for sustained key evaluation (deterministic ordering preserved for output maps).
  - [ ] Add explicit configuration knobs for sustained parallelism (for example worker count/chunk size) with safe defaults.
  - [ ] Keep behavior equivalent to current serial logic for small input sizes and degraded modes.

- [ ] Task 3: Implement bounded in-process peak history retention (AC: 2)
  - [ ] Maintain per-scope bounded history windows (fixed max depth) instead of unbounded growth.
  - [ ] Evict stale scopes predictably to cap process memory footprint.
  - [ ] Ensure bounded-history settings are configurable and validated at startup.

- [ ] Task 4: Preserve Redis-backed sustained continuity and degradation rules (AC: 1, 2)
  - [ ] Keep sustained state source-of-truth in Redis with best-effort load/persist behavior.
  - [ ] Preserve D3 degradation posture: sustained fallback to `None`, peak fallback to `UNKNOWN`, no hot-path halt for cache consumer failures.
  - [ ] Maintain D1 key conventions and existing legacy-fallback read behavior for rolling compatibility.

- [ ] Task 5: Add observability for performance and memory guardrails (AC: 2)
  - [ ] Add metrics for sustained compute duration, key count processed, and bounded-history size/eviction signals.
  - [ ] Emit structured warnings when retention caps are hit or parallel execution falls back to serial mode.

- [ ] Task 6: Expand tests and execute full quality gates (AC: 1, 2)
  - [ ] Add/extend unit tests for peak classification boundaries, unknown-evidence behavior, and deterministic outcomes.
  - [ ] Add/extend unit tests for sustained parallel execution equivalence vs serial baseline.
  - [ ] Add/extend tests for bounded-memory retention limits and eviction semantics.
  - [ ] Run lint and full regression with zero skipped tests.

## Dev Notes

### Developer Context Section

- Story 1.3 is the first explicit performance-and-memory hardening step for Stage 2 classification in Epic 1.
- Story 1.2 already established Redis-backed sustained state continuity and batched cache retrieval; Story 1.3 must build on that baseline without regressions.
- Current code already classifies peak windows and sustained streaks, but sustained evaluation is serial and memory-retention controls are not explicitly bounded/configurable for large scope growth.
- The deliverable focus is production-safe behavior under scale: deterministic classification, bounded memory, and measurable sustained-compute performance.
- Do not introduce cold-path or integration-boundary changes in this story.

### Technical Requirements

- FR8: Classify anomaly patterns as `PEAK`, `NEAR_PEAK`, `OFF_PEAK` using cached profiles and baseline-derived fallback profiles.
- FR9: Compute sustained status from externalized Redis state shared by all hot-path replicas.
- FR10: Parallelize sustained status computation for large key sets while preserving deterministic output ordering.
- FR11: Bound per-process memory growth for peak history/retention with configurable limits.
- NFR-P6: Sustained status computation should complete within 50% of scheduler interval for large scope sets.
- NFR-P7: Peak-profile historical memory must be bounded by configurable retention depth.
- UNKNOWN handling remains explicit end-to-end; never coerce missing evidence to PRESENT/zero.

### Architecture Compliance

- D1: Preserve Redis namespace convention (`aiops:{data_type}:{scope_key}`) for any added keys.
- D2: Redis remains ephemeral accelerator; correctness must not depend on Redis persistence.
- D3: Preserve degradation matrix behavior:
  - sustained state unavailable -> fallback `None` (conservative)
  - peak profile cache unavailable -> classification can be `UNKNOWN`
  - cache-read failures warn and continue (no hot-path halt)
- D13: Reuse shared Redis connection/client from composition root (`__main__.py`), no per-module pools.
- Keep stage order and gating contract semantics unchanged.
- Keep hot/cold path isolation unchanged.

### Library / Framework Requirements

- Keep project-pinned runtime versions for implementation unless explicitly scoped for upgrade:
  - Python >=3.13
  - redis==7.2.1
  - pydantic==2.12.5
  - pydantic-settings~=2.13.1
  - SQLAlchemy==2.0.47
  - confluent-kafka==2.13.0
- Upstream snapshot (2026-03-22) for awareness only:
  - redis 7.3.0
  - SQLAlchemy 2.0.48
  - confluent-kafka 2.13.2
- Implement this story against current locked stack; do not bundle dependency upgrades into Story 1.3.

### Project Structure Notes

- Primary code targets:
  - `src/aiops_triage_pipeline/pipeline/stages/peak.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/cache/evidence_window.py`
  - `src/aiops_triage_pipeline/cache/peak_cache.py`
  - `src/aiops_triage_pipeline/config/settings.py` (if introducing bounded-memory/parallelism settings)
  - `src/aiops_triage_pipeline/health/metrics.py` (new metrics)
- Optional contract/policy updates if retention settings become policy-driven:
  - `src/aiops_triage_pipeline/contracts/peak_policy.py`
  - `config/policies/peak-policy-v1.yaml`
- Primary tests to extend:
  - `tests/unit/pipeline/stages/test_peak.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/cache/test_evidence_window.py`
  - `tests/unit/cache/test_peak_cache.py`

### Testing Requirements

- Required tests:
  - peak classification boundaries (`PEAK`, `NEAR_PEAK`, `OFF_PEAK`) and UNKNOWN fallback correctness.
  - sustained parallel evaluation correctness vs serial-equivalent baseline on identical inputs.
  - deterministic ordering guarantees under parallel execution.
  - bounded-memory retention behavior (max depth, eviction, stale-scope cleanup).
  - Redis degradation behavior unchanged for sustained/peak cache paths.
- Required quality-gate commands:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Sprint gate remains strict: 0 skipped tests.

### Previous Story Intelligence

- Story 1.2 introduced Redis-backed sustained persistence, baseline persistence/reuse, and batched cache retrieval.
- Review fixes in Story 1.2 addressed two critical continuity gaps:
  - sustained identity-key candidate expansion in `__main__.py` to avoid streak loss between cycles.
  - peak baseline bootstrap from persisted Redis baselines when cached profiles are missing.
- Story 1.3 must not regress these fixes; new parallelization/memory logic must preserve sustained continuity semantics.
- Continue using warning-only behavior for cache consumer failures.

### Git Intelligence Summary

- Recent commit pattern shows effective sequence: story context -> implementation -> review-driven corrections -> sprint status sync.
- Highest-impact files changed in recent work:
  - `src/aiops_triage_pipeline/__main__.py`
  - `src/aiops_triage_pipeline/pipeline/stages/peak.py`
  - `src/aiops_triage_pipeline/cache/evidence_window.py`
  - `src/aiops_triage_pipeline/cache/peak_cache.py`
  - `tests/unit/pipeline/test_scheduler.py`
- Actionable guidance for Story 1.3:
  - keep changes localized to Stage 2/scheduler/cache + tests.
  - preserve existing reason-code semantics and regression expectations from current unit tests.
  - prioritize deterministic behavior and observability when adding parallel execution.

### Latest Tech Information

- Snapshot date: 2026-03-22.
- PyPI latest versions:
  - `redis`: 7.3.0
  - `pydantic`: 2.12.5
  - `pydantic-settings`: 2.13.1
  - `pytest`: 9.0.2
  - `SQLAlchemy`: 2.0.48
  - `confluent-kafka`: 2.13.2
- Relevant official docs to apply in implementation choices:
  - Python `asyncio.to_thread` usage for safely offloading blocking work.
  - Python `collections.deque(maxlen=...)` for bounded in-memory retention.
  - Redis `MGET` behavior/complexity for batched read planning.
- Decision for this story: stay on pinned versions and apply best practices compatible with the locked stack.

### Project Context Reference

- Loaded and applied `archive/project-context.md` rules:
  - Python 3.13 typing style and immutable contracts.
  - config module remains a generic leaf (no contract-specific imports in settings loader).
  - structured logging/health primitives are reused (no parallel enforcement frameworks).
  - critical invariants fail loud; degradable dependencies continue with explicit degraded posture.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Epic 1, Story 1.3]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` - FR8, FR9, FR10, FR11]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-P6, NFR-P7, NFR-SC4, NFR-R5]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` - UNKNOWN propagation, degraded mode]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` - D1, D2, D3, D13]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/implementation-artifacts/1-2-persist-and-reuse-redis-baselines-and-state-in-bulk.md`]
- [Source: `artifact/implementation-artifacts/sprint-status.yaml`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/peak.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/cache/evidence_window.py`]
- [Source: `src/aiops_triage_pipeline/cache/peak_cache.py`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `tests/unit/pipeline/stages/test_peak.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: `tests/unit/cache/test_evidence_window.py`]
- [Source: `tests/unit/cache/test_peak_cache.py`]
- [Source: `archive/project-context.md`]
- [Source: https://pypi.org/project/redis/7.3.0/]
- [Source: https://pypi.org/project/pydantic/2.12.5/]
- [Source: https://pypi.org/project/pydantic-settings/2.13.1/]
- [Source: https://pypi.org/project/pytest/9.0.2/]
- [Source: https://pypi.org/project/SQLAlchemy/2.0.48/]
- [Source: https://pypi.org/project/confluent-kafka/2.13.2/]
- [Source: https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread]
- [Source: https://docs.python.org/3/library/collections.html#collections.deque]
- [Source: https://redis.io/docs/latest/commands/mget/]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Story context generated from planning artifacts, architecture shards, current codebase, prior story, and recent commit history.
- Validation checklist reviewed manually (workflow validator task file not present in `_bmad/core/tasks`).

### Completion Notes List

- Story context created for FR8/FR9/FR10/FR11 with explicit implementation guardrails.
- Story status prepared for handoff to `dev-story`.

### File List

- artifact/implementation-artifacts/1-3-classify-peak-and-sustained-conditions-with-bounded-memory.md
- artifact/implementation-artifacts/sprint-status.yaml

## Story Completion Status

- Story status: `ready-for-dev`
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created.

## Change Log

- 2026-03-22: Story created via create-story workflow with exhaustive artifact and code-context analysis; status set to ready-for-dev.
