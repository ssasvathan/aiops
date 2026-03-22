# Story 1.5: Execute YAML Rulebook Gates AG0-AG3 via Isolated Rule Engine

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want early-stage deterministic gating to run from YAML-defined checks in an isolated engine,
so that safety-critical action reduction behavior is testable and policy-driven.

**Implements:** FR17, FR18, FR19, FR20, FR21

## Acceptance Criteria

1. **Given** rulebook gate definitions are loaded at startup  
   **When** gate evaluation starts  
   **Then** AG0 through AG3 are evaluated sequentially through the handler registry  
   **And** check type dispatch fails fast at startup if any configured type has no handler.

2. **Given** environment and tier caps apply  
   **When** AG1 evaluates the current action  
   **Then** action severity can only remain equal or be capped downward per environment policy  
   **And** post-condition safety assertions enforce that `PAGE` is impossible outside `PROD + TIER_0`.

## Tasks / Subtasks

- [x] Task 1: Create isolated `rule_engine/` package and public API for early gate execution (AC: 1)
  - [x] Add `src/aiops_triage_pipeline/rule_engine/__init__.py` exposing a narrow API (`evaluate_gates()` or equivalent).
  - [x] Add `engine.py`, `handlers.py`, `predicates.py`, `protocol.py`, and `safety.py` with imports restricted to `contracts/`.
  - [x] Keep handler registry frozen at import time and deterministic in iteration order.

- [x] Task 2: Implement YAML-driven AG0-AG3 handler execution with fail-fast startup validation (AC: 1)
  - [x] Implement check-type dispatch for AG0-AG3 checks from `config/policies/rulebook-v1.yaml`.
  - [x] Validate at startup that each configured `check.type` maps to a registered handler; raise a typed startup error on mismatch.
  - [x] Preserve existing gate-order contract and deterministic reason-code ordering.

- [x] Task 3: Implement AG1 cap semantics and AG3 source-topic constraint in isolated engine (AC: 2)
  - [x] Enforce monotonic capping (`never escalate`) for environment and prod-tier policies.
  - [x] Preserve compatibility for `uat`/`stage` mapping fallback currently used by policy artifacts.
  - [x] Enforce structural impossibility of `PAGE` outside `PROD + TIER_0` via post-condition safety assertions.

- [x] Task 4: Integrate isolated rule engine into Stage 6 while preserving current behavior boundaries (AC: 1, 2)
  - [x] Refactor `pipeline/stages/gating.py` so AG0-AG3 evaluation flows through `rule_engine/`.
  - [x] Keep AG4-AG6 behavior deterministic and backward-compatible for Story 1.6 continuation.
  - [x] Keep `audit/replay.py` and scheduler paths stable with no contract-breaking API changes.

- [x] Task 5: Update contract/policy validation seams and docs for CR-02 traceability (AC: 1, 2)
  - [x] Extend `contracts/rulebook.py` validation only where required for AG0-AG3 handler registry integrity.
  - [x] Ensure policy-driven behavior remains authoritative from YAML, not hardcoded branching.
  - [x] Update required docs (`docs/architecture-patterns.md`, plus any directly affected operational docs) in the same change set.

- [x] Task 6: Expand tests and run quality gates with zero skipped tests (AC: 1, 2)
  - [x] Add unit tests for `rule_engine/` package (engine, handlers, predicates, safety, startup validation).
  - [x] Keep and pass existing `tests/unit/pipeline/stages/test_gating.py` coverage to prevent regressions.
  - [x] Add targeted tests for unknown evidence handling in AG2 and source-topic deny behavior in AG3 through the new engine path.
  - [x] Run:
    - [x] `uv run ruff check`
    - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Confirm regression gate result is `0 skipped`.

## Dev Notes

### Developer Context Section

- Story 1.5 is a refactor + isolation boundary story: extract early gate execution (AG0-AG3) from monolithic Stage 6 logic into `rule_engine/` without changing external decision contracts.
- Current codebase already evaluates AG0-AG6 in `pipeline/stages/gating.py`; implementation should migrate behavior instead of introducing parallel or duplicate decision logic.
- This story must protect deterministic properties relied on by downstream dispatch, casefile trails, and replay workflows.
- Keep scope tight to AG0-AG3 isolation and startup handler validation; avoid implementing AG4-AG6 redesign here (Story 1.6 scope).

### Technical Requirements

- FR17: Gate evaluation remains sequential and policy-driven by YAML check definitions.
- FR18: AG1 enforces environment/tier caps with only downward or unchanged outcomes.
- FR19: Post-condition safety assertions keep `PAGE` impossible outside `PROD + TIER_0`.
- FR20: AG2 preserves UNKNOWN evidence semantics (never collapse UNKNOWN/ABSENT/STALE to PRESENT).
- FR21: AG3 enforces source-topic gating constraints with deterministic reason-code output.
- NFR-P1: Preserve p99 gate evaluation latency guardrail (<= 500ms).
- NFR-R6/NFR-R7: Unknown handler/check-type is fail-fast at startup; degradable dependencies keep capped behavior.
- NFR-A5: Decision trail and reason-code fidelity remain complete and deterministic.

### Architecture Compliance

- D4 (critical): `rule_engine/` must be isolated from `pipeline/`, `integrations/`, `storage/`, `health/`, and `config/`; allow imports only from `contracts/`.
- D4 (critical): Handler registry must be frozen at import time and validate all configured check types before runtime processing.
- D1/D13 consistency: preserve action fingerprint and policy-driven cap behavior compatible with shared Redis/dedupe and existing gate execution patterns.
- Maintain standing invariant that deterministic hot-path gating remains authoritative; no LLM/cold-path coupling.
- Preserve composition-root wiring (`__main__.py`) and avoid module-level mutable singleton patterns.

### Library / Framework Requirements

- Locked project runtime for implementation:
  - Python >=3.13
  - pydantic==2.12.5
  - pydantic-settings~=2.13.1
  - pyyaml~=6.0
  - pytest==9.0.2
  - redis==7.2.1
  - SQLAlchemy==2.0.47
  - confluent-kafka==2.13.0
- Latest upstream snapshot checked on 2026-03-22 (awareness only, no in-scope upgrades):
  - pydantic 2.12.5
  - pydantic-settings 2.13.1
  - PyYAML 6.0.3
  - pytest 9.0.2
  - SQLAlchemy 2.0.48
  - redis 7.3.0
  - confluent-kafka 2.13.2
- PyPI vulnerability feeds for the above packages reported zero active vulnerabilities at lookup time.
- Implementation guidance: use safe YAML parsing patterns and keep frozen contract-model behavior for policy/contract objects.

### File Structure Requirements

- Create:
  - `src/aiops_triage_pipeline/rule_engine/__init__.py`
  - `src/aiops_triage_pipeline/rule_engine/engine.py`
  - `src/aiops_triage_pipeline/rule_engine/handlers.py`
  - `src/aiops_triage_pipeline/rule_engine/predicates.py`
  - `src/aiops_triage_pipeline/rule_engine/protocol.py`
  - `src/aiops_triage_pipeline/rule_engine/safety.py`
  - `tests/unit/rule_engine/test_engine.py`
  - `tests/unit/rule_engine/test_handlers.py`
  - `tests/unit/rule_engine/test_predicates.py`
  - `tests/unit/rule_engine/test_safety.py`
- Modify likely:
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `src/aiops_triage_pipeline/contracts/rulebook.py`
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
  - `src/aiops_triage_pipeline/audit/replay.py` (only if adapter changes are required)
  - `tests/unit/pipeline/stages/test_gating.py`
  - `config/policies/rulebook-v1.yaml` (only if minimally required for AG0-AG3 handler clarity)
  - `docs/architecture-patterns.md`

### Testing Requirements

- Preserve existing Stage 6 regression behavior:
  - gate order remains `AG0..AG6`
  - monotonic cap enforcement
  - deterministic reason-code ordering
  - AG2 insufficient evidence downgrade semantics
  - AG3 source-topic page denial semantics
- Add new validation coverage:
  - startup failure when YAML `check.type` has no registered handler
  - AG0 malformed input handling via isolated engine
  - AG1 matrix for env/tier caps (including `uat`/`stage` compatibility)
  - AG2 UNKNOWN/ABSENT/STALE and allowed-non-present exceptions
  - AG3 page deny path with reason code retention
  - post-condition safety assertion that prevents `PAGE` outside `PROD + TIER_0`
- Required quality commands:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Sprint quality gate: 0 skipped tests.

### Previous Story Intelligence

- Story 1.4 completed topology ownership and blast-radius hardening with extensive regression coverage around deterministic fallback behavior.
- Recent review fixes emphasized full file-list traceability, cleanup hygiene, and explicit regression checks; carry these standards into Story 1.5.
- Story 1.5 should avoid topology-surface churn and keep change radius concentrated in gating/rulebook paths.

### Git Intelligence Summary

- Last five commits show consistent pattern: create story context, implement/refine story, remediate review findings, then status synchronization.
- Recent implementation hotspots:
  - `src/aiops_triage_pipeline/__main__.py`
  - `src/aiops_triage_pipeline/config/settings.py`
  - `src/aiops_triage_pipeline/pipeline/stages/peak.py`
  - topology registry loader/resolver paths from Story 1.4
- Actionable guidance:
  - keep AG0-AG3 isolation changes localized to `gating.py` + new `rule_engine/` + related tests
  - avoid broad refactors in unrelated runtime-mode or topology modules
  - retain deterministic logging and decision-trail field conventions already established

### Latest Tech Information

- External snapshot date: 2026-03-22.
- Latest stable versions identified from PyPI API:
  - pydantic 2.12.5
  - pydantic-settings 2.13.1
  - PyYAML 6.0.3
  - pytest 9.0.2
  - SQLAlchemy 2.0.48
  - redis 7.3.0
  - confluent-kafka 2.13.2
- Story decision: keep locked project dependency set for implementation stability; adopt only compatible best practices (safe YAML parsing, frozen-model contracts, deterministic tests/logging).

### Project Context Reference

- Applied `archive/project-context.md` constraints:
  - Python 3.13 typing conventions and frozen model discipline
  - config module remains generic and leaf-like
  - deterministic hot-path authority and explicit degraded/error signaling
  - shared logging, correlation-id, and health/metrics patterns
  - strict no-skip full regression expectation

### References

- [Source: `artifact/planning-artifacts/epics.md` - Epic 1, Story 1.5]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` - FR17, FR18, FR19, FR20, FR21]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-P1, NFR-R6, NFR-R7, NFR-A5]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` - safety invariants, UNKNOWN propagation]
- [Source: `artifact/planning-artifacts/prd/process-governance-requirements.md` - PG1, PG2]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` - D4 isolation and handler rules]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/implementation-artifacts/1-4-resolve-topology-ownership-and-blast-radius-from-unified-registry.md`]
- [Source: `artifact/implementation-artifacts/sprint-status.yaml`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/contracts/rulebook.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/peak.py`]
- [Source: `src/aiops_triage_pipeline/audit/replay.py`]
- [Source: `tests/unit/pipeline/stages/test_gating.py`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `archive/project-context.md`]
- [Source: https://pypi.org/project/pydantic/]
- [Source: https://pypi.org/project/pydantic-settings/]
- [Source: https://pypi.org/project/PyYAML/]
- [Source: https://pypi.org/project/pytest/]
- [Source: https://pypi.org/project/SQLAlchemy/]
- [Source: https://pypi.org/project/redis/]
- [Source: https://pypi.org/project/confluent-kafka/]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Story creation workflow executed with full artifact analysis and sprint status synchronization.
- Validation fallback applied manually because `_bmad/core/tasks/validate-workflow.xml` is absent in this repository.
- Implemented isolated `rule_engine/` package (engine, handlers, predicates, protocol, safety) with contracts-only dependency boundary.
- Refactored Stage 6 gating to execute AG0-AG3 through `rule_engine.evaluate_gates()` while preserving AG4-AG6 behavior and output contract.
- Added startup fail-fast validation via `load_rulebook_policy()` + `validate_rulebook_handlers()` and extended rulebook validation for duplicate gate IDs/check type normalization.
- Resolved compatibility regressions in audit reproducibility tests by aligning synthetic test rulebook AG0-AG3 checks to handler-based semantics.
- Completed quality gates: `uv run ruff check` and full regression `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` with zero skips.

### Completion Notes List

- Implemented isolated AG0-AG3 rule-engine package with frozen handler registry and deterministic dispatch order.
- Enforced startup check-type validation with typed errors (`UnknownCheckTypeStartupError`) and integrated it into rulebook policy loading.
- Added monotonic AG1 capping and explicit PAGE safety assertion (`PROD + TIER_0` only), preserving `uat`/`stage` fallback behavior.
- Preserved Stage 6 AG4-AG6 logic and decision output stability while routing early gates through the isolated engine.
- Added dedicated `tests/unit/rule_engine/*` coverage plus startup-validation tests and compatibility updates in existing suites.
- Remediated code-review findings by making Story 1.5 ATDD tests discoverable and aligned with current rule-engine API.
- Full regression and lint gates passed (875 passed, 0 skipped); story status advanced to `done`.

### File List

- artifact/implementation-artifacts/1-5-execute-yaml-rulebook-gates-ag0-ag3-via-isolated-rule-engine.md
- artifact/implementation-artifacts/sprint-status.yaml
- docs/architecture-patterns.md
- src/aiops_triage_pipeline/contracts/rulebook.py
- src/aiops_triage_pipeline/pipeline/stages/gating.py
- src/aiops_triage_pipeline/pipeline/stages/peak.py
- src/aiops_triage_pipeline/rule_engine/__init__.py
- src/aiops_triage_pipeline/rule_engine/engine.py
- src/aiops_triage_pipeline/rule_engine/handlers.py
- src/aiops_triage_pipeline/rule_engine/predicates.py
- src/aiops_triage_pipeline/rule_engine/protocol.py
- src/aiops_triage_pipeline/rule_engine/safety.py
- tests/atdd/fixtures/story_1_5_test_data.py
- tests/atdd/test_story_1_5_rule_engine.py
- tests/unit/audit/test_decision_reproducibility.py
- tests/unit/pipeline/stages/test_peak.py
- tests/unit/rule_engine/test_engine.py
- tests/unit/rule_engine/test_handlers.py
- tests/unit/rule_engine/test_predicates.py
- tests/unit/rule_engine/test_safety.py
- artifact/implementation-artifacts/review-1-5-execute-yaml-rulebook-gates-ag0-ag3-via-isolated-rule-engine.md

## Senior Developer Review (AI)

- Reviewer: Sas (AI)
- Date: 2026-03-22
- Outcome: Approved (all review findings fixed)

### Findings Resolved

- [MEDIUM] ATDD test module was not pytest-discoverable due to non-`test_*.py` filename; fixed by renaming to `tests/atdd/test_story_1_5_rule_engine.py`.
- [MEDIUM] ATDD assertions targeted stale `rule_engine` API shape; fixed by updating tests to current `evaluate_gates(..., initial_action=...)` and `EarlyGateEvaluation` fields.
- [LOW] Story File List omitted changed fixture `tests/atdd/fixtures/story_1_5_test_data.py`; fixed by updating Dev Agent Record file list.

### Validation Executed

- `uv run ruff check` (pass)
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (875 passed, 0 skipped)

## Story Completion Status

- Story status: `done`
- Completion note: AG0-AG3 isolated rule-engine implementation and review remediations complete with full lint/regression gates passing (875 passed, 0 skipped).

## Change Log

- 2026-03-22: Story created via create-story workflow with exhaustive planning/architecture/code-context analysis; status set to ready-for-dev.
- 2026-03-22: Implemented isolated AG0-AG3 `rule_engine` package, integrated Stage 6 early-gate evaluation path, added startup handler validation, expanded test coverage, and passed full quality gates (870 passed, 0 skipped); status set to review.
- 2026-03-22: Executed `bmad-bmm-code-review`, fixed ATDD discoverability/API issues, updated story file-list traceability, reran quality gates (`ruff`, full Docker-backed pytest: 875 passed, 0 skipped), and set story status to done.
