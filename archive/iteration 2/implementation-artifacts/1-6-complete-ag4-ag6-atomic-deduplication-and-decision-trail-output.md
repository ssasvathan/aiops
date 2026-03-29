# Story 1.6: Complete AG4-AG6, Atomic Deduplication, and Decision Trail Output

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want late-stage gating and decision outputs to be deterministic and auditable,
so that every action has reproducible evidence and reason codes.

**Implements:** FR22, FR23, FR24, FR25

## Acceptance Criteria

1. **Given** evidence, sustained state, and topology context are available  
   **When** AG4 through AG6 execute  
   **Then** sustained/confidence, atomic dedupe, and postmortem predicates are evaluated in sequence  
   **And** AG5 uses single-step atomic set-if-not-exists with TTL as the authoritative dedupe check.

2. **Given** a gate evaluation completes  
   **When** an action is finalized  
   **Then** the pipeline outputs `ActionDecisionV1` with full reason codes and gate trail  
   **And** unknown evidence semantics remain explicit end-to-end.

## Tasks / Subtasks

- [x] Task 1: Finalize AG4 sustained/confidence gate behavior in Stage 6 evaluation flow (AC: 1)
  - [x] Keep AG4 checks tied to rulebook policy (`min_value diagnosis_confidence`, `equals sustained`) with deterministic reason-code order.
  - [x] Preserve monotonic reduction behavior (never escalate) and current gate order contract `AG0..AG6`.
  - [x] Ensure AG4 continues to run only for `TICKET`/`PAGE` candidate actions and does not alter low-urgency paths.

- [x] Task 2: Implement AG5 as single authoritative atomic dedupe check (AC: 1)
  - [x] Remove the split read-then-write race window in Stage 6 AG5 logic; use one atomic write outcome as source of truth.
  - [x] Align gate behavior with degraded-mode policy: dedupe store errors cap to safe action and emit reason code.
  - [x] Preserve per-action TTL behavior and Redis health metrics for dedupe operations.

- [x] Task 3: Complete AG6 postmortem predicate behavior for qualifying peak windows (AC: 1)
  - [x] Keep AG6 gating scoped to `PROD + TIER_0` and ensure it never mutates final action severity.
  - [x] Ensure postmortem fields (`postmortem_required`, `postmortem_mode`, reason codes) are deterministic and consistent.
  - [x] Preserve strict handling of `peak is True` and sustained semantics from rulebook intent.

- [x] Task 4: Guarantee ActionDecisionV1 decision-trail completeness across handoff boundaries (AC: 2)
  - [x] Ensure `ActionDecisionV1` output contains full `gate_rule_ids` and `gate_reason_codes` for every decision path.
  - [x] Verify unknown evidence semantics remain explicit through gating, casefile, and replay paths.
  - [x] Preserve contract compatibility for downstream stages (`dispatch`, `casefile`, `audit/replay`).

- [x] Task 5: Keep policy/config and architecture consistency for AG4-AG6 (AC: 1, 2)
  - [x] Keep `config/policies/rulebook-v1.yaml` as authoritative source for AG4/AG5/AG6 checks and effects.
  - [x] Preserve Redis namespace conventions and degradation posture for dedupe behavior.
  - [x] Update `docs/` and `README.md` only if behavior/operations expectations materially change (PG1).

- [x] Task 6: Expand and run regression coverage with zero skipped tests (AC: 1, 2)
  - [x] Add/update unit tests for AG4/AG5/AG6 transitions, reason-code ordering, and postmortem outputs.
  - [x] Add/update dedupe tests to validate single-step atomic semantics and degraded-mode behavior.
  - [x] Re-run audit reproducibility tests to ensure replay remains deterministic with AG5 handling constraints.
  - [x] Run:
    - [x] `uv run ruff check`
    - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Confirm full regression result is `0 skipped`.

## Dev Notes

### Developer Context Section

- Story 1.5 already moved AG0-AG3 into `rule_engine/`; Story 1.6 completes the late-stage path in `pipeline/stages/gating.py` (AG4-AG6 + final decision trail output).
- Current AG5 path still performs a two-step check (`is_duplicate` then `remember`), which can create a race window across replicas; this story closes that gap.
- Keep deterministic behavior first: gate order, monotonic reduction, reason-code ordering, and reproducibility for audit replay.
- No UX artifact exists for this project; this is backend-only event-driven pipeline work.

### Technical Requirements

- FR22: Evaluate sustained threshold and confidence floor (AG4) using externalized sustained state.
- FR23: Perform AG5 atomic dedupe via single-step `SET NX EX` semantics with TTL.
- FR24: Evaluate AG6 postmortem predicates for qualifying peak windows.
- FR25: Emit `ActionDecisionV1` with full reason codes and gate evaluation trail.
- NFR-SC4: Coordination mechanisms (including AG5 dedupe) use Redis as the shared state layer.
- NFR-R5/NFR-R7: Redis failure must degrade safely and remain observable via health signals.
- NFR-A5: Preserve full gate reason-code trail for every triage decision.

### Architecture Compliance

- D1/D13: Keep Redis key/connection usage consistent with namespace and shared pooling constraints.
- D3: AG5 Redis failures must follow degraded behavior (safe cap + health update), not silent continuation.
- D4: Keep rule-engine boundary intact (no dependency drift from established package boundaries).
- Maintain standing invariant: `PAGE` remains structurally impossible outside `PROD + TIER_0`.
- Maintain UNKNOWN evidence semantics end-to-end (no coercion to PRESENT/zero).

### Library / Framework Requirements

- Locked implementation baseline from `pyproject.toml`:
  - Python >=3.13
  - pydantic==2.12.5
  - pydantic-settings~=2.13.1
  - pyyaml~=6.0
  - redis==7.2.1
  - SQLAlchemy==2.0.47
  - confluent-kafka==2.13.0
  - pytest==9.0.2
- Latest stable snapshot checked on 2026-03-22 (PyPI):
  - pydantic 2.12.5
  - pydantic-settings 2.13.1
  - PyYAML 6.0.3
  - pytest 9.0.2
  - SQLAlchemy 2.0.48
  - redis 7.3.0
  - confluent-kafka 2.13.2
- Story decision: do not upgrade dependencies in this story unless required for AG4-AG6 correctness or security response.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `src/aiops_triage_pipeline/cache/dedupe.py`
  - `src/aiops_triage_pipeline/contracts/action_decision.py` (only if contract clarifications are required)
  - `src/aiops_triage_pipeline/audit/replay.py` (verify replay compatibility with AG5 behavior)
  - `config/policies/rulebook-v1.yaml` (only if policy metadata refinement is needed)
- Primary test targets:
  - `tests/unit/pipeline/stages/test_gating.py`
  - `tests/unit/cache/test_dedupe.py`
  - `tests/unit/audit/test_decision_reproducibility.py`
  - Add integration coverage only where race/degraded behavior requires real Redis verification.

### Testing Requirements

- Validate AG4:
  - confidence and sustained checks, threshold boundary behavior, deterministic reason-code ordering.
- Validate AG5:
  - single-step atomic dedupe semantics, duplicate suppression behavior, store-error safe cap path.
- Validate AG6:
  - PROD/TIER_0 gating conditions, `peak+sustained` predicate behavior, postmortem fields stability.
- Validate decision trail:
  - `ActionDecisionV1` includes full gate IDs and reason codes for all key paths.
- Validate replay:
  - replay output remains deterministic and policy-version guarded.
- Required quality commands:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Sprint gate requirement: 0 skipped tests.

### Previous Story Intelligence

- Story 1.5 established AG0-AG3 through `rule_engine.evaluate_gates`; avoid re-introducing parallel gating logic outside established boundaries.
- Recent review findings emphasized:
  - pytest discoverability naming (`test_*.py`)
  - alignment to current API contracts
  - complete file-list traceability in story artifacts
- Carry these lessons into Story 1.6 changes and verification.

### Git Intelligence Summary

- Recent commits show consistent sequence: create story artifact, implement with tests, run review workflow, then status progression.
- Relevant hotspots from the latest 5 commits:
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `src/aiops_triage_pipeline/cache/dedupe.py`
  - `tests/unit/pipeline/stages/test_gating.py`
  - `tests/unit/cache/test_dedupe.py`
  - `tests/unit/audit/test_decision_reproducibility.py`
- Actionable guidance:
  - keep Story 1.6 changes localized to AG4-AG6 + dedupe + decision trail contracts/tests
  - avoid unrelated runtime-mode or topology refactors
  - preserve deterministic logging/metrics conventions for gate evaluation.

### Latest Tech Information

- External lookup date: 2026-03-22.
- PyPI latest stable versions checked for key dependencies used in this story:
  - pydantic 2.12.5 (locked, current)
  - pydantic-settings 2.13.1 (locked range, current)
  - PyYAML 6.0.3 (locked range compatible)
  - pytest 9.0.2 (locked, current)
  - SQLAlchemy 2.0.48 (one patch above locked 2.0.47)
  - redis 7.3.0 (above locked 7.2.1)
  - confluent-kafka 2.13.2 (above locked 2.13.0)
- PyPI vulnerability metadata for the checked packages reported 0 listed vulnerabilities at lookup time.

### Project Context Reference

- Applied `archive/project-context.md` constraints:
  - Python 3.13 typing conventions and frozen-model discipline
  - deterministic hot-path guardrail authority and no LLM override of gate outcomes
  - explicit degraded-mode handling with HealthRegistry visibility
  - shared structured logging/correlation conventions
  - full regression expectation with zero skipped tests.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Epic 1, Story 1.6]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` - FR22, FR23, FR24, FR25]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-SC4, NFR-R5, NFR-R7, NFR-A5]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` - UNKNOWN propagation, atomic dedupe invariant]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` - D1, D3, D4, D13]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/implementation-artifacts/1-5-execute-yaml-rulebook-gates-ag0-ag3-via-isolated-rule-engine.md`]
- [Source: `artifact/implementation-artifacts/review-1-5-execute-yaml-rulebook-gates-ag0-ag3-via-isolated-rule-engine.md`]
- [Source: `artifact/implementation-artifacts/sprint-status.yaml`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/cache/dedupe.py`]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py`]
- [Source: `src/aiops_triage_pipeline/audit/replay.py`]
- [Source: `tests/unit/pipeline/stages/test_gating.py`]
- [Source: `tests/unit/cache/test_dedupe.py`]
- [Source: `tests/unit/audit/test_decision_reproducibility.py`]
- [Source: `archive/project-context.md`]
- [Source: https://pypi.org/pypi/pydantic/json]
- [Source: https://pypi.org/pypi/pydantic-settings/json]
- [Source: https://pypi.org/pypi/PyYAML/json]
- [Source: https://pypi.org/pypi/pytest/json]
- [Source: https://pypi.org/pypi/SQLAlchemy/json]
- [Source: https://pypi.org/pypi/redis/json]
- [Source: https://pypi.org/pypi/confluent-kafka/json]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Create-story workflow executed in YOLO/full-auto mode for explicit story key `1-6-complete-ag4-ag6-atomic-deduplication-and-decision-trail-output`.
- Story context assembled from epics, PRD shards, architecture shards, project context, previous story artifact, and recent git history.
- Workflow validation-task dependency `_bmad/core/tasks/validate-workflow.xml` is missing in repository; checklist invocation was blocked.
- Dev-story workflow executed in YOLO mode using `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`.
- Implemented AG5 Stage 6 atomic-authoritative behavior by using a single `remember(..., action)` outcome in `evaluate_rulebook_gates` and removing read-then-write branching.
- Updated AG5-focused and downstream scheduler/ATDD tests to enforce atomic claim semantics and validate full AG0..AG6 decision trail determinism.
- Ran required quality gates: targeted unit regression, `uv run ruff check`, and full Docker-enabled `uv run pytest -q -rs` with zero skipped tests.

### Completion Notes List

- Story artifact created with status `ready-for-dev` and comprehensive AG4-AG6 implementation guardrails.
- Sprint tracking status updated from `backlog` to `ready-for-dev` for Story 1.6.
- AG5 now uses one atomic dedupe claim outcome as authoritative duplicate detection in Stage 6, preserving safe-cap degraded behavior on store errors.
- AG4/AG6 deterministic behavior and full ActionDecisionV1 gate trail (`AG0..AG6`, reason-code ordering, postmortem fields) were validated across unit and ATDD paths.
- Full regression completed successfully with `879 passed` and `0 skipped`.

### File List

- artifact/implementation-artifacts/1-6-complete-ag4-ag6-atomic-deduplication-and-decision-trail-output.md
- artifact/implementation-artifacts/sprint-status.yaml
- artifact/implementation-artifacts/review-1-6-complete-ag4-ag6-atomic-deduplication-and-decision-trail-output.md
- artifact/test-artifacts/atdd-checklist-1-6-complete-ag4-ag6-atomic-deduplication-and-decision-trail-output.md
- artifact/test-artifacts/tea-atdd-api-tests-2026-03-22T17-19-39Z.json
- artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-22T17-19-39Z.json
- artifact/test-artifacts/tea-atdd-summary-2026-03-22T17-19-39Z.json
- src/aiops_triage_pipeline/pipeline/stages/gating.py
- tests/atdd/fixtures/story_1_6_test_data.py
- tests/unit/pipeline/stages/test_gating.py
- tests/unit/pipeline/test_scheduler.py
- tests/atdd/test_story_1_6_atomic_dedupe_and_decision_trail.py

## Senior Developer Review (AI)

- Reviewer: Sas (AI)
- Date: 2026-03-22
- Outcome: Approved (all review findings fixed)

### Findings Resolved

- [MEDIUM] Story Dev Agent Record file list omitted changed `tests/atdd/fixtures/story_1_6_test_data.py`; fixed by updating File List.
- [MEDIUM] Story Dev Agent Record file list omitted changed ATDD output artifacts under `artifact/test-artifacts/`; fixed by updating File List with all uncommitted artifacts for this story run.
- [LOW] Story lacked a dedicated review findings artifact for Story 1.6; fixed by creating `artifact/implementation-artifacts/review-1-6-complete-ag4-ag6-atomic-deduplication-and-decision-trail-output.md`.

### Validation Executed

- `uv run ruff check` (pass)
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (879 passed, 0 skipped)

## Story Completion Status

- Story status: `done`
- Completion note: AG4-AG6 implementation and code-review remediations are complete with atomic AG5 semantics, full decision-trail coverage, and zero-skip regression validation.

## Change Log

- 2026-03-22: Story created via create-story workflow with full artifact analysis and sprint status synchronization; status set to `ready-for-dev`.
- 2026-03-22: Implemented Story 1.6 AG4-AG6 completion work, switched AG5 Stage 6 dedupe to single atomic claim outcome, updated tests, and advanced story status to `review` after passing lint + full zero-skip regression.
- 2026-03-22: Executed `bmad-bmm-code-review`, resolved all review findings (file-list traceability + review artifact generation), revalidated quality gates, and set story status to `done`.
