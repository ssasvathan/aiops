# Story 1.3: Persist Differentiated Confidence and Reason-Code Audit Outcomes

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an Incident Responder,
I want each decision record to include meaningful confidence and reason details,
so that I can distinguish weak-signal silence from valid escalations.

## Acceptance Criteria

1. Given a scope contains at least one PRESENT evidence signal, when `ActionDecisionV1` is written, then `diagnosis_confidence` is non-zero for that decision path and values vary across scopes rather than collapsing to a flat default.
2. Given decisions are persisted for mixed confidence scenarios, when reason codes are assigned, then differentiated codes are emitted (for example high-confidence sustained-peak vs insufficient-evidence low-confidence) and `LOW_CONFIDENCE` is no longer universal across records.

## Tasks / Subtasks

- [ ] Preserve and persist differentiated confidence context from gating through casefile assembly (AC: 1, 2)
  - [ ] Ensure every `GateInputV1` produced by `collect_gate_inputs_by_scope` carries deterministic scoring metadata in `decision_basis` (`score_version`, `base_score`, `sustained_boost`, `peak_boost`, `final_score`, `score_reason_code`, `fallback_applied`).
  - [ ] Ensure fallback scoring path (`SCORING_FALLBACK_APPLIED`) is retained only for genuine scoring failures and not used as a default for normal signal paths.
  - [ ] Ensure scoped anomaly-family scoring payload (`scoring_by_anomaly_family`) remains parseable and deterministic so persisted audit records keep per-signal explanation fidelity.
- [ ] Keep AG4 reason-code semantics explicit and non-universal in finalized decisions (AC: 2)
  - [ ] Preserve `LOW_CONFIDENCE` and `NOT_SUSTAINED` as AG4 failure reasons in `ActionDecisionV1.gate_reason_codes` without schema changes.
  - [ ] Verify success/high-confidence paths do not inject `LOW_CONFIDENCE` by default.
  - [ ] Ensure mixed scenario coverage demonstrates both low-confidence and non-low-confidence outcomes.
- [ ] Maintain deterministic replay and audit-chain compatibility while improving reason-code quality (AC: 1, 2)
  - [ ] Keep frozen contract posture (`GateInputV1`, `ActionDecisionV1`, `CaseFileTriageV1`) and avoid any field additions/removals.
  - [ ] Preserve `reproduce_gate_decision()` behavior and version checks while confirming replay outputs remain deterministic for pre-score and post-score records.
  - [ ] Keep casefile triage hash determinism by preserving stable key/value serialization for decision basis payloads.
- [ ] Expand automated verification for differentiated confidence and reason-code outcomes (AC: 1, 2)
  - [ ] Add/extend stage-level tests proving non-zero confidence for PRESENT-evidence paths and score variance across representative scopes.
  - [ ] Add/extend casefile/audit tests proving persisted records include differentiated reason-code evidence (not universal `LOW_CONFIDENCE`) and stable gate-reason propagation.
  - [ ] Add/extend replay tests proving deterministic parity across mixed confidence records and rulebook-version match constraints.
- [ ] Execute quality gate with zero skipped tests (AC: 1, 2)
  - [ ] Run targeted suites for touched gating/casefile/audit modules.
  - [ ] Run full regression with Docker-backed testcontainers and confirm `0 skipped`.

## Dev Notes

### Story Context and Constraints

- Story scope is FR11, FR18, FR19 only.
- This story builds on Story 1.1 (scoring core) and Story 1.2 (gate-input enrichment + AG4 enforcement).
- Do not introduce contract/schema changes; keep frozen payload compatibility.
- Preserve hot-path determinism and D6 separation (no diagnosis/cold-path influence on confidence outcomes).
- Keep environment and gate authority unchanged: scoring provides candidate context; AG0-AG6 and policy caps remain authoritative.

### Current Code Reality (Build on Existing)

- `collect_gate_inputs_by_scope` in `pipeline/stages/gating.py` already computes and attaches `diagnosis_confidence` plus scoring metadata.
- `evaluate_rulebook_gates` already appends AG4 reason codes (`LOW_CONFIDENCE`, `NOT_SUSTAINED`) into `ActionDecisionV1.gate_reason_codes`.
- `CaseFileTriageV1` already persists both `gate_input` (contains confidence + decision basis) and `action_decision` (contains gate reason codes).
- `audit/replay.py` already re-evaluates gate decisions deterministically with strict rulebook-version matching.
- Primary risk for this story is behavioral regression to flat confidence/reason defaults rather than missing plumbing.

### Technical Requirements

- Preserve deterministic v1 scoring pipeline and metadata fields end-to-end.
- Ensure non-zero `diagnosis_confidence` for PRESENT-evidence paths unless true fallback conditions apply.
- Ensure differentiated scoring reason codes continue to map to score outcomes:
  - `LOW_CONFIDENCE_INSUFFICIENT_EVIDENCE`
  - `MEDIUM_CONFIDENCE_BASELINE`
  - `MEDIUM_CONFIDENCE_SUSTAINED`
  - `MEDIUM_CONFIDENCE_SUSTAINED_PEAK`
  - `HIGH_CONFIDENCE`
  - `HIGH_CONFIDENCE_SUSTAINED`
  - `HIGH_CONFIDENCE_SUSTAINED_PEAK`
  - `SCORING_FALLBACK_APPLIED` (error path only)
- Preserve AG4 gate-reason integrity (`LOW_CONFIDENCE`, `NOT_SUSTAINED`) and deterministic ordering when both checks fail.
- Preserve deterministic serialization and hash stability in casefile assembly.

### Architecture Compliance

- Keep scoring logic module-local to `src/aiops_triage_pipeline/pipeline/stages/gating.py`.
- Do not add new scoring modules or alternate policy engines.
- Do not modify protected zones unless explicitly required and approved:
  - `src/aiops_triage_pipeline/contracts/*`
  - `src/aiops_triage_pipeline/diagnosis/*`
  - `src/aiops_triage_pipeline/integrations/*`
- Preserve replay invariants in `src/aiops_triage_pipeline/audit/replay.py`.
- Preserve casefile write-once and triage-hash integrity behavior in `src/aiops_triage_pipeline/pipeline/stages/casefile.py`.

### Library / Framework Requirements

Latest checks executed on 2026-03-29 from official PyPI package indexes:

- `pydantic` latest: `2.12.5` (project pinned `2.12.5`)
- `pydantic-settings` latest: `2.13.1` (project range `~=2.13.1`)
- `pytest` latest: `9.0.2` (project pinned `9.0.2`)
- `confluent-kafka` latest: `2.13.2` (project pinned `2.13.0`)
- `opentelemetry-sdk` latest: `1.40.0` (project pinned `1.39.1`)

Story guidance: do not perform dependency upgrades in Story 1.3 unless a concrete defect requires it; keep scope on audit-outcome fidelity and deterministic behavior.

### File Structure Requirements

Primary implementation surface:

- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- `src/aiops_triage_pipeline/audit/replay.py`

Primary verification surface:

- `tests/unit/pipeline/stages/test_gating.py`
- `tests/unit/pipeline/stages/test_casefile.py`
- `tests/unit/audit/test_decision_reproducibility.py`

Secondary verification candidates (if behavior impact extends):

- `tests/integration/test_casefile_write.py`
- `tests/integration/cold_path/test_context_reconstruction.py`

Policy/context references:

- `config/policies/rulebook-v1.yaml`
- `artifact/project-context.md`

### Testing Requirements

Required behavioral coverage:

- Non-zero confidence on PRESENT-evidence scenarios (unless scoring fallback is intentionally triggered).
- Differentiated score reason codes across mixed signal quality scenarios (not universal low-confidence labels).
- AG4 reason code correctness and deterministic ordering.
- Casefile persistence of gate input confidence/decision basis + action decision reason codes.
- Replay determinism and rulebook-version mismatch failure behavior.

Required commands:

```bash
uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/stages/test_casefile.py tests/unit/audit/test_decision_reproducibility.py
```

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

Acceptance gate: full regression must finish with `0 skipped`.

### Previous Story Intelligence (Story 1.2)

- Reuse explicit trust boundary from Story 1.2: only consume context-provided scoring when v1 scoring metadata is present and valid.
- Preserve strict payload validation introduced in Story 1.2:
  - reject non-finite numeric scores
  - reject non-boolean `fallback_applied`
  - normalize/validate `score_reason_code`
- Preserve deterministic fallback behavior (`0.0`/`OBSERVE`, `gating.scoring.fallback_applied`) and avoid broadening fallback activation.
- Keep story artifact and sprint tracking discipline aligned with previous stories (`ready-for-dev` -> dev flow -> code review).

### Git Intelligence Summary

Recent relevant commit patterns:

- `45c87fc` (`fix(review)`): tightened scoring payload safety, fallback semantics, and gating tests.
- `33b9007` (`feat(gating)`): implemented deterministic scoring core and regression gate execution.
- `ce24a6c` (`create-story`): established story artifact structure and sprint-status transitions.

Actionable implication for Story 1.3:

- Keep changes localized to gating/casefile/audit modules and mirrored tests.
- Retain deterministic payload validation and no-regression discipline from recent review fixes.

### Latest Tech Information (Step 4 Research)

Research source: official PyPI JSON package metadata (checked 2026-03-29).

- No immediate library upgrade is required to implement Story 1.3.
- Existing pinned/ranged versions already support required scoring/audit behaviors.
- Keep this story focused on deterministic behavior correctness and audit outcome quality, not dependency churn.

### Project Context Reference

Critical rules from `artifact/project-context.md` applied to this story:

- Hot-path gating must remain deterministic and non-blocking.
- Cold-path diagnosis/LLM output must not influence deterministic gate decisions.
- Gate order and AG0-AG6 authority remain fixed.
- Preserve structured logging and correlation context practices.
- Full regression quality gate requires zero skipped tests.

### References

- `artifact/planning-artifacts/epics.md` (Epic 1 / Story 1.3 acceptance criteria)
- `artifact/planning-artifacts/prd.md` (FR11, FR18, FR19; auditability NFRs)
- `artifact/planning-artifacts/architecture/project-context-analysis.md`
- `artifact/planning-artifacts/architecture/core-architectural-decisions.md`
- `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
- `artifact/planning-artifacts/architecture/project-structure-boundaries.md`
- `artifact/project-context.md`
- `artifact/implementation-artifacts/1-2-enrich-gate-inputs-and-enforce-ag4-confidence-sustained-rules.md`
- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- `src/aiops_triage_pipeline/models/case_file.py`
- `src/aiops_triage_pipeline/audit/replay.py`
- `tests/unit/pipeline/stages/test_gating.py`
- `tests/unit/pipeline/stages/test_casefile.py`
- `tests/unit/audit/test_decision_reproducibility.py`
- `config/policies/rulebook-v1.yaml`

## Story Completion Status

- Story analysis type: exhaustive artifact-based context build
- Previous-story intelligence: applied from Story 1.2 artifact and recent review commits
- Git-intelligence dependency: completed
- Web research dependency: completed
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Loaded and analyzed sprint status, epics, PRD, architecture shards, project context, prior story artifacts, and recent commits.
- Confirmed current gating/casefile/audit code paths that already carry confidence and reason-code signals.
- Executed latest-package checks from official PyPI metadata to confirm no dependency-driven blockers.

### Completion Notes List

- Story created as `ready-for-dev` with implementation guardrails focused on FR11/FR18/FR19.
- Scope constrained to deterministic audit-outcome quality and replay-safe persistence; no contract/schema expansion.
- Includes explicit anti-regression guidance from Story 1.2 review findings.

### File List

- artifact/implementation-artifacts/1-3-persist-differentiated-confidence-and-reason-code-audit-outcomes.md
- artifact/implementation-artifacts/sprint-status.yaml
