# Story 5.3: Evidence Sufficiency & Source Topic Gates (AG2, AG3)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,  
I want actions downgraded when evidence is insufficient and PAGE denied for source topic anomalies,  
so that the system never takes high-severity actions based on uncertain evidence or misclassified source-side issues (FR30, FR31).

## Acceptance Criteria

1. **Given** the Rulebook engine reaches AG2 and AG3  
   **When** AG2 evaluates evidence sufficiency  
   **Then** each finding's `evidence_required[]` is checked against `evidence_status_map`.
2. **And** evidence with status `UNKNOWN`/`ABSENT`/`STALE` is treated as insufficient unless the finding explicitly allows it (FR31).
3. **And** insufficient evidence downgrades the action and never assumes `PRESENT`.
4. **When** AG3 evaluates anomaly type  
   **Then** PAGE is denied for `SOURCE_TOPIC` anomalies and final_action caps to `TICKET` or lower depending on env/tier/remaining gates (FR30).
5. **And** `gate_reason_codes` include evidence insufficiency and source-topic denial reasons as applicable.
6. **And** unit tests verify: evidence sufficiency downgrade for each status, SOURCE_TOPIC PAGE denial, and combined AG2+AG3 interaction.

## Tasks / Subtasks

- [x] Task 1: Add explicit finding-level evidence allowance semantics for AG2 (AC: 1, 2, 3, 6)
  - [x] Extend `Finding` contracts used by Stage 6 so a finding can explicitly allow selected non-`PRESENT` statuses for specific evidence keys without weakening default-safe behavior.
  - [x] Keep default behavior strict (`PRESENT` required) when no explicit allowance is set.
  - [x] Keep contract immutability and schema validation patterns consistent with existing frozen Pydantic models.

- [x] Task 2: Implement AG2 sufficiency evaluation refinements in Stage 6 (AC: 1, 2, 3, 5)
  - [x] Update `src/aiops_triage_pipeline/pipeline/stages/gating.py::_ag2_has_insufficient_evidence` to evaluate anomalous findings per selector policy and enforce finding-level explicit allowances.
  - [x] Preserve deterministic behavior and monotonic downward-only action changes via policy effects.
  - [x] Ensure AG2 reason codes are emitted when insufficiency is detected, with no silent pass-through.

- [x] Task 3: Confirm and harden AG3 PAGE-deny semantics for source topics (AC: 4, 5, 6)
  - [x] Keep AG3 behavior constrained to source-topic PAGE denial (`SOURCE_TOPIC` + current action `PAGE`).
  - [x] Ensure AG3 cap is applied without escalation and composes correctly with AG1/AG2/AG4 ordering.
  - [x] Verify reason code behavior when AG2 and AG3 both trigger in the same evaluation path.

- [x] Task 4: Expand AG2/AG3 regression coverage (AC: 1, 2, 3, 4, 5, 6)
  - [x] Extend `tests/unit/pipeline/stages/test_gating.py` with AG2 matrix tests across `PRESENT`, `UNKNOWN`, `ABSENT`, `STALE`, including explicit-allowance cases.
  - [x] Add AG3-focused tests for SOURCE_TOPIC PAGE denial with env/tier combinations where PAGE would otherwise be possible.
  - [x] Add combined AG2+AG3 interaction tests asserting deterministic gate ordering and reason code aggregation.
  - [x] Extend `tests/unit/pipeline/test_scheduler.py` for end-to-end stage-cycle assertions covering AG2/AG3 outcomes by scope.

- [x] Task 5: Run quality gates for Story 5.3
  - [x] `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py`
  - [x] `uv run ruff check`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-3-evidence-sufficiency-and-source-topic-gates-ag2-ag3`
  - Story ID: `5.3`
- Epic context: Epic 5 implements deterministic safety gating and action execution (FR27-FR35, FR43-FR45, FR51).
- Prior stories:
  - Story 5.1 established the AG0-AG6 engine and deterministic sequencing.
  - Story 5.2 finalized AG1 environment/tier cap semantics and strengthened guardrails.

### Technical Requirements

- Enforce FR30/FR31 exactly:
  - AG2 evaluates each selected finding's `evidence_required[]` against `evidence_status_map`.
  - `UNKNOWN`/`ABSENT`/`STALE` are insufficient by default.
  - Any exception to default insufficiency must be explicit at finding level (no implicit assumptions).
  - AG3 denies PAGE for `SOURCE_TOPIC` anomalies; final action remains `TICKET` or lower and can be further reduced by later gates.
- Preserve gate order and deterministic outcomes:
  - `AG0 -> AG1 -> AG2 -> AG3 -> AG4 -> AG5 -> AG6`
  - no gate may escalate action.
- Keep Stage 6 pure-computation except AG5 dedupe seam.

### Architecture Compliance

- Keep AG2/AG3 logic in `src/aiops_triage_pipeline/pipeline/stages/gating.py`.
- Keep policy-driven behavior anchored to `config/policies/rulebook-v1.yaml`.
- Preserve contract-first boundary:
  - input via `GateInputV1`/`Finding`
  - output via `ActionDecisionV1`
- Maintain UNKNOWN-not-zero semantics end-to-end; do not coerce missing evidence to `PRESENT` or numeric zero.

### Library / Framework Requirements

- No new dependencies required for this story.
- Continue using existing pinned stack and project testing/linting tooling.
- Preserve Python 3.13 typing style and frozen Pydantic model patterns.

### File Structure Requirements

- Primary implementation files:
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `src/aiops_triage_pipeline/contracts/gate_input.py`
  - `src/aiops_triage_pipeline/models/anomaly.py` (if finding metadata is propagated from anomaly stage)
  - `src/aiops_triage_pipeline/pipeline/stages/anomaly.py` (if finding metadata needs construction updates)
- Policy/contract alignment checks:
  - `config/policies/rulebook-v1.yaml`
  - `src/aiops_triage_pipeline/contracts/rulebook.py`
- Test targets:
  - `tests/unit/pipeline/stages/test_gating.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/contracts/test_policy_models.py`

### Testing Requirements

- Required AG2 coverage:
  - downgrade on each insufficient status (`UNKNOWN`, `ABSENT`, `STALE`)
  - no downgrade on `PRESENT`
  - explicit finding-level allowance honored only where defined
  - anomalous-only selector and primary-preference behavior preserved
- Required AG3 coverage:
  - PAGE denied for `SOURCE_TOPIC`
  - no denial for non-source topic roles
  - deterministic interaction with AG1/AG2/AG4 cap behavior
- Scheduler-level coverage:
  - by-scope decision outputs reflect AG2/AG3 changes and reason codes.

### Previous Story Intelligence

- Reuse Story 5.1/5.2 Stage 6 patterns:
  - strict order validation
  - monotonic reduction helper
  - explicit policy injection in scheduler helpers
  - no hidden file I/O in decision cycle
- Keep AG1 semantics unchanged while implementing AG2/AG3 refinements.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Rulebook deterministic gates are authoritative for action decisions.
- PAGE must remain structurally impossible outside `PROD + TIER_0` and must also be denied on `SOURCE_TOPIC` via AG3.
- Preserve UNKNOWN semantics; never silently inflate confidence or action.
- High-risk gating/contract changes require targeted regression verification plus full no-skip suite.

### Project Structure Notes

- Existing repository structure already supports this story:
  - Stage 6 evaluator in `pipeline/stages/gating.py`
  - contracts under `contracts/`
  - scheduler orchestration in `pipeline/scheduler.py`
  - unit tests in `tests/unit/pipeline/` and `tests/unit/contracts/`
- No UX artifacts are required for this backend gating story.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.3: Evidence Sufficiency & Source Topic Gates (AG2, AG3)`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR30, FR31)]
- [Source: `artifact/planning-artifacts/prd/glossary-terminology.md` (AG2, AG3, evidence_status_map, topic_role)]
- [Source: `artifact/planning-artifacts/architecture.md` (Action Gating FR27-FR35 mapping and Stage 6 placement)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/5-1-rulebook-gate-engine-ag0-ag6-sequential-evaluation.md`]
- [Source: `artifact/implementation-artifacts/5-2-environment-and-criticality-tier-caps-ag1.md`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py`]
- [Source: `src/aiops_triage_pipeline/contracts/rulebook.py`]
- [Source: `tests/unit/pipeline/stages/test_gating.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]

### Story Completion Status

- Story context generated for Epic 5 Story 5.3.
- Story file: `artifact/implementation-artifacts/5-3-evidence-sufficiency-and-source-topic-gates-ag2-ag3.md`.
- Story status set to: `done`.
- Completion note: Story implementation and senior review follow-up fixes are complete.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Dev workflow config: `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`
- Story source: `artifact/implementation-artifacts/5-3-evidence-sufficiency-and-source-topic-gates-ag2-ag3.md`
- Implementation references:
  - `src/aiops_triage_pipeline/contracts/gate_input.py`
  - `src/aiops_triage_pipeline/models/anomaly.py`
  - `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `tests/unit/contracts/test_frozen_models.py`
  - `tests/unit/pipeline/stages/test_anomaly.py`
  - `tests/unit/pipeline/stages/test_gating.py`
  - `tests/unit/pipeline/test_scheduler.py`
- Validation commands:
  - `uv run pytest -q tests/unit/contracts/test_frozen_models.py tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/stages/test_anomaly.py`
  - `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py`
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Implemented finding-level explicit non-`PRESENT` evidence allowances by extending `Finding` and `AnomalyFinding` contracts with `allowed_non_present_statuses_by_evidence`.
- Updated anomaly-to-gate finding conversion to preserve allowance metadata into Stage 6 `GateInputV1`.
- Refined AG2 evidence sufficiency evaluation to treat missing evidence keys as `UNKNOWN` by default while honoring explicit per-finding allowances.
- Added strict schema invariants for per-finding allowance maps:
  - keys must exist in `evidence_required`
  - values can only include `UNKNOWN`/`ABSENT`/`STALE`
  - nested allowance maps are frozen after validation.
- Added AG2/AG3 regression coverage in Stage 6 tests (status matrix, explicit allowance behavior, SOURCE_TOPIC PAGE denial, and deterministic AG2->AG3 interaction).
- Added scheduler-level AG2/AG3 decision tests and anomaly-stage propagation tests for the new allowance metadata.
- Added negative contract tests to prevent regression on invalid allowance maps and nested mutability.
- Quality gates passed:
  - Focused suite: `158 passed`
  - Ruff: `All checks passed`
  - Full regression (Docker): `457 passed`, `0 skipped`

### File List

- `artifact/implementation-artifacts/sprint-status.yaml`
- `artifact/implementation-artifacts/5-3-evidence-sufficiency-and-source-topic-gates-ag2-ag3.md`
- `src/aiops_triage_pipeline/contracts/gate_input.py`
- `src/aiops_triage_pipeline/models/anomaly.py`
- `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `tests/unit/contracts/test_frozen_models.py`
- `tests/unit/pipeline/stages/test_anomaly.py`
- `tests/unit/pipeline/stages/test_gating.py`
- `tests/unit/pipeline/test_scheduler.py`

## Senior Developer Review (AI)

- Review date: 2026-03-06
- Outcome: Changes requested and fixed in this story iteration.
- Findings addressed:
  - HIGH: `allowed_non_present_statuses_by_evidence` nested mutability bypassed frozen-model guarantees.
  - MEDIUM: allowance-map schema accepted invalid keys and `PRESENT` status.
  - MEDIUM: missing negative tests for the above contract invariants.
  - LOW: story metadata inconsistency (`ready-for-dev` note while status was `review`).
- Fix verification:
  - `uv run pytest -q tests/unit/contracts/test_frozen_models.py tests/unit/pipeline/stages/test_anomaly.py tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py` → `158 passed`
  - `uv run ruff check` → `All checks passed`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` → `457 passed`, `0 skipped`

## Change Log

- 2026-03-06: Validated and expanded Story 5.3 from placeholder into a complete implementation-ready story document with AG2/AG3 guardrails and test plan.
- 2026-03-06: Implemented Story 5.3 AG2/AG3 behavior, added finding-level explicit evidence-status allowances, expanded Stage 6/scheduler/anomaly test coverage, and passed full no-skip regression (`451 passed`).
- 2026-03-06: Completed senior review follow-up fixes for contract immutability and allowance-map validation, added negative regression tests, and reran full no-skip regression (`457 passed`, `0 skipped`).
