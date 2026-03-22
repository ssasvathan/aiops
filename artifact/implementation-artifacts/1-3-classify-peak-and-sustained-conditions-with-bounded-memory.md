# Story 1.3: Classify Peak and Sustained Conditions with Bounded Memory

Status: done

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

- [x] Task 1: Finalize deterministic peak classification from cached/computed profiles (AC: 1)
  - [x] Ensure `run_peak_stage_cycle` and `collect_peak_stage_output` classify to `PEAK|NEAR_PEAK|OFF_PEAK` whenever required evidence is present.
  - [x] Keep `UNKNOWN` only for evidence-insufficient or profile-missing cases and preserve reason-code semantics.
  - [x] Confirm cached profile reuse has precedence over recompute when valid cached data exists.

- [x] Task 2: Parallelize sustained-status computation for large key sets (AC: 2)
  - [x] Introduce bounded parallel execution for sustained key evaluation (deterministic ordering preserved for output maps).
  - [x] Add explicit configuration knobs for sustained parallelism (for example worker count/chunk size) with safe defaults.
  - [x] Keep behavior equivalent to current serial logic for small input sizes and degraded modes.

- [x] Task 3: Implement bounded in-process peak history retention (AC: 2)
  - [x] Maintain per-scope bounded history windows (fixed max depth) instead of unbounded growth.
  - [x] Evict stale scopes predictably to cap process memory footprint.
  - [x] Ensure bounded-history settings are configurable and validated at startup.

- [x] Task 4: Preserve Redis-backed sustained continuity and degradation rules (AC: 1, 2)
  - [x] Keep sustained state source-of-truth in Redis with best-effort load/persist behavior.
  - [x] Preserve D3 degradation posture: sustained fallback to `None`, peak fallback to `UNKNOWN`, no hot-path halt for cache consumer failures.
  - [x] Maintain D1 key conventions and existing legacy-fallback read behavior for rolling compatibility.

- [x] Task 5: Add observability for performance and memory guardrails (AC: 2)
  - [x] Add metrics for sustained compute duration, key count processed, and bounded-history size/eviction signals.
  - [x] Emit structured warnings when retention caps are hit or parallel execution falls back to serial mode.

- [x] Task 6: Expand tests and execute full quality gates (AC: 1, 2)
  - [x] Add/extend unit tests for peak classification boundaries, unknown-evidence behavior, and deterministic outcomes.
  - [x] Add/extend unit tests for sustained parallel execution equivalence vs serial baseline.
  - [x] Add/extend tests for bounded-memory retention limits and eviction semantics.
  - [x] Run lint and full regression with zero skipped tests.

### Review Follow-ups (AI)

- [x] [AI-Review][MEDIUM] Reject stale or incompatible cached peak profiles before classification so thresholding does not run on outdated cache state. [src/aiops_triage_pipeline/pipeline/stages/peak.py]
- [x] [AI-Review][MEDIUM] Ensure retention idle-cycle eviction still progresses during empty-scope cycles by advancing retention state on empty baseline loads. [src/aiops_triage_pipeline/__main__.py]
- [x] [AI-Review][MEDIUM] Prevent active-scope churn under scope-cap pressure by skipping over-cap scopes when all retained scopes are active in the same cycle. [src/aiops_triage_pipeline/__main__.py]
- [x] [AI-Review][LOW] Include exception context when parallel sustained computation falls back to serial execution for operability/debugging. [src/aiops_triage_pipeline/pipeline/stages/peak.py]

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

- Implemented bounded sustained-status parallelization controls in Stage 2 with deterministic chunked execution and serial fallback warnings.
- Added bounded in-process peak-history retention in hot-path scheduler loop with scope-cap/staleness eviction and metric emissions.
- Added Stage 2 parallel/retention settings with validation and startup logging.
- Added telemetry for sustained compute duration/key count and peak-history scope/evictions.
- Applied code-review fixes for stale cached-profile rejection, empty-cycle retention progression, scope-cap churn prevention, and fallback exception logging.
- Validation executed:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Completed deterministic cached-profile precedence validation for Stage 2 classification and kept UNKNOWN semantics constrained to missing evidence/profile cases.
- Parallelized sustained-status evaluation with bounded worker/chunk controls and deterministic output ordering.
- Added bounded in-process peak-history retention (depth/scopes/idle-cycle limits) with predictable eviction behavior.
- Preserved Redis sustained continuity and degraded-mode handling while keeping existing D1 key behaviors unchanged.
- Added observability for sustained compute and retention memory guardrails, including fallback/cap warning events.
- Resolved review findings by enforcing cached-profile freshness checks, keeping retention eviction active on empty cycles, and eliminating active-scope cap churn.
- Full lint and regression gates passed with zero skipped tests (`849 passed`, `0 skipped`).

### File List

- artifact/implementation-artifacts/1-3-classify-peak-and-sustained-conditions-with-bounded-memory.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/__main__.py
- src/aiops_triage_pipeline/config/settings.py
- src/aiops_triage_pipeline/health/metrics.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- src/aiops_triage_pipeline/pipeline/stages/peak.py
- tests/unit/config/test_settings.py
- tests/unit/health/test_metrics.py
- tests/unit/pipeline/stages/test_peak.py
- tests/unit/test_main.py

## Story Completion Status

- Story status: `done`
- Completion note: Story 1.3 implementation and adversarial review fixes are complete; cached-profile validity and retention edge cases are covered by tests and full quality gates pass with zero skips.

## Senior Developer Review (AI)

- Review date: 2026-03-22
- Outcome: Approved after fixes
- Findings addressed:
  - [x] Stale/incompatible cached peak profiles are rejected before use.
  - [x] Retention aging/eviction now advances during empty-scope cycles.
  - [x] Scope-cap handling no longer evicts currently active scopes in-cycle when capacity is saturated.
  - [x] Parallel fallback warning now includes exception context (`exc_info=True`).
- Verification:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - Result: `849 passed`, `0 skipped`

## Change Log

- 2026-03-22: Story created via create-story workflow with exhaustive artifact and code-context analysis; status set to ready-for-dev.
- 2026-03-22: Implemented Story 1.3 changes for Stage 2 sustained parallelization controls, bounded peak-history retention, and observability updates.
- 2026-03-22: Added/updated unit tests for parallel sustained equivalence, cached-profile precedence, retention bounds, settings validation, and metrics instrumentation.
- 2026-03-22: Ran lint and full Docker-enabled regression suite; all tests passed with zero skipped and story moved to review.
- 2026-03-22: Resolved all review findings, revalidated with full zero-skip regression gate, and updated story/sprint status to done.
