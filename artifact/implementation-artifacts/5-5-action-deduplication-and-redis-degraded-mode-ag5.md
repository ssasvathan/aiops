# Story 5.5: Action Deduplication & Redis Degraded Mode (AG5)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,  
I want actions deduplicated by action_fingerprint with per-type TTLs and safe degraded behavior when Redis is unavailable,  
so that repeat actions are suppressed (preventing paging storms) and Redis failure never causes unsafe escalation (FR33, FR34, FR51).

## Acceptance Criteria

1. **Given** the Rulebook engine reaches AG5  
   **When** dedupe is evaluated against Redis  
   **Then** actions are deduplicated by action_fingerprint with TTLs: PAGE 120m, TICKET 240m, NOTIFY 60m (FR33).
2. **And** a duplicate action within the TTL window is suppressed (action becomes OBSERVE).
3. **And** dedupe keys are stored in Redis using the `dedupe:{fingerprint}` key pattern.
4. **When** Redis is unavailable  
   **Then** the system detects Redis unavailability and caps all actions to NOTIFY-only (FR34).
5. **And** a `DegradedModeEvent` is emitted containing: affected scope, reason, capped action level, estimated impact window (FR51).
6. **And** the DegradedModeEvent is sent to logs and Slack (if configured).
7. **And** when Redis recovers, dedupe state is rebuilt from scratch (cache-only, no persistent state lost) and normal behavior resumes.
8. **And** unit tests verify: deduplication within TTL, TTL expiry allows new action, Redis unavailability -> NOTIFY-only cap, DegradedModeEvent emission, recovery behavior (NFR-T4).

## Tasks / Subtasks

- [ ] Task 1: Implement production AG5 dedupe store with Redis TTL semantics (AC: 1, 2, 3)
  - [ ] Implement `RedisActionDedupeStore` in `src/aiops_triage_pipeline/cache/dedupe.py` behind `GateDedupeStoreProtocol`.
  - [ ] Use Redis atomic claim semantics (`SET ... NX EX`) so duplicate detection and TTL registration are race-safe.
  - [ ] Ensure key format follows `dedupe:{fingerprint}` and supports action-specific TTL behavior required by FR33.

- [ ] Task 2: Align AG5 policy/configuration with FR33 per-action TTL requirements (AC: 1)
  - [ ] Add explicit AG5 TTL mapping for `PAGE=120m`, `TICKET=240m`, `NOTIFY=60m` in the policy path consumed by Stage 6 (rulebook or dedicated AG5 policy section).
  - [ ] Keep policy contracts and validators consistent with any new policy fields (`contracts/rulebook.py` and related tests).
  - [ ] Preserve backward compatibility for existing policy artifacts where feasible and fail loudly on invalid/missing AG5 TTL config.

- [ ] Task 3: Harden Stage 6 AG5 logic for action-aware dedupe and safe degradation (AC: 1, 2, 4)
  - [ ] Update `src/aiops_triage_pipeline/pipeline/stages/gating.py` AG5 path to dedupe by fingerprint in a way that satisfies glossary intent (anomaly identity + action behavior).
  - [ ] Keep gate evaluation monotonic and deterministic; AG5 must only suppress or cap, never escalate.
  - [ ] Preserve AG0-AG6 order and existing AG4/AG6 behavior while integrating real dedupe I/O.

- [ ] Task 4: Emit degraded-mode operational signals on Redis failures (AC: 4, 5, 6, 7)
  - [ ] On AG5 Redis lookup/write failures, emit `DegradedModeEvent` with required fields and structured logging (`event_type="DegradedModeEvent"`).
  - [ ] Update `HealthRegistry` component status for Redis degradation and recovery.
  - [ ] Route degraded notification through Slack integration mode behavior (`OFF|LOG|MOCK|LIVE`) with log fallback.

- [ ] Task 5: Wire AG5 dedupe store through scheduler/runtime boundaries (AC: 1, 4, 7)
  - [ ] Ensure `run_gate_decision_stage_cycle(...)` call sites receive a concrete dedupe store in runtime code paths.
  - [ ] Avoid hidden file/network side effects in pure evaluation paths; keep explicit dependency injection.
  - [ ] Verify recovery path restores normal AG5 behavior once Redis connectivity returns.

- [ ] Task 6: Expand unit and integration coverage for AG5 and degraded mode (AC: 1-8)
  - [ ] Extend `tests/unit/pipeline/stages/test_gating.py` for per-action TTL behavior, duplicate suppression, store errors, and reason codes.
  - [ ] Extend `tests/unit/pipeline/test_scheduler.py` for degraded-mode event/health behavior and recovery.
  - [ ] Add focused tests for dedupe store implementation (`tests/unit/cache/test_dedupe.py` or equivalent).
  - [ ] Add/extend integration tests to verify Redis failure -> NOTIFY-only cap + `DegradedModeEvent` and post-recovery behavior (NFR-T4).

- [ ] Task 7: Run quality gates with zero skips
  - [ ] `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py`
  - [ ] `uv run ruff check`
  - [ ] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-5-action-deduplication-and-redis-degraded-mode-ag5`
  - Story ID: `5.5`
- Epic context: Epic 5 enforces deterministic action safety (AG0-AG6) and storm-control guardrails.
- This story is the first Epic 5 item that requires real AG5 infrastructure behavior (Redis-backed dedupe + degraded-mode signaling), not only protocol seams.
- Current repo baseline relevant to this story:
  - AG5 gate hook exists in `pipeline/stages/gating.py` and supports duplicate/store-error branching.
  - `src/aiops_triage_pipeline/cache/dedupe.py` is currently empty.
  - `src/aiops_triage_pipeline/integrations/slack.py` is currently empty.
  - `DegradedModeEvent` model exists in `src/aiops_triage_pipeline/models/events.py`.
  - `HealthRegistry` exists and already supports `DEGRADED`/`UNAVAILABLE` lifecycle.

### Technical Requirements

- Implement FR33 exactly:
  - PAGE dedupe TTL = 120 minutes.
  - TICKET dedupe TTL = 240 minutes.
  - NOTIFY dedupe TTL = 60 minutes.
- Implement FR34 and FR51 exactly:
  - Redis unavailable must cap to NOTIFY-only.
  - Emit `DegradedModeEvent` with affected scope, reason, capped action level, estimated impact window.
  - Send to logs and Slack when configured.
- Keep AG5 behavior deterministic:
  - no action escalation,
  - reason-code traceability preserved (`AG5_DUPLICATE_SUPPRESSED`, `AG5_DEDUPE_STORE_ERROR`),
  - AG0-AG6 sequence unchanged.
- Preserve cold/hot path boundary:
  - AG5 work remains in hot-path gate evaluation and must not depend on LLM/cold-path components.
- Critical alignment item:
  - Current `redis-ttl-policy-v1` contract exposes a single `dedupe_seconds` per env, while FR33 requires per-action TTLs.
  - Story implementation must resolve this mismatch explicitly (policy model update or AG5-specific policy structure) and add guardrail tests.
- Preserve case safety under transient Redis faults:
  - no uncontrolled exceptions from AG5 path,
  - degradation is explicit, observable, and reversible.

### Architecture Compliance

- Follow architecture mapping for action gating:
  - Stage 6 logic in `src/aiops_triage_pipeline/pipeline/stages/gating.py`.
  - Dedupe implementation in `src/aiops_triage_pipeline/cache/dedupe.py`.
  - Health updates via `src/aiops_triage_pipeline/health/registry.py`.
- Follow architecture Redis key convention:
  - `dedupe:{...}` prefix, no env prefix in key name (dedicated infra per env).
- Keep cross-cutting concerns enforced:
  - deterministic guardrails remain authoritative,
  - degraded-mode safety is explicit via HealthRegistry + events,
  - structured logging conventions remain consistent.
- Reuse existing degraded-event patterns seen in stage code:
  - `pipeline/stages/casefile.py` and `pipeline/stages/outbox.py` already emit `DegradedModeEvent`-shaped logs for critical dependencies.

### Library / Framework Requirements

Verification date: 2026-03-06.

- `redis` (redis-py) latest stable: `7.2.1` (project pin already aligned).
- Use redis-py `Redis.set(...)` options for atomic dedupe claims:
  - `nx=True` to avoid overwriting existing active dedupe windows.
  - `ex=<seconds>` for TTL in seconds.
- Redis command semantics to honor:
  - `SET` supports expiration options (`EX`/`PX`/`EXAT`/`PXAT`) and conditional set (`NX`/`XX`).
  - Deduplication should be implemented without race windows between read/check and write.
- No new third-party dependencies are required for this story.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/cache/dedupe.py`
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
- Likely supporting files:
  - `src/aiops_triage_pipeline/cache/client.py` (if Redis client wrapper is added here)
  - `src/aiops_triage_pipeline/health/registry.py` (only if additional helper methods are needed)
  - `src/aiops_triage_pipeline/integrations/slack.py` (if event dispatch abstraction is implemented here)
  - `src/aiops_triage_pipeline/contracts/rulebook.py` (if AG5 TTL config fields are added)
  - `config/policies/rulebook-v1.yaml` and/or `config/policies/redis-ttl-policy-v1.yaml`
- Test targets:
  - `tests/unit/pipeline/stages/test_gating.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/contracts/test_policy_models.py`
  - `tests/unit/contracts/conftest.py` (if policy contract fixtures change)
  - `tests/unit/cache/test_dedupe.py` (new or updated)
  - `tests/integration/test_degraded_modes.py` (new or updated)

### Testing Requirements

- AG5 unit tests must verify:
  - duplicate in-window suppression for PAGE/TICKET/NOTIFY,
  - TTL expiry allows action again,
  - Redis store failures enforce NOTIFY-only cap,
  - required AG5 reason codes are present and deterministic.
- Degraded-mode behavior tests must verify:
  - `DegradedModeEvent` payload fields are populated per FR51,
  - logging path always emits the event on Redis degradation,
  - Slack emission follows integration mode behavior without blocking pipeline safety.
- Recovery tests must verify:
  - post-recovery dedupe behavior resumes normally,
  - Redis health status transitions from degraded/unavailable back to healthy.
- Regression tests must confirm no breakage to:
  - AG4 threshold behavior from Story 5.4,
  - AG6 postmortem-only semantics,
  - overall AG0-AG6 order and monotonic reduction.
- Full regression quality gate expectation:
  - complete suite with zero skipped tests.

### Previous Story Intelligence

From Story 5.4 (`artifact/implementation-artifacts/5-4-sustained-and-confidence-threshold-gate-ag4.md`):

- Keep deterministic gate ordering and monotonic safety semantics central in Stage 6.
- Preserve precise, explicit reason-code behavior; previous story hardened this and reviewers required extra depth.
- Scheduler-level tests are used as regression guardrails for downstream interactions, not only stage-local tests.
- Maintain story/sprint-status synchronization discipline to avoid state drift.

From Story 5.3 and recent Epic 5 implementation pattern:

- Changes that touch gating are typically coupled with policy artifact updates and contract tests.
- High-risk gating changes receive adversarial-review fixes; design for testability and explicit failure paths up front.

### Git Intelligence Summary

Recent commits (most recent first):

- `f0460fb` story 5.4: apply code-review remediations
- `c7f2d05` Implement AG4 sustained/confidence gating with granular reason codes
- `6bbf54d` chore:(story): story created
- `f3e3144` Story 5.3: implement AG2/AG3 gates and apply review fixes
- `44caa7a` fix(story-5.2): harden AG1 policy validation and close review

Actionable patterns for Story 5.5:

- Concentrate change set in Stage 6 + policy + targeted tests first; avoid broad refactors.
- Keep contract/policy and implementation synchronized in the same story branch.
- Expect reviewer focus on regressions, deterministic behavior, and policy/contract mismatch handling.
- Use explicit tests as the source of truth for gate semantics and degraded-mode behavior.

### Latest Tech Information

Verification date: 2026-03-06.

- `redis` on PyPI reports latest stable `7.2.1` (project currently pinned to `7.2.1`).
- redis-py command docs expose `set(name, value, ex=None, px=None, nx=False, xx=False, keepttl=False, get=False, exat=None, pxat=None)` and recommend using `SET` options instead of deprecated `SETEX` patterns for new code paths.
- Redis official `SET` command supports `NX` and `EX` option combinations used for atomic dedupe registration.
- Redis-py `7.2.1` release notes include parser/stability bug fixes; no migration blockers identified for AG5 implementation.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Deterministic gate engine remains authoritative; no LLM path can override action decisions.
- Preserve degraded-mode safety and fail-loud/fail-safe split:
  - degradable dependency failures continue with caps + explicit health/event signaling,
  - critical invariants do not silently degrade.
- Keep cross-cutting patterns centralized:
  - shared logging conventions,
  - shared health registry semantics,
  - no parallel gate evaluators.
- High-risk changes (gating/contracts/degraded behavior) require targeted regressions and full quality gates.

### Project Structure Notes

- Existing structure already anticipates this story:
  - `cache/` package reserved for Redis-backed helpers,
  - `pipeline/stages/gating.py` owns AG5 logic,
  - scheduler and tests already pass a dedupe abstraction seam.
- No frontend or UX artifacts are required for this backend safety-gate story.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.5: Action Deduplication & Redis Degraded Mode (AG5)`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR33, FR34, FR51)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-R1, NFR-T4)]
- [Source: `artifact/planning-artifacts/prd/glossary-terminology.md` (AG5, action_fingerprint, DegradedModeEvent)]
- [Source: `artifact/planning-artifacts/prd/user-journeys.md#Journey 6: Ops Lead / SRE Manager — System Health & Degraded Mode`]
- [Source: `artifact/planning-artifacts/prd/success-criteria.md` (Storm control + degraded-mode transparency)]
- [Source: `artifact/planning-artifacts/architecture.md` (Action gating placement, Redis key strategy, HealthRegistry)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/5-4-sustained-and-confidence-threshold-gate-ag4.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/contracts/rulebook.py`]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py`]
- [Source: `src/aiops_triage_pipeline/contracts/redis_ttl_policy.py`]
- [Source: `src/aiops_triage_pipeline/models/events.py`]
- [Source: `src/aiops_triage_pipeline/health/registry.py`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `config/policies/redis-ttl-policy-v1.yaml`]
- [Source: https://pypi.org/pypi/redis/json]
- [Source: https://redis.readthedocs.io/en/stable/commands.html]
- [Source: https://redis.io/docs/latest/commands/set/]
- [Source: https://github.com/redis/redis-py/releases/tag/v7.2.1]

### Story Completion Status

- Story context generated for Epic 5 Story 5.5.
- Story file: `artifact/implementation-artifacts/5-5-action-deduplication-and-redis-degraded-mode-ag5.md`.
- Story status set to: `ready-for-dev`.
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
- Core planning artifacts:
  - `artifact/planning-artifacts/epics.md`
  - `artifact/planning-artifacts/architecture.md`
  - `artifact/planning-artifacts/prd/functional-requirements.md`
  - `artifact/planning-artifacts/prd/non-functional-requirements.md`
  - `artifact/planning-artifacts/prd/glossary-terminology.md`
  - `artifact/planning-artifacts/prd/user-journeys.md`
  - `artifact/planning-artifacts/prd/success-criteria.md`
  - `artifact/project-context.md`

### Completion Notes List

- Selected first backlog story from sprint status (`5-5-action-deduplication-and-redis-degraded-mode-ag5`).
- Analyzed Epic 5 context, Story 5.5 ACs, architecture constraints, previous story implementation learnings, and recent commit patterns.
- Added explicit implementation guardrails for AG5 TTL, Redis degraded mode, DegradedModeEvent signaling, and regression protection.
- Included current-technology notes for Redis/redis-py and atomic dedupe command semantics.

### File List

- `artifact/implementation-artifacts/5-5-action-deduplication-and-redis-degraded-mode-ag5.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
