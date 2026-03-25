# Story 2.6: Redis Evidence Caching

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want evidence windows, peak profiles, and per-interval findings cached in Redis with environment-specific TTLs,
so that repeated computations are avoided and cache behavior follows redis-ttl-policy-v1 (FR7).

## Acceptance Criteria

1. **Given** Redis is available and configured  
   **When** evidence, peak profiles, or findings are computed  
   **Then** results are cached in Redis using the key design: `evidence:{key}`, `peak:{key}`.

2. **And** TTLs are set per environment as defined in redis-ttl-policy-v1.

3. **And** cache hits return previously computed results without re-querying Prometheus.

4. **And** cache misses trigger fresh computation and cache population.

5. **And** cached data is treated as cache-only (not system-of-record) and loss of Redis data is recoverable.

6. **And** unit tests verify: cache write/read round-trip, TTL expiration behavior, cache miss triggers computation.

## Tasks / Subtasks

- [x] Task 1: Align Redis key namespaces to architecture-required prefixes (AC: 1)
  - [x] Ensure evidence-window cache keys use `evidence:{key}` namespace (not ad-hoc prefixes).
  - [x] Keep peak-profile cache keys in `peak:{key}` namespace.
  - [x] Add a compatibility read path for legacy keys if needed to avoid immediate regression during rollout.

- [x] Task 2: Enforce environment-specific TTL policy usage for all FR7 cache writes (AC: 2)
  - [x] Keep peak-profile TTL sourced from `ttls_by_env.<env>.peak_profile_seconds`.
  - [x] Keep evidence-window TTL sourced from `ttls_by_env.<env>.evidence_window_seconds`.
  - [x] Define per-interval findings TTL using existing redis-ttl-policy-v1 fields without introducing unvalidated config.

- [x] Task 3: Implement read-through behavior for per-interval findings cache (AC: 3, 4)
  - [x] Add a deterministic findings cache key strategy scoped by `(env, cluster_id, scope, evaluation interval)`.
  - [x] On cache hit: reuse cached finding payload and skip duplicate computation paths.
  - [x] On cache miss: compute findings, persist to cache, and return computed value.

- [x] Task 4: Preserve cache-only semantics and degraded behavior (AC: 5)
  - [x] Treat Redis read/write failures as best-effort warnings in this stage, not hard pipeline failures.
  - [x] Do not promote Redis cache contents to authoritative state.
  - [x] Ensure existing UNKNOWN propagation and scheduler cadence behavior remain unchanged when cache is unavailable.

- [x] Task 5: Add/adjust tests for FR7 behavior (AC: 6)
  - [x] Unit tests for key format, TTL selection, deterministic serialization, and read-through hit/miss behavior.
  - [x] Unit tests for fallback behavior under Redis read/write exceptions.
  - [x] Scheduler/integration tests proving cache hit avoids redundant computation where applicable.

- [x] Task 6: Quality gates
  - [x] Run focused cache tests and affected stage tests.
  - [x] Run full `uv run pytest -q` and `uv run ruff check` before review.

## Dev Notes

### Developer Context Section

- Story 2.6 is the FR7 performance and stability checkpoint for Epic 2.
- Existing cache helpers already exist in `cache/evidence_window.py` and `cache/peak_cache.py`; this story should extend and harden those patterns rather than creating parallel cache abstractions.
- Previous Story 2.5 introduced strict UNKNOWN propagation through Stage 1 -> Stage 2 -> Stage 6; cache integration must not dilute those semantics.
- Redis is explicitly cache-only and degradable in architecture; this story must not add any dependency that can halt hot-path evaluation when Redis fails.
- Keep implementation deterministic and scoped to caching behavior only; do not redesign anomaly logic, gate policy logic, or CaseFile durability in this story.

### Technical Requirements

- Use the frozen `RedisTtlPolicyV1` contract as the only source of truth for TTLs.
- Preserve deterministic payload serialization (`json.dumps(..., sort_keys=True, separators=(",", ":"))`) for cache values.
- Ensure key construction remains deterministic and scope-based to prevent collisions.
- Preserve read-through cache behavior for peak profiles and add equivalent behavior for per-interval findings.
- Keep evidence window / findings cache behavior aligned with 5-minute scheduler intervals and sustained-window key identity rules.
- Prefer Redis `SET key value EX seconds` style over deprecated command forms for any new write paths; do not introduce deprecated command usage.
- Ensure no cache write path bypasses env-specific TTL derivation.

### Architecture Compliance

- Enforce architecture key-prefix strategy:
  - `evidence:{key}` for evidence-window / per-interval evidence-derived payloads.
  - `peak:{key}` for peak profiles.
  - `dedupe:{key}` remains reserved for AG5 dedupe behavior (do not repurpose in this story).
- Keep Redis as degradable dependency: cache failures log warnings and continue processing.
- Maintain hot/cold path separation and non-blocking hot path.
- Keep policy/config loading generic (`load_policy_yaml`) and contract-first.
- Avoid introducing global mutable state or non-async-safe cache coordination.

### Library / Framework Requirements

- Python typing/style: keep project-standard Python 3.13 conventions.
- Pydantic v2 frozen models remain mandatory for contracts and stage outputs.
- redis-py usage must match project baseline and avoid deprecated command patterns in new code.
- Logging must use structured `event_type` fields via shared logger setup.
- Keep cache adapters protocol-driven for testability; avoid direct hard coupling to one Redis client implementation in stage logic.

### File Structure Requirements

- Primary files expected to change:
  - `src/aiops_triage_pipeline/cache/evidence_window.py`
  - `src/aiops_triage_pipeline/cache/peak_cache.py`
  - `src/aiops_triage_pipeline/cache/__init__.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py` (only if cache wiring requires stage orchestration updates)
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py` and/or `pipeline/stages/anomaly.py` for per-interval findings cache integration
- Primary test files expected to change/add:
  - `tests/unit/cache/test_evidence_window.py`
  - `tests/unit/cache/test_peak_cache.py`
  - `tests/unit/pipeline/stages/test_evidence.py`
  - `tests/unit/pipeline/stages/test_anomaly.py` (if findings cache hooks are introduced there)
  - `tests/unit/pipeline/test_scheduler.py` (if orchestration/cache-hit behavior is surfaced at scheduler level)

### Testing Requirements

- Unit tests must verify:
  - deterministic key format and namespace compliance.
  - env-specific TTL selection from redis-ttl-policy-v1.
  - read/write round-trip correctness for cached payloads.
  - read-through behavior (cache hit avoids recompute, cache miss triggers recompute and populate).
  - degraded behavior on Redis exceptions (warn-and-continue).
- Integration/scheduler coverage must verify:
  - cache behavior does not alter UNKNOWN propagation semantics.
  - cache behavior does not break wall-clock cadence processing.
  - cache loss/restart is recoverable (fresh computation path works end-to-end).
- Regression checks must include full unit suite and lint gates.

### Previous Story Intelligence

- Story 2.5 (UNKNOWN propagation) recently completed and hardened Stage 1/2/6 semantics.
- Preserve these behaviors while adding cache optimization:
  - `evidence_status_map_by_scope` is stage-derived truth and must remain unchanged by cache plumbing.
  - Sustained streak behavior around insufficient evidence and interval gaps is already regression-tested; caching must not bypass these checks.
- Recent implementation patterns in Epic 2:
  - narrow, stage-local changes
  - deterministic serialization for persisted artifacts
  - explicit warning-level logging on degradable dependency failures
  - focused + full test gate execution before status transitions

### Git Intelligence Summary

Recent commits (most recent first):
- `9e00864` `feat: propagate UNKNOWN evidence through peak and gating`
- `6efacc1` `Story 2.4: Code-review pass — 8 issues fixed, story marked done`
- `1ebaaba` `Story 2.3: Code-review pass — 9 issues fixed, story marked done`
- `84088d0` `Implement Story 2.3 peak classification, cache, and tests`
- `37843b2` `Story 2.2: Second code-review pass — detector hardening and model correctness`

Actionable implications for Story 2.6:
- Keep changes concentrated in `cache/` and stage wiring paths already used in Stories 2.3-2.5.
- Maintain deterministic models/contracts and avoid introducing mutable ad-hoc cache payloads.
- Expect code-review focus on regression safety and hidden behavior changes in scheduler/stage flow.

### Latest Tech Information

Verification date: **March 3, 2026**.

- **redis-py**:
  - Latest release visible on PyPI index: `7.1.1`.
  - Project baseline currently pins `redis==7.2.1`; confirm compatibility/availability assumptions before any dependency change in this story.
- **Redis command guidance**:
  - Redis command docs mark `SETEX` as deprecated in favor of `SET key value EX seconds`.
  - For any new cache write logic in Story 2.6, prefer non-deprecated command forms.
- **Pydantic**:
  - PyPI latest visible version: `2.12.5`.
  - No migration required for this story; keep current frozen-model approach.
- **pytest**:
  - PyPI latest visible version: `9.0.2`.
  - Existing test stack stays aligned; no test framework migration needed.

### Project Context Reference

Use `artifact/project-context.md` as a mandatory guardrail source, especially:
- Never collapse UNKNOWN semantics.
- Never bypass deterministic policy guardrails.
- Keep Redis degradable and non-fatal for hot-path processing.
- Preserve shared logging/health/contract patterns (no parallel abstractions).

### Story Completion Status

- Story context generation complete.
- Status set to `ready-for-dev`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created**.

## Project Structure Notes

- Reuse and extend existing `cache/` adapters and Stage 1/2 integration points.
- Do not create duplicate cache systems outside established modules.
- Keep namespace consistency explicit (`evidence:` and `peak:`) and document any temporary compatibility strategy for legacy keys.

## References

- [Source: `artifact/planning-artifacts/epics.md#Epic 2: Evidence Collection & Signal Validation`]
- [Source: `artifact/planning-artifacts/epics.md#Story 2.6: Redis Evidence Caching`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR7, FR34, FR51)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-R1, NFR-R2, NFR-T2, NFR-T4)]
- [Source: `artifact/planning-artifacts/architecture.md` (Redis key design, degradable dependency model, cache-only posture)]
- [Source: `artifact/project-context.md` (Critical Don't-Miss Rules, Framework Rules, Testing Rules)]
- [Source: `config/policies/redis-ttl-policy-v1.yaml`]
- [Source: `src/aiops_triage_pipeline/cache/evidence_window.py`]
- [Source: `src/aiops_triage_pipeline/cache/peak_cache.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/peak.py`]
- [Source: `https://pypi.org/project/redis/`]
- [Source: `https://redis.io/docs/latest/commands/setex/`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://pypi.org/project/pytest/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with `workflow-config=_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`.
- Story auto-selected from sprint backlog order: `2-6-redis-evidence-caching`.
- Discovery summary:
  - `epics_content`: loaded from `artifact/planning-artifacts/epics.md`
  - `architecture_content`: loaded from `artifact/planning-artifacts/architecture.md`
  - `prd_content`: selectively loaded from `artifact/planning-artifacts/prd/functional-requirements.md` and `artifact/planning-artifacts/prd/non-functional-requirements.md`
  - `ux_content`: not found
  - `project_context`: loaded from `artifact/project-context.md`
- Previous story intelligence loaded from `artifact/implementation-artifacts/2-5-unknown-evidence-propagation.md`.
- Git intelligence derived from last 5 commits.
- Latest package/command references reviewed on March 3, 2026.
- Note: invoke-task target `_bmad/core/tasks/validate-workflow.xml` is not present in this repository; manual checklist-based validation was applied.
- Implementation plan (executed): align Redis namespaces and TTL enforcement, add per-interval findings read-through cache, keep Redis failures warning-only, and verify via focused + full test gates.
- Validation gates executed:
  - `uv run pytest -q tests/unit/cache/test_evidence_window.py tests/unit/cache/test_peak_cache.py tests/unit/cache/test_findings_cache.py tests/unit/pipeline/stages/test_anomaly.py tests/unit/pipeline/stages/test_evidence.py tests/unit/pipeline/test_scheduler.py` (66 passed)
  - `uv run pytest -q` (246 passed)
  - `uv run ruff check` (all checks passed)

### Completion Notes List

- [x] Story context generated with exhaustive artifact grounding.
- [x] Status set to `ready-for-dev` in story file.
- [x] Implement story in `dev-story`.
- [x] Run `code-review` after implementation.
- [x] Updated evidence-window keys to `evidence:` namespace with legacy read fallback.
- [x] Updated peak cache writes to `SET ... EX` style (`set(..., ex=ttl)`).
- [x] Added per-interval findings cache adapter with deterministic keying and read-through behavior.
- [x] Added Redis read/write warning-only fallback behavior in read-through cache paths.
- [x] Added and updated unit tests for FR7 cache behavior and cache-hit reuse in anomaly stage.
- [x] Code-review fixes applied: findings cache key cleanup + legacy-read compatibility, partial-cache configuration warning, and scheduler-level cache-hit reuse coverage.

### File List

- artifact/implementation-artifacts/2-6-redis-evidence-caching.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/cache/__init__.py
- src/aiops_triage_pipeline/cache/evidence_window.py
- src/aiops_triage_pipeline/cache/findings_cache.py
- src/aiops_triage_pipeline/cache/peak_cache.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- src/aiops_triage_pipeline/pipeline/stages/anomaly.py
- src/aiops_triage_pipeline/pipeline/stages/evidence.py
- tests/unit/cache/test_evidence_window.py
- tests/unit/cache/test_findings_cache.py
- tests/unit/cache/test_peak_cache.py
- tests/unit/pipeline/stages/test_anomaly.py
- tests/unit/pipeline/test_scheduler.py

## Change Log

- 2026-03-03: Implemented Story 2.6 FR7 Redis evidence caching updates (namespace alignment, env TTL enforcement, per-interval findings read-through cache, degradable Redis failure handling, and full test/lint validation).
- 2026-03-04: Code-review pass applied (3 findings fixed): normalized findings cache key shape with legacy fallback read, added warning for partial cache wiring in anomaly stage, and added scheduler-level cache-hit coverage; story moved to `done`.
