# Story 3.1: Validate Replay Determinism Across Pre-Score and Post-Score Casefiles

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Audit and Compliance Reviewer,
I want replay outputs to remain identical for identical inputs across casefile generations,
so that decision histories remain trustworthy and defensible.

## Acceptance Criteria

1. Given stored casefiles from both pre-release (`confidence=0.0`) and post-release scored records, when `reproduce_gate_decision()` is executed under the same policy version, then replayed `ActionDecisionV1` outputs match expected deterministic results.

2. Given stored casefiles from both generations, when replay validation runs, then backward compatibility is preserved without contract/schema migration.

## Tasks / Subtasks

- [x] Add explicit replay fixture coverage for both casefile generations (AC: 1, 2)
  - [x] Add deterministic test fixtures/builders representing pre-score casefiles (no v1 scoring metadata in `decision_basis`, `diagnosis_confidence` persisted as `0.0`).
  - [x] Add deterministic test fixtures/builders representing post-score casefiles (v1 scoring metadata present with non-zero confidence paths).
  - [x] Ensure fixture payloads use valid `CaseFileTriageV1` hash semantics and rulebook version stamping.

- [x] Extend replay equivalence tests to validate field-for-field determinism across generations (AC: 1)
  - [x] Add/extend tests in `tests/unit/audit/test_decision_reproducibility.py` to replay both fixture generations with `dedupe_store=None` and assert exact `ActionDecisionV1` equality.
  - [x] Keep assertions strict on `final_action`, `gate_rule_ids`, `gate_reason_codes`, `env_cap_applied`, and postmortem fields.
  - [x] Verify mixed-confidence reason-code differentiation remains stable (`LOW_CONFIDENCE` only on true low-confidence paths).

- [x] Validate backward-compatibility behavior explicitly (AC: 2)
  - [x] Add tests proving pre-score records replay correctly without requiring schema migration utilities.
  - [x] Add tests confirming rulebook-version mismatch still raises `ValueError` with actionable guidance.
  - [x] Confirm `CaseFilePolicyVersions` defaults continue to support older payloads without widening contract shapes.

- [x] Preserve audit-trail determinism guarantees while adding replay coverage (AC: 1, 2)
  - [x] Keep `build_audit_trail()` key-set and serialization behavior deterministic for replay-related fields.
  - [x] Confirm policy version fields remain non-empty and replay-relevant fields are still emitted in stable structure.

- [x] Execute required verification gates with zero skipped tests (AC: 1, 2)
  - [x] Run targeted audit replay tests.
  - [x] Run full regression suite with Docker-enabled command and confirm `0 skipped`.

## Dev Notes

### Story Context and Constraints

- Scope is Epic 3 / Story 3.1 (`FR20`): deterministic replay equivalence across pre-score and post-score records.
- This is a brownfield verification story. Do not introduce new contract versions, schema migrations, or replay side channels.
- `reproduce_gate_decision()` must remain deterministic and rulebook-version-locked.
- Replay must continue using `evaluate_rulebook_gates(..., dedupe_store=None)` to avoid AG5 store side effects.
- Maintain frozen-contract posture: enrich behavior and tests, not contract shape changes.

### Current Code Reality (Build on Existing)

- Replay entry point exists in `src/aiops_triage_pipeline/audit/replay.py` and already enforces rulebook-version equality before replay.
- Current unit replay suite (`tests/unit/audit/test_decision_reproducibility.py`) is strong but mostly synthetic-builder driven; this story should lock in explicit pre-score vs post-score generation semantics.
- `CaseFilePolicyVersions` currently includes defaults for `anomaly_detection_policy_version` and `topology_registry_version`, which supports backward compatibility for older payloads that omit newer optional stamps.
- AG4 confidence boundary logic is already centralized in `pipeline/stages/gating.py`; replay tests should assert parity, not re-implement gate logic.

### Technical Requirements

- `reproduce_gate_decision(casefile, rulebook)` must return identical `ActionDecisionV1` output for equivalent inputs and policy version.
- Version mismatch behavior is required and must stay explicit (`ValueError` on mismatch).
- No contract/schema migration is allowed as part of this story.
- Pre-score records (`diagnosis_confidence=0.0`) and post-score records (scored confidence + v1 scoring metadata) must both replay deterministically.
- Replay coverage must include both low-confidence and high-confidence paths to protect reason-code differentiation.

### Architecture Compliance

- Allowed primary change surface:
  - `src/aiops_triage_pipeline/audit/replay.py`
  - `tests/unit/audit/test_decision_reproducibility.py`
  - `tests/fixtures/**` (if fixture files are added)
  - `tests/unit/storage/test_casefile_io.py` (only if required for legacy payload validation support)

- Protected zones (do not modify for this story):
  - `src/aiops_triage_pipeline/contracts/*`
  - `src/aiops_triage_pipeline/diagnosis/*`
  - `src/aiops_triage_pipeline/integrations/*`

- Keep replay logic decoupled from cold-path diagnosis behavior and external integrations.

### Library / Framework Requirements

Date checked: 2026-03-29 (official PyPI JSON APIs).

- `pytest`: `9.0.2` (aligned)
- `pydantic`: `2.12.5` (aligned)
- `pydantic-settings`: `2.13.1` (aligned)
- `testcontainers`: `4.14.2` (project pinned to `4.14.1`; no upgrade required in this story)

Story guidance:
- Do not bundle dependency upgrades into Story 3.1.
- Keep scope focused on replay determinism and compatibility verification.

### File Structure Requirements

Primary implementation/test surface:

- `src/aiops_triage_pipeline/audit/replay.py`
- `tests/unit/audit/test_decision_reproducibility.py`
- Optional fixture paths under `tests/fixtures/` (if file-backed fixtures are introduced)

Potential support surface (only if strictly needed):

- `tests/unit/storage/test_casefile_io.py`

### Testing Requirements

- Add/extend tests to prove replay determinism across:
  - pre-score record generation,
  - post-score record generation,
  - rulebook-version mismatch failure path.

- Maintain strict equality assertions for replayed vs expected `ActionDecisionV1`.

- Required commands:

```bash
uv run pytest -q tests/unit/audit/test_decision_reproducibility.py
```

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

Acceptance gate: full regression must finish with `0 skipped`.

### Project Structure Notes

- Keep replay logic in `audit/` and gate evaluation logic in `pipeline/stages/gating.py`.
- Do not create parallel replay/evaluation modules.
- Keep test organization mirrored under `tests/unit/audit/`.

### Latest Tech Information

- Official package-index checks show current project baseline remains valid for this story.
- No security/compatibility-driven package change is required to implement replay determinism validation.
- Use existing pinned stack and avoid dependency churn.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Preserve deterministic guardrails and replay behavior; do not bypass gate authority.
- Keep contract-first approach; no ad-hoc schema expansion.
- Treat skipped tests as failures and run Docker-backed full regression.
- Keep structured, explicit failure behavior for invariant checks (rulebook mismatch path).

### References

- `artifact/planning-artifacts/epics.md` (Epic 3 / Story 3.1)
- `artifact/planning-artifacts/prd.md` (FR20, NFR-T1/NFR-T2/NFR-T3 context)
- `artifact/planning-artifacts/architecture/project-context-analysis.md` (backward-compatibility constraint)
- `artifact/planning-artifacts/architecture/core-architectural-decisions.md` (D-R6 backward compatibility)
- `artifact/planning-artifacts/architecture/project-structure-boundaries.md` (allowed change surface)
- `artifact/project-context.md`
- `src/aiops_triage_pipeline/audit/replay.py`
- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `src/aiops_triage_pipeline/models/case_file.py`
- `tests/unit/audit/test_decision_reproducibility.py`
- `tests/unit/storage/test_casefile_io.py`
- https://pypi.org/pypi/pytest/json
- https://pypi.org/pypi/pydantic/json
- https://pypi.org/pypi/pydantic-settings/json
- https://pypi.org/pypi/testcontainers/json

## Story Completion Status

- Story analysis type: exhaustive artifact-based context build
- Previous-story intelligence: not applicable (first story in epic)
- Git-intelligence dependency: not applicable (no prior story in epic)
- Web research dependency: completed
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

gpt-5 (Codex)

### Debug Log References

- Loaded sprint status and selected first backlog story in order.
- Loaded epics, PRD, architecture set, project context, replay source, and replay/storage tests.
- Performed latest-version checks from official PyPI JSON endpoints.
- Updated sprint status to `in-progress` before implementation and to `review` on completion.
- Added deterministic pre-score and post-score replay fixture builders and legacy payload replay coverage.
- Executed `uv run pytest -q tests/unit/audit/test_decision_reproducibility.py` (19 passed).
- Executed full regression: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (1205 passed, 0 skipped).
- Executed scoped lint check: `uv run ruff check tests/unit/audit/test_decision_reproducibility.py` (passed).

### Completion Notes List

- Implemented explicit replay fixture builders for pre-score (`diagnosis_confidence=0.0`, no v1 scoring metadata) and post-score (`score_version=v1`) casefile generations.
- Upgraded replay fixtures to use computed `triage_hash` values and explicit rulebook version stamping for deterministic hash semantics.
- Added deterministic replay equivalence assertions across generations with strict field checks for action/result parity and postmortem fields.
- Added backward-compatibility replay coverage for legacy casefile payloads that omit optional policy-version stamps, verifying defaults apply without schema migration utilities.
- Kept mixed-confidence reason-code differentiation and existing audit trail determinism tests intact and passing.

### File List

- artifact/implementation-artifacts/3-1-validate-replay-determinism-across-pre-score-and-post-score-casefiles.md
- artifact/implementation-artifacts/sprint-status.yaml
- tests/unit/audit/test_decision_reproducibility.py

## Change Log

- 2026-03-29: Implemented Story 3.1 replay determinism and backward-compatibility validation updates; story status moved to `review`.
