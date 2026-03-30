# Story 1.2: Enrich Gate Inputs and Enforce AG4 Confidence/Sustained Rules

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Platform SRE,
I want AG4 to evaluate both confidence and sustained conditions with clear capping behavior,
so that escalations only occur for strong, sustained signals.

## Acceptance Criteria

1. Given scoring outputs are produced for a scope, when gate inputs are assembled, then `GateInputContext` is enriched with both `diagnosis_confidence` and `proposed_action`, and enrichment occurs before `collect_gate_inputs_by_scope`.
2. Given AG4 evaluates a scope with `diagnosis_confidence < 0.6`, when candidate action is `TICKET` or `PAGE`, then AG4 caps the action to `OBSERVE`, independent of other positive gate signals.
3. Given AG4 evaluates a scope with `diagnosis_confidence >= 0.6` and `is_sustained=True`, when environment caps permit the candidate action, then AG4 allows `TICKET`/`PAGE` progression, and PAGE outside `PROD+TIER_0` remains blocked by existing cap authority.
4. Given AG4 evaluates a scope with `diagnosis_confidence >= 0.6` and `is_sustained=False`, when candidate action is `TICKET` or `PAGE`, then AG4 suppresses escalation to `OBSERVE`, and suppression reasoning is captured as sustained-condition failure.

## Tasks / Subtasks

- [x] Add a pre-collection gate-input context enrichment step (AC: 1)
  - [x] Implement enrichment in the stage/scheduler path before `collect_gate_inputs_by_scope` is called.
  - [x] Populate `GateInputContext.diagnosis_confidence` and `GateInputContext.proposed_action` using deterministic hot-path signals only.
  - [x] Preserve tri-state sustained semantics (`True | False | None`) for scoring; never treat `None` as `True`.
- [x] Wire `collect_gate_inputs_by_scope` to consume enriched context without breaking current deterministic behavior (AC: 1)
  - [x] Keep scoring deterministic and local to gating-stage code paths.
  - [x] Preserve per-scope/per-finding behavior and existing `max_safe_action` cap-down logic.
  - [x] Keep fail-safe fallback (`0.0/OBSERVE`) and fallback metadata/logging.
- [x] Enforce AG4 confidence+sustained rules exactly and keep reason-code semantics stable (AC: 2, 3, 4)
  - [x] Keep confidence floor at `0.6` (`LOW_CONFIDENCE` on fail).
  - [x] Keep sustained check as explicit boolean equality (`NOT_SUSTAINED` on fail).
  - [x] Ensure deterministic reason ordering when both checks fail.
- [x] Expand/adjust tests for enrichment timing and AG4 outcomes (AC: 1, 2, 3, 4)
  - [x] Add/update scheduler-level test proving enrichment occurs before `collect_gate_inputs_by_scope`.
  - [x] Keep AG4 boundary matrix coverage for `0.59`, `0.60`, and sustained true/false across `PAGE` and `TICKET` candidates.
  - [x] Assert environment caps remain final authority (for example, local/dev still cap high-urgency actions).
- [x] Run quality gates with zero skipped tests (AC: 1, 2, 3, 4)
  - [x] Run targeted suites for touched files first.
  - [x] Run full regression using Docker-backed command and confirm `0 skipped`.

## Dev Notes

### Story Context and Constraints

- Story scope is FR6, FR8, FR9, FR10 only.
- Do not implement FR11/FR18/FR19 persistence and audit differentiation in this story; those belong to Story 1.3.
- No contract/schema changes are allowed (`contracts/*` remains frozen).
- Keep action-authority hierarchy unchanged: scoring proposes; AG0-AG6 and env/tier caps decide final action.

### Current Code Reality (Build on Existing)

- Story 1.1 already implemented deterministic scoring helpers and scoring metadata in `pipeline/stages/gating.py`.
- `collect_gate_inputs_by_scope` currently computes scoring result per finding and populates `GateInputV1` (`diagnosis_confidence`, `proposed_action`) directly.
- AG4 currently evaluates both checks through rulebook-driven checks with explicit reason-code extraction:
  - confidence check (`min_value diagnosis_confidence`, threshold `0.6`)
  - sustained check (`equals sustained true`)
- Existing tests already cover AG4 boundary behavior and deterministic reason ordering.

### Architecture Compliance Guardrails

- Keep scoring and AG4 integration in `src/aiops_triage_pipeline/pipeline/stages/gating.py` and scheduler call paths only.
- Do not create new shared scoring modules.
- Do not import from `src/aiops_triage_pipeline/diagnosis/*` (D6 invariant).
- Preserve protected zones:
  - `src/aiops_triage_pipeline/contracts/*`
  - `src/aiops_triage_pipeline/diagnosis/*`
  - `src/aiops_triage_pipeline/integrations/*`
- Preserve deterministic/fail-safe behavior:
  - on scoring failure => `diagnosis_confidence=0.0`, `proposed_action=OBSERVE`
  - emit `event_type="gating.scoring.fallback_applied"`

### Library/Framework Requirements

- Stay on current dependency set from `pyproject.toml` for this story.
- Use Python 3.13 typing style and existing `structlog` patterns.
- Keep rulebook semantics centralized in `config/policies/rulebook-v1.yaml`.

### File Structure Requirements

- Primary implementation:
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- Primary policy reference (verify, do not drift semantics):
  - `config/policies/rulebook-v1.yaml`
- Primary tests:
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/pipeline/stages/test_gating.py`

### Testing Requirements

- Required test assertions:
  - Enrichment occurs before `collect_gate_inputs_by_scope` and is deterministic for same inputs.
  - AG4 caps to OBSERVE when `diagnosis_confidence < 0.6` for `TICKET/PAGE` candidates.
  - AG4 caps to OBSERVE when `sustained=False` even with confidence >= 0.6.
  - AG4 allows high-urgency progression at boundary `diagnosis_confidence == 0.6` when `sustained=True`, subject to env caps.
  - Reason codes are deterministic (`LOW_CONFIDENCE`, `NOT_SUSTAINED`) with stable ordering.
- Required full regression command (must yield zero skipped):

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

### Previous Story Intelligence (Story 1.1)

- Reuse the existing deterministic scoring helpers/constants and metadata key schema (`score_version`, `base_score`, `sustained_boost`, `peak_boost`, `final_score`, `score_reason_code`, `fallback_applied`).
- Keep conservative sustained handling from review fixes: missing/invalid sustained metadata must not increase confidence.
- Keep established test style:
  - stage-level assertions in `tests/unit/pipeline/stages/test_gating.py`
  - scheduler wiring assertions in `tests/unit/pipeline/test_scheduler.py`
- Preserve no-regression baseline achieved by Story 1.1 (`full regression with 0 skipped`).

### Git Intelligence Summary

Recent commits show the active implementation/test surface and conventions to preserve:

- `45c87fc` (`fix(review)`): refined Story 1.1 logic and tests in gating and integration safety checks.
- `33b9007` (`feat(gating)`): introduced deterministic scoring core and AG4 boundary-focused tests.
- `ce24a6c` (`create-story`): story artifact format and sprint-status update pattern.

Actionable pattern: continue using focused edits in `gating.py` + scheduler + mirrored unit tests, while keeping story artifacts updated in `artifact/implementation-artifacts/`.

### Latest Tech Information (Step 4 Research)

Live checks run on 2026-03-29 against PyPI JSON endpoints:

- `pydantic`: latest `2.12.5` (project pinned `2.12.5`)
- `pydantic-settings`: latest `2.13.1` (project range `~=2.13.1`)
- `pytest`: latest `9.0.2` (project pinned `9.0.2`)
- `confluent-kafka`: latest `2.13.2` (project pinned `2.13.0`)
- `opentelemetry-sdk`: latest `1.40.0` (project pinned `1.39.1`)

Story guidance: do not upgrade dependencies in Story 1.2; keep scope on gate-input enrichment and AG4 enforcement.

### Project Context Reference

From `artifact/project-context.md`, rules directly affecting this story:

- Hot path must remain deterministic and non-blocking.
- Cold-path diagnosis/LLM remains advisory only; no influence on deterministic gating outcomes.
- Gate order is fixed (`AG0..AG6`) and must not be reordered.
- PAGE remains structurally impossible outside `PROD+TIER_0` through cap framework.
- Full regression quality gate requires `0 skipped tests`.

### References

- `artifact/planning-artifacts/epics.md` (Epic 1, Story 1.2 acceptance criteria)
- `artifact/planning-artifacts/prd.md` (FR6, FR8-FR10, NFR reliability/testability constraints)
- `artifact/planning-artifacts/architecture/project-context-analysis.md`
- `artifact/planning-artifacts/architecture/core-architectural-decisions.md`
- `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
- `artifact/planning-artifacts/architecture/project-structure-boundaries.md`
- `artifact/project-context.md`
- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `src/aiops_triage_pipeline/pipeline/scheduler.py`
- `config/policies/rulebook-v1.yaml`
- `tests/unit/pipeline/stages/test_gating.py`
- `tests/unit/pipeline/test_scheduler.py`

## Story Completion Status

- Story analysis type: exhaustive artifact-based context build
- Previous-story intelligence: applied from Story 1.1 artifact and recent commits
- Git-intelligence dependency: completed
- Web research dependency: completed (PyPI latest-version checks)
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Executed create-story workflow analysis across epics, PRD, architecture shards, project-context, previous story artifact, and recent git history.
- Captured current implementation reality for gate-input assembly and AG4 check flow.
- Performed live package-version checks for latest-tech section.
- Added `enrich_gate_input_context_by_scope` in gating stage and wired scheduler gate-input stage to enrich contexts before collection.
- Updated `collect_gate_inputs_by_scope` to consume enriched context scores while preserving deterministic legacy fallback scoring for non-enriched contexts.
- Ran targeted test suites first, then full Docker-backed regression (`1175 passed`, `0 skipped`).

### Completion Notes List

- Story file created with implementation guardrails and regression protections focused on FR6/FR8/FR9/FR10.
- Scope explicitly constrained to avoid contract changes and out-of-scope audit-persistence work.
- Includes previous-story and git intelligence to prevent rework/regressions.
- ATDD red-phase acceptance tests created for AC1-AC4 and verified failing as expected (4/4 failing).
- ATDD checklist generated at `artifact/test-artifacts/atdd-checklist-1-2-enrich-gate-inputs-and-enforce-ag4-confidence-sustained-rules.md`.
- Implemented deterministic pre-collection gate-input enrichment in scheduler path and kept tri-state sustained (`True|False|None`) scoring semantics.
- Preserved per-finding behavior by storing/consuming scoring payloads by anomaly family, and retained fail-safe fallback (`0.0`/`OBSERVE`) with `gating.scoring.fallback_applied` logging.
- Confirmed AG4 behavior for low-confidence and not-sustained suppression and boundary allow (`0.60` + sustained true), with environment caps remaining final authority.
- Hardened scoring payload parsing to reject non-finite score values and non-boolean `fallback_applied` flags, and normalized reason-code parsing.
- Validation summary:
  - `uv run ruff check src/aiops_triage_pipeline/pipeline/stages/gating.py tests/unit/pipeline/stages/test_gating.py` (pass)
  - `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py` (pass, 129 passed)
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (pass, 1175 passed / 0 skipped)

### File List

- artifact/implementation-artifacts/1-2-enrich-gate-inputs-and-enforce-ag4-confidence-sustained-rules.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/pipeline/stages/gating.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- tests/unit/pipeline/stages/test_gating.py
- tests/unit/pipeline/test_scheduler.py
- tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py
- tests/atdd/fixtures/story_1_2_test_data.py
- tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py
- artifact/test-artifacts/atdd-checklist-1-1-implement-deterministic-confidence-scoring-core.md
- artifact/test-artifacts/atdd-checklist-1-2-enrich-gate-inputs-and-enforce-ag4-confidence-sustained-rules.md
- artifact/test-artifacts/gate-decision-1-2-enrich-gate-inputs-and-enforce-ag4-confidence-sustained-rules.yaml
- artifact/test-artifacts/traceability-matrix.md
- artifact/test-artifacts/traceability-report.md
- artifact/test-artifacts/tmp/tea-atdd-api-tests-2026-03-29T16-20-21.json
- artifact/test-artifacts/tmp/tea-atdd-api-tests-2026-03-29T17-26-18Z.json
- artifact/test-artifacts/tmp/tea-atdd-e2e-tests-2026-03-29T16-20-21.json
- artifact/test-artifacts/tmp/tea-atdd-e2e-tests-2026-03-29T17-26-18Z.json
- artifact/test-artifacts/tmp/tea-atdd-summary-2026-03-29T16-20-21.json
- artifact/test-artifacts/tmp/tea-atdd-summary-2026-03-29T17-26-18Z.json

### Senior Developer Review (AI)

- Reviewer: Sas
- Date: 2026-03-29
- Outcome: Approved (fixed during review)

Findings fixed during this review:

1. [HIGH] `collect_gate_inputs_by_scope` accepted raw non-default context confidence/action without explicit scoring metadata, allowing non-deterministic overrides of hot-path scoring.
   - Fix: Require explicit v1 scoring metadata before consuming context-provided score/action; otherwise recompute deterministically from stage outputs.
   - Evidence: `src/aiops_triage_pipeline/pipeline/stages/gating.py` (`_context_has_explicit_scoring`, `_scoring_result_from_context`) and `tests/unit/pipeline/stages/test_gating.py::test_collect_gate_inputs_by_scope_ignores_unenriched_context_scoring_values`.
2. [MEDIUM] Scoring payload parser accepted boolean values as numeric score fields (`True`/`False` coerced to `1.0/0.0`), which could admit malformed payloads.
   - Fix: Reject booleans in `_to_float`.
   - Evidence: `src/aiops_triage_pipeline/pipeline/stages/gating.py` (`_to_float`).
3. [LOW] Scoring payload parser accepted unknown score versions and blank reason codes.
   - Fix: Enforce score version compatibility (`v1` or absent) and non-empty `score_reason_code` in `_parse_scoring_result_payload`.
   - Evidence: `src/aiops_triage_pipeline/pipeline/stages/gating.py` (`_parse_scoring_result_payload`).
4. [HIGH] Scoring payload parser accepted non-finite numeric values (`NaN`, `inf`, `-inf`), which could clamp to valid scores and bypass intended AG4 behavior.
   - Fix: Reject non-finite numeric values in `_to_float`; malformed payloads now fail closed and are ignored.
   - Evidence: `src/aiops_triage_pipeline/pipeline/stages/gating.py` (`_to_float`) and `tests/unit/pipeline/stages/test_gating.py::test_parse_scoring_result_payload_rejects_non_finite_numeric_values`.
5. [MEDIUM] Scoring payload parser treated non-boolean `fallback_applied` values as truthy/falsey via implicit coercion (`bool(...)`), allowing `"false"` to become `True`.
   - Fix: Add strict boolean parsing (`_to_bool`) and reject malformed payloads with non-boolean fallback flags.
   - Evidence: `src/aiops_triage_pipeline/pipeline/stages/gating.py` (`_to_bool`, `_parse_scoring_result_payload`) and `tests/unit/pipeline/stages/test_gating.py::test_parse_scoring_result_payload_rejects_non_boolean_fallback_flag`.
6. [LOW] Scoring payload parser preserved surrounding whitespace in `score_reason_code`, causing inconsistent reason-code values in downstream audit payloads.
   - Fix: Normalize parsed reason codes with `strip()`.
   - Evidence: `src/aiops_triage_pipeline/pipeline/stages/gating.py` (`_parse_scoring_result_payload`) and `tests/unit/pipeline/stages/test_gating.py::test_parse_scoring_result_payload_normalizes_reason_code`.
7. [MEDIUM] Story `File List` was incomplete versus current git working-tree changes, reducing review traceability.
   - Fix: Synced `File List` to include all currently changed/generated files.
   - Evidence: `artifact/implementation-artifacts/1-2-enrich-gate-inputs-and-enforce-ag4-confidence-sustained-rules.md` (`File List` section).

Validation run after fixes:

- `uv run ruff check src/aiops_triage_pipeline/pipeline/stages/gating.py tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/atdd/fixtures/story_1_2_test_data.py tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py` (pass)
- `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/atdd/test_story_1_1_deterministic_confidence_scoring_core_red_phase.py tests/atdd/test_story_1_2_enrich_gate_inputs_and_enforce_ag4_rules_red_phase.py` (pass, 129 passed)
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (pass, 1175 passed / 0 skipped)

Unresolved findings:

- None (no unresolved Critical/High/Medium/Low findings).

### Change Log

- 2026-03-29: Implemented Story 1.2 gate-input enrichment flow and AG4 confidence/sustained enforcement validation; updated scheduler/gating code paths and coverage, then passed full Docker-backed regression with zero skipped tests.
- 2026-03-29: Completed adversarial code review fixes for deterministic scoring trust boundaries and payload hardening; re-ran targeted + full Docker-backed regression with zero skipped tests, then marked story done.
- 2026-03-29: Completed follow-up adversarial review hardening for non-finite score parsing, strict fallback-flag parsing, and reason-code normalization; synced artifact file list and re-ran full Docker-backed regression (1175 passed / 0 skipped).
