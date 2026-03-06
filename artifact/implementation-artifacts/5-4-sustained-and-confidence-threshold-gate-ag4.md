# Story 5.4: Sustained & Confidence Threshold Gate (AG4)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,  
I want PAGE and TICKET actions to require `sustained=true` and `confidence >= 0.6`,  
so that only persistent, high-confidence anomalies trigger disruptive actions (FR32).

## Acceptance Criteria

1. **Given** the Rulebook engine reaches AG4  
   **When** sustained status and confidence are evaluated  
   **Then** PAGE requires `sustained=true` **and** `confidence >= 0.6`.
2. **And** TICKET requires `sustained=true` **and** `confidence >= 0.6`.
3. **And** if either condition fails, the action is downgraded to NOTIFY or lower.
4. **And** `gate_reason_codes` record the specific AG4 failure (`NOT_SUSTAINED`, `LOW_CONFIDENCE`, or both).
5. **And** unit tests verify: sustained=false downgrades, confidence < 0.6 downgrades, both conditions failing, boundary case at confidence = 0.6 exactly.

## Tasks / Subtasks

- [x] Task 1: Refine AG4 evaluation semantics in Stage 6 (AC: 1, 2, 3, 4)
  - [x] Update `src/aiops_triage_pipeline/pipeline/stages/gating.py` AG4 logic to evaluate sustained and confidence checks explicitly and deterministically.
  - [x] Ensure AG4 only downgrades (never escalates) and composes correctly after AG1/AG2/AG3 reductions.
  - [x] Emit granular AG4 reason codes for each failed condition (`NOT_SUSTAINED`, `LOW_CONFIDENCE`) with deterministic ordering when both fail.

- [x] Task 2: Align Rulebook policy artifact with AG4 reason-code requirements (AC: 4)
  - [x] Update `config/policies/rulebook-v1.yaml` AG4 `effect.on_fail` reason-code strategy so policy and implementation remain consistent with acceptance criteria.
  - [x] Preserve existing minimum confidence threshold (`0.6`) and sustained requirement in policy checks.

- [x] Task 3: Expand AG4-focused unit coverage in Stage 6 tests (AC: 1, 2, 3, 4, 5)
  - [x] Extend `tests/unit/pipeline/stages/test_gating.py` with explicit AG4 tests for: not sustained only, low confidence only, both failures, and confidence boundary at exactly `0.6`.
  - [x] Assert both `final_action` behavior and precise AG4 reason-code outputs.
  - [x] Verify AG4 behavior remains deterministic with unchanged gate ordering (`AG0..AG6`).

- [x] Task 4: Add scheduler-level AG4 regression checks (AC: 3, 4, 5)
  - [x] Extend `tests/unit/pipeline/test_scheduler.py` to assert AG4 outcomes are surfaced correctly through `run_gate_decision_stage_cycle(...)` by scope.
  - [x] Verify AG4 interacts safely with prior AG2/AG3 behavior and does not regress dedupe/postmortem downstream semantics.

- [x] Task 5: Run quality gates for Story 5.4
  - [x] `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py`
  - [x] `uv run ruff check`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-4-sustained-and-confidence-threshold-gate-ag4`
  - Story ID: `5.4`
- Epic context: Epic 5 implements deterministic safety gating and action execution (FR27-FR35, FR43-FR45, FR51).
- Story objective: enforce FR32 threshold semantics so high-urgency actions require both persistent anomaly state and sufficient confidence before action execution.
- Cross-story continuity in Epic 5:
  - Story 5.1 established deterministic AG0-AG6 sequencing and monotonic reduction.
  - Story 5.2 hardened AG1 environment/tier cap policy and validation.
  - Story 5.3 refined AG2/AG3 evidence and source-topic guardrails.
  - Story 5.4 now tightens AG4 threshold behavior and audit trace precision.

### Technical Requirements

- Enforce FR32 exactly:
  - PAGE requires `sustained=true` and `diagnosis_confidence >= 0.6`.
  - TICKET requires `sustained=true` and `diagnosis_confidence >= 0.6`.
- Keep deterministic gate ordering unchanged: `AG0 -> AG1 -> AG2 -> AG3 -> AG4 -> AG5 -> AG6`.
- Preserve monotonic action safety:
  - AG4 may only keep or reduce action severity.
  - AG4 must never escalate action, directly or indirectly.
- Emit AG4-specific failure diagnostics suitable for audit/replay:
  - `NOT_SUSTAINED` when sustained requirement fails.
  - `LOW_CONFIDENCE` when confidence threshold fails.
  - both codes when both conditions fail.
- Maintain explicit boundary behavior:
  - confidence exactly `0.6` satisfies threshold (`>= 0.6`).
- Keep Stage 6 computation-only and policy-driven:
  - no external I/O in AG4 evaluation path.

### Architecture Compliance

- Keep AG4 logic inside Stage 6 evaluator:
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- Keep policy source of truth in Rulebook artifact:
  - `config/policies/rulebook-v1.yaml`
- Preserve contract boundary:
  - input via `GateInputV1`
  - output via `ActionDecisionV1`
- Maintain architecture invariants from planning docs:
  - deterministic rulebook remains authoritative.
  - UNKNOWN-not-zero propagation remains intact across evidence -> peak -> sustained/confidence -> gating.
  - AG4 changes must not weaken AG1/AG2/AG3 guardrails or AG5 degraded-mode safety.

### Library / Framework Requirements

Verification date: 2026-03-06.

- No new dependencies are required for Story 5.4.
- Keep implementation aligned with current project baseline from architecture/project-context:
  - Python `>=3.13`
  - `pydantic==2.12.5`
  - `pytest==9.0.2`
  - `redis==7.2.1`
- Datetime guidance remains: prefer aware UTC datetimes; avoid introducing `datetime.utcnow()` usage (deprecated in Python 3.12+ docs).

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `config/policies/rulebook-v1.yaml`
- Contract/policy alignment checks:
  - `src/aiops_triage_pipeline/contracts/rulebook.py`
  - `src/aiops_triage_pipeline/contracts/gate_input.py`
  - `src/aiops_triage_pipeline/contracts/action_decision.py`
- Test targets:
  - `tests/unit/pipeline/stages/test_gating.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/contracts/test_policy_models.py`

### Testing Requirements

- Mandatory AG4 unit coverage:
  - sustained=false with high confidence -> downgrade + `NOT_SUSTAINED`
  - sustained=true with confidence < 0.6 -> downgrade + `LOW_CONFIDENCE`
  - sustained=false with confidence < 0.6 -> downgrade + both AG4 reason codes
  - sustained=true with confidence exactly 0.6 -> no AG4 downgrade from threshold check
- Integration-of-gates regression expectations:
  - AG4 behavior remains deterministic with prior AG2/AG3 outcomes.
  - AG4 changes do not break AG5 dedupe safe-cap behavior.
  - AG4 changes do not alter AG6 postmortem-only semantics.
- Quality gate expectation:
  - full regression must complete with zero skipped tests.

### Previous Story Intelligence

From Story 5.3 (`artifact/implementation-artifacts/5-3-evidence-sufficiency-and-source-topic-gates-ag2-ag3.md`):

- Reuse Stage 6 patterns already hardened in 5.3:
  - strict deterministic gate ordering and monotonic action reduction helper.
  - explicit reason-code assertions in unit tests.
  - scheduler-level by-scope decision assertions.
- Avoid regressions introduced by AG2 enhancements:
  - AG2 now honors finding-level explicit non-`PRESENT` evidence allowances.
  - AG4 must operate on already-reduced action state after AG2/AG3, not on `proposed_action` assumptions.
- Keep story metadata discipline learned in 5.3:
  - avoid status drift between story file and sprint-status tracking.

### Git Intelligence Summary

Recent commits (most recent first):

- `f3e3144` Story 5.3 implementation + review fixes
- `44caa7a` Story 5.2 policy validation hardening
- `26382be` Story 5.1 adversarial review remediation
- `50e998d` zero-skip regression policy enforcement
- `956e102` Story 5.1 initial implementation

Actionable patterns for Story 5.4:

- Keep change set concentrated in Stage 6 + policy + targeted tests.
- Pair each gate behavior change with explicit unit tests in `test_gating.py` and scheduler assertions in `test_scheduler.py`.
- Preserve no-skip full-suite discipline before marking implementation complete.

### Latest Tech Information

Verification date: 2026-03-06.

- `pytest` current stable remains `9.0.2` (project pin already aligned).
- `pydantic` current stable remains `2.12.5` (project pin already aligned).
- `redis` (redis-py) current stable remains `7.2.1` (project pin already aligned).
- Python docs continue to mark `datetime.utcnow()` as deprecated in favor of aware UTC datetime APIs.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Deterministic gate engine is authoritative for action decisions.
- PAGE must remain structurally impossible outside `PROD + TIER_0` and must continue to satisfy downstream safety gates.
- Preserve UNKNOWN semantics; do not inflate confidence or bypass downgrade logic.
- Keep cross-cutting logic centralized (no parallel gate evaluators).
- High-risk gating changes require targeted regressions plus full no-skip suite verification.

### Project Structure Notes

- Existing code layout directly supports Story 5.4:
  - Stage 6 evaluator: `pipeline/stages/gating.py`
  - policy artifacts: `config/policies/`
  - scheduler orchestration: `pipeline/scheduler.py`
  - tests: `tests/unit/pipeline/`, `tests/unit/contracts/`
- No UX artifacts are required for this backend gating story.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.4: Sustained & Confidence Threshold Gate (AG4)`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR27, FR32)]
- [Source: `artifact/planning-artifacts/prd/glossary-terminology.md` (AG4, sustained, confidence, UNKNOWN-not-zero)]
- [Source: `artifact/planning-artifacts/architecture.md` (Action Gating mapping and Stage 6 placement)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/5-1-rulebook-gate-engine-ag0-ag6-sequential-evaluation.md`]
- [Source: `artifact/implementation-artifacts/5-2-environment-and-criticality-tier-caps-ag1.md`]
- [Source: `artifact/implementation-artifacts/5-3-evidence-sufficiency-and-source-topic-gates-ag2-ag3.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `tests/unit/pipeline/stages/test_gating.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: `https://pypi.org/project/pytest/`]
- [Source: `https://docs.pytest.org/en/stable/changelog.html`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://pypi.org/project/redis/`]
- [Source: `https://docs.python.org/3/library/datetime.html`]

### Story Completion Status

- Story context generated for Epic 5 Story 5.4.
- Story file: `artifact/implementation-artifacts/5-4-sustained-and-confidence-threshold-gate-ag4.md`.
- Story status set to: `ready-for-dev`.
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
- Core planning artifacts:
  - `artifact/planning-artifacts/epics.md`
  - `artifact/planning-artifacts/architecture.md`
  - `artifact/planning-artifacts/prd/functional-requirements.md`
  - `artifact/planning-artifacts/prd/glossary-terminology.md`
  - `artifact/project-context.md`
- Implementation + validation commands:
  - `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py -k "ag4"` (red phase)
  - `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py`
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Story 5.4 context created from next backlog item in sprint status.
- Epic 5 continuity and prior-story learnings integrated to prevent regressions.
- AG4-specific implementation guardrails and test expectations documented for deterministic execution.
- Implemented deterministic AG4 failure evaluation in Stage 6 for high-urgency actions only (`PAGE`/`TICKET`) using policy checks.
- Added granular AG4 reason-code emission with deterministic ordering: `LOW_CONFIDENCE`, `NOT_SUSTAINED`.
- Updated rulebook policy AG4 checks with `reason_code_on_fail` metadata and retained threshold/sustained constraints.
- Added AG4 regression coverage in stage-level and scheduler-level tests, including confidence boundary `0.6`.
- Verified quality gates: targeted pytest suite, Ruff lint, and full Docker-backed regression with zero skips (`464 passed`).

### File List

- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `config/policies/rulebook-v1.yaml`
- `tests/unit/pipeline/stages/test_gating.py`
- `tests/unit/pipeline/test_scheduler.py`
- `artifact/implementation-artifacts/5-4-sustained-and-confidence-threshold-gate-ag4.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-03-06: Created Story 5.4 context document with AG4 implementation guardrails, architecture constraints, test plan, and latest-technology checks.
- 2026-03-06: Implemented Story 5.4 AG4 sustained/confidence gate behavior with granular reason codes, added AG4 regression tests, passed lint, and completed full no-skip regression run.
