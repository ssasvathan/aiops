# Story 1.1: Implement Deterministic Confidence Scoring Core

Status: ready-for-dev

## Story

As a Platform SRE,
I want confidence scores to be computed deterministically from evidence, sustained, and peak inputs,
so that gate decisions are explainable and repeatable.

## Acceptance Criteria

1. Given evidence status counts and sustained/peak context are available for a scope, when the scoring function executes in the gating stage, then it computes `diagnosis_confidence` in the `0.0..1.0` range using tiered logic and derives a candidate `proposed_action` from the same inputs.
2. Given `is_sustained=None` is present from degraded coordination context, when tier amplifiers are evaluated, then sustained amplification is not applied and behavior remains deterministic for identical inputs.
3. Given the scoring function raises an internal exception, when gating continues, then output falls back to `diagnosis_confidence=0.0` and `proposed_action=OBSERVE` and processing continues without unhandled exception.

## Tasks / Subtasks

- [ ] Implement deterministic scoring in `pipeline/stages/gating.py` (AC: 1, 2, 3)
  - [ ] Add module-local v1 constants with `SCORE_V1_` prefix for base weighting, sustained amplifier, peak amplifier, and action bands.
  - [ ] Add private helpers (`_score_*`, `_derive_*`) to compute base score, sustained boost, peak boost, final clamp to `[0.0, 1.0]`, and candidate action mapping (`<0.6=OBSERVE`, `0.6-<0.85=TICKET`, `>=0.85=PAGE`).
  - [ ] Keep scoring function pure and deterministic (no network, file, Redis, or time dependency).
- [ ] Integrate scoring into gate-input assembly before `GateInputV1` materialization (AC: 1, 2)
  - [ ] In `collect_gate_inputs_by_scope`, derive scoring inputs from `evidence_status_map`, `peak_output.peak_context_by_scope`, and sustained state.
  - [ ] Preserve three-state sustained semantics for scoring (`True | False | None`) before converting `GateInputV1.sustained` to boolean.
  - [ ] Populate `GateInputV1.diagnosis_confidence` and `GateInputV1.proposed_action` from scoring output, then apply existing `max_safe_action` cap logic.
- [ ] Add deterministic scoring metadata and fallback marker for audit/debug clarity (AC: 1, 3)
  - [ ] Add stable `decision_basis` keys: `score_version`, `base_score`, `sustained_boost`, `peak_boost`, `final_score`, `score_reason_code`, `fallback_applied`.
  - [ ] On scoring exception, log warning with `event_type="gating.scoring.fallback_applied"` and produce deterministic fallback payload.
- [ ] Expand unit tests to cover scoring boundaries and fallback behavior (AC: 1, 2, 3)
  - [ ] Add AG4 boundary tests explicitly tied to score derivation (`0.59` capped, `0.60` passes, high-confidence sustained+peak reaches high-urgency candidate band).
  - [ ] Add `is_sustained=None` scoring-path test to verify no sustained boost and deterministic output.
  - [ ] Add scoring exception-path test to verify `0.0/OBSERVE` fallback and no unhandled exception.
- [ ] Run quality gates with zero skipped tests (AC: 1, 2, 3)
  - [ ] Run targeted unit tests for `gating.py` and scheduler gate-input flow.
  - [ ] Run full regression with Docker-backed testcontainers and confirm `0 skipped`.

## Dev Notes

### Story Context and Constraints

- This story only covers FR1, FR2, FR3, FR4, FR5, FR7 and must not implement AG4 policy changes beyond feeding correct inputs.
- Existing AG4 threshold and reason-code logic already exists in `config/policies/rulebook-v1.yaml`; this story must supply correct confidence/action inputs to that existing gate logic.
- No contract/schema changes are allowed. `GateInputV1` already has `proposed_action` and `diagnosis_confidence`.

### Current Code Reality (must build on this)

- `GateInputContext` defaults to `proposed_action=OBSERVE` and `diagnosis_confidence=0.0` in `pipeline/stages/gating.py`.
- Topology stage currently creates `GateInputContext` without scoring; scoring must be computed later in gate-input assembly (`collect_gate_inputs_by_scope`) using evidence+peak+sustained context.
- `collect_gate_inputs_by_scope` currently forwards context values directly and sets sustained as boolean from Stage 2 sustained status; scoring integration belongs here to avoid topology coupling and to keep hot-path deterministic.

### Architecture Compliance Guardrails

- Keep scoring implementation module-local in `src/aiops_triage_pipeline/pipeline/stages/gating.py`; do not create `scoring.py` or new shared utility module.
- Do not import from `diagnosis/` package (D6 hot/cold separation invariant).
- Preserve action-authority chain: scoring emits candidate action only; AG0-AG6 plus env/tier caps remain final authority.
- Preserve fail-safe semantics: any scoring failure must degrade to `0.0/OBSERVE`.
- Preserve UNKNOWN semantics: UNKNOWN evidence must be weighted lower than PRESENT, not collapsed to PRESENT and not coerced to hard zero.

### Library/Framework Requirements

- Use existing stack and pins from `pyproject.toml`; no dependency upgrades in this story unless explicitly approved in scope.
- Keep Python 3.13 typing style (`X | None`, built-in generics).
- Use existing structured logging (`structlog`) and event naming conventions.

### File Structure Requirements

- Primary implementation file: `src/aiops_triage_pipeline/pipeline/stages/gating.py`.
- Primary unit tests: `tests/unit/pipeline/stages/test_gating.py`.
- Secondary integration/wiring assertions (if touched): `tests/unit/pipeline/test_scheduler.py`.
- Do not modify protected zones for this story:
  - `src/aiops_triage_pipeline/contracts/*`
  - `src/aiops_triage_pipeline/diagnosis/*`
  - `src/aiops_triage_pipeline/integrations/*`

### Testing Requirements

- Required targeted tests:
  - Deterministic score calculation from evidence+sustained+peak inputs.
  - Boundary behavior (`0.59`, `0.60`, high-confidence sustained+peak).
  - `is_sustained=None` conservative handling.
  - Exception fallback path (`0.0/OBSERVE`) with no unhandled raise.
- Required regression command (must produce zero skipped tests):

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

### Latest Tech Information (Step 4 Research)

Latest package versions checked from PyPI JSON endpoints on 2026-03-29:

- `pydantic`: latest `2.12.5` (project already pinned to `2.12.5`).
- `pydantic-settings`: latest `2.13.1` (project range `~=2.13.1` already aligned).
- `pytest`: latest `9.0.2` (project already pinned to `9.0.2`).
- `confluent-kafka`: latest `2.13.2` (project pinned `2.13.0`; no upgrade required for this story).
- `opentelemetry-sdk`: latest `1.40.0` (project pinned `1.39.1`; no upgrade required for this story).

Implementation guidance for this story: keep dependency set unchanged; focus on deterministic gating logic only.

### Project Context Reference

Critical project-context rules that apply directly:

- Hot path must stay deterministic and non-blocking.
- Cold-path LLM output is advisory and must not influence deterministic gating decisions.
- Gate order and policy authority are fixed; no gate-order mutation.
- Structured logging with correlation context must be preserved.
- Full regression quality gate is `0 skipped tests`.

### References

- `artifact/planning-artifacts/epics.md` (Epic 1, Story 1.1, ACs)
- `artifact/planning-artifacts/prd.md` (Functional requirements FR1-FR7; NFR reliability/testability constraints)
- `artifact/planning-artifacts/architecture/core-architectural-decisions.md` (D-R1..D-R6)
- `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md` (naming, structure, fallback, metadata keys)
- `artifact/planning-artifacts/architecture/project-context-analysis.md` (D6 invariant, UNKNOWN semantics, verification architecture)
- `artifact/planning-artifacts/architecture/project-structure-boundaries.md` (allowed/protected surfaces)
- `artifact/project-context.md` (technology pins, testing gate, coding invariants)
- `config/policies/rulebook-v1.yaml` (AG4 threshold and reason-code expectations)
- `src/aiops_triage_pipeline/pipeline/stages/gating.py` (current gate-input assembly/evaluation path)
- `src/aiops_triage_pipeline/pipeline/stages/topology.py` (current context construction path)
- `tests/unit/pipeline/stages/test_gating.py` (existing gate behavior tests)

## Story Completion Status

- Story analysis type: exhaustive artifact-based context build
- Previous-story intelligence: not applicable (first story in epic)
- Git-intelligence dependency: skipped (condition not met: no previous story)
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Artifact discovery + analysis executed across epics, PRD, architecture shards, project-context, and code/test surfaces.
- Latest package version snapshot gathered from official PyPI JSON APIs.

### Completion Notes List

- Story created as `ready-for-dev` with implementation guardrails and explicit no-regression boundaries.
- Scope strictly constrained to deterministic scoring core (Story 1.1), no contract/schema changes.

### File List

- artifact/implementation-artifacts/1-1-implement-deterministic-confidence-scoring-core.md
