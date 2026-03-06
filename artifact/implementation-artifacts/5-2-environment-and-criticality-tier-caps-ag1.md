# Story 5.2: Environment & Criticality Tier Caps (AG1)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,  
I want actions capped by environment and criticality tier,  
so that local/dev/uat environments cannot trigger production-level actions and only TIER_0 streams in prod are PAGE-eligible (FR28, FR29).

## Acceptance Criteria

1. **Given** the Rulebook engine reaches AG1  
   **When** environment and tier caps are evaluated  
   **Then** local environment caps to OBSERVE maximum (FR28).
2. **And** dev environment caps to NOTIFY maximum (FR28).
3. **And** uat environment caps to TICKET maximum (FR28).
4. **And** prod environment: TIER_0 = PAGE eligible (if all other gates pass), TIER_1 = TICKET, TIER_2/UNKNOWN = NOTIFY (FR29).
5. **And** the `env_cap_applied` field in `ActionDecision.v1` reflects which cap was applied.
6. **And** `gate_rule_ids` and `gate_reason_codes` record the AG1 evaluation.
7. **And** unit tests verify: each environment cap, each prod tier cap, UNKNOWN tier treated as TIER_2.

## Tasks / Subtasks

- [ ] Task 1: Align AG1 environment cap policy artifacts with FR28/FR29 (AC: 1, 2, 3, 4, 7)
  - [ ] Update `config/policies/rulebook-v1.yaml` `caps.max_action_by_env` to align with requirements: `local=OBSERVE`, `dev=NOTIFY`, `uat=TICKET`, `prod=PAGE`.
  - [ ] Preserve compatibility only where required during migration (legacy `stage` mapping), but keep `Environment` enum (`local|dev|uat|prod`) as source of truth.
  - [ ] Ensure policy-level prod tier map remains `TIER_0=PAGE`, `TIER_1=TICKET`, `TIER_2=NOTIFY`, `UNKNOWN=NOTIFY`.

- [ ] Task 2: Harden AG1 evaluator behavior in Stage 6 (AC: 1, 2, 3, 4, 5, 6)
  - [ ] In `src/aiops_triage_pipeline/pipeline/stages/gating.py::_evaluate_ag1`, keep evaluation order deterministic: environment cap first, prod tier cap second.
  - [ ] Keep action changes monotonic downward only (`OBSERVE < NOTIFY < TICKET < PAGE`) with no escalation path.
  - [ ] Set `env_cap_applied=True` only when environment cap reduced the action (not when only tier cap reduced it).
  - [ ] Ensure AG1 reason codes are appended when either env or tier cap reduces action.
  - [ ] Keep AG1 behavior pure computation (no external I/O).

- [ ] Task 3: Add AG1-focused regression coverage (AC: 1, 2, 3, 4, 5, 6, 7)
  - [ ] Extend `tests/unit/pipeline/stages/test_gating.py` with explicit matrix tests for `local`, `dev`, `uat`, `prod` + prod tier variants (`TIER_0`, `TIER_1`, `TIER_2`, `UNKNOWN`).
  - [ ] Verify `env_cap_applied` semantics for env-only cap vs tier-only cap.
  - [ ] Verify AG1 reason code inclusion and ordered gate IDs in all cap scenarios.
  - [ ] Keep/adjust migration-compatibility test for `uat` fallback behavior if legacy `stage` policy entries still exist.

- [ ] Task 4: Verify scheduler integration surfaces AG1 outcomes correctly (AC: 5, 6, 7)
  - [ ] Extend `tests/unit/pipeline/test_scheduler.py` to assert AG1 decision outputs are returned by scope with explicit rulebook input.
  - [ ] Keep explicit `rulebook_policy` requirement in `run_gate_decision_stage_cycle(...)` (no implicit file I/O regression).

- [ ] Task 5: Run quality gates for AG1 change set
  - [ ] `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py`
  - [ ] `uv run ruff check`

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-2-environment-and-criticality-tier-caps-ag1`
  - Story ID: `5.2`
- Epic context: Epic 5 implements deterministic safety gating and action execution (FR27-FR35, FR43-FR45, FR51).
- This story specializes AG1 semantics after Story 5.1 created the Stage 6 gate engine skeleton.

### Technical Requirements

- AG1 must enforce FR28/FR29 exactly:
  - local -> OBSERVE max
  - dev -> NOTIFY max
  - uat -> TICKET max
  - prod tier caps: `TIER_0=PAGE`, `TIER_1=TICKET`, `TIER_2/UNKNOWN=NOTIFY`
- Preserve strict AG0..AG6 order and deterministic outputs from Story 5.1.
- Keep `ActionDecisionV1` contract unchanged; only refine policy/evaluation semantics.
- Keep all AG1 behavior in Stage 6 deterministic code and policy models; do not duplicate cap logic elsewhere.
- Resolve current policy mismatch before implementation:
  - `rulebook-v1.yaml` currently defines `dev: OBSERVE` and `stage: NOTIFY`.
  - `Environment` and FRs require `dev` and `uat` semantics.
- Maintain backward compatibility intentionally and test it explicitly if migration aliasing remains.

### Architecture Compliance

- Respect Action Gating architecture boundary:
  - AG1 logic remains in `pipeline/stages/gating.py`.
  - Policy source remains `config/policies/rulebook-v1.yaml`.
  - Contracts remain `GateInputV1` -> `ActionDecisionV1`.
- Maintain cross-cutting invariants:
  - no gate may escalate action severity.
  - no diagnosis/cold-path behavior can override deterministic gate outcomes.
  - UNKNOWN semantics remain first-class and must map to safe caps.
- Keep configuration and policy semantics aligned with documented environment isolation.

### Library / Framework Requirements

Verification date: 2026-03-06.

- `pytest` latest stable is `9.0.2` (PyPI), and project pin is already `9.0.2`.
- `pydantic` latest stable is `2.12.5` (PyPI), and project pin is already `2.12.5`.
- `redis` (redis-py client) latest stable is `7.2.1` (PyPI), and project pin is already `7.2.1`.
- Python datetime guidance remains: prefer aware UTC (`datetime.now(timezone.utc)`); `datetime.utcnow()` is deprecated since Python 3.12.
- Do not add new dependencies for AG1.

### File Structure Requirements

- Primary implementation targets:
  - `config/policies/rulebook-v1.yaml`
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- Contract/config alignment checks:
  - `src/aiops_triage_pipeline/config/settings.py`
  - `src/aiops_triage_pipeline/contracts/enums.py`
  - `src/aiops_triage_pipeline/contracts/action_decision.py`
- Test targets:
  - `tests/unit/pipeline/stages/test_gating.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/contracts/test_policy_models.py`

### Testing Requirements

- Mandatory AG1 unit coverage:
  - local cap to OBSERVE
  - dev cap to NOTIFY
  - uat cap to TICKET
  - prod tier matrix (`TIER_0`, `TIER_1`, `TIER_2`, `UNKNOWN`)
  - `env_cap_applied` true only for environment-cap reduction
  - AG1 reason code and gate trace audit fields
- Regression coverage:
  - monotonic reduction across AG1 + downstream gates remains intact.
  - no scheduler regression for explicit policy injection.
  - no fallback-path breakage from `stage`/`uat` compatibility behavior (if retained).

### Previous Story Intelligence

- Story 5.1 established the Stage 6 engine and AG1 scaffolding; reuse that implementation and test harness.
- Important learnings already captured in Story 5.1 completion notes:
  - UAT compatibility fallback to legacy `stage` policy key was added in AG1.
  - `env_cap_applied` semantics were corrected to exclude tier-only caps.
  - `run_gate_decision_stage_cycle(...)` now requires explicit `rulebook_policy` to avoid hidden file I/O.
- Apply Story 5.2 changes as refinement, not redesign: keep existing interfaces stable.

### Git Intelligence Summary

- Recent history indicates workflow pattern:
  - story context creation commits update story artifact + sprint status together.
  - implementation/fix commits include paired code + tests in same change set.
- Most relevant recent commits:
  - `cdd8396` (`chore(story): create context for epic 5 story 5.1`)
  - `0b3a92e` (`fix(story-4.7): resolve code review findings`)
  - `f3d527d` (`feat(story-4.7): implement casefile retention lifecycle`)
- Implication for Story 5.2: expect compact, test-first adjustments centered in Stage 6 and policy artifacts.

### Latest Tech Information

Verification date: 2026-03-06.

- PyPI reports:
  - `pytest` latest: `9.0.2` (released 2025-12-06)
  - `pydantic` latest: `2.12.5` (released 2025-11-26)
  - `redis` latest: `7.2.1` (released 2026-02-25)
- pytest 9.x note: changelog documents compatibility adjustments after 9.0.0 (for example terminal progress defaults and compatibility shims), so keep tests/plugin usage explicit.
- Python docs continue to recommend aware UTC datetimes and mark `datetime.utcnow()` deprecated since 3.12.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Deterministic gate outputs are authoritative; do not introduce alternate cap evaluators.
- PAGE must remain structurally impossible outside PROD + TIER_0.
- Keep shared policy/cap logic centralized in Rulebook-driven evaluation.
- Preserve UNKNOWN semantics and fail-safe downgrade behavior.
- AG1 and contract/gating changes require targeted regression tests before story completion.

### Project Structure Notes

- Existing repo structure already supports this story:
  - Stage 6 code in `pipeline/stages/gating.py`
  - policy artifacts in `config/policies/`
  - scheduler orchestration in `pipeline/scheduler.py`
  - tests under `tests/unit/pipeline/` and `tests/unit/contracts/`
- No UX artifacts are required for this backend-only gating story.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.2: Environment & Criticality Tier Caps (AG1)`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR27, FR28, FR29)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-P3, NFR-T1, NFR-T4)]
- [Source: `artifact/planning-artifacts/prd/glossary-terminology.md` (AG1, GateInput.v1, ActionDecision.v1, criticality tiers)]
- [Source: `artifact/planning-artifacts/architecture.md` (Action Gating mapping, env isolation, Stage 6 placement)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/5-1-rulebook-gate-engine-ag0-ag6-sequential-evaluation.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py`]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py`]
- [Source: `src/aiops_triage_pipeline/contracts/rulebook.py`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `tests/unit/pipeline/stages/test_gating.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: `https://pypi.org/project/pytest/`]
- [Source: `https://docs.pytest.org/en/stable/changelog.html`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://pypi.org/project/redis/`]
- [Source: `https://docs.python.org/3/library/datetime.html`]

### Story Completion Status

- Story context generated for Epic 5 Story 5.2.
- Story file: `artifact/implementation-artifacts/5-2-environment-and-criticality-tier-caps-ag1.md`.
- Story status set to: `ready-for-dev`.
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
- Core source artifacts:
  - `artifact/planning-artifacts/epics.md`
  - `artifact/planning-artifacts/architecture.md`
  - `artifact/planning-artifacts/prd/functional-requirements.md`
  - `artifact/planning-artifacts/prd/non-functional-requirements.md`
  - `artifact/planning-artifacts/prd/glossary-terminology.md`
  - `artifact/project-context.md`

### Implementation Plan

- Correct AG1 env cap policy values to match FR28 and environment enum.
- Keep AG1 evaluation deterministic and monotonic in Stage 6.
- Preserve explicit `rulebook_policy` injection and existing Stage 6 architecture boundaries.
- Add full AG1 matrix and semantics regression tests before marking implementation complete.

### Completion Notes List

- Story file created for `5-2-environment-and-criticality-tier-caps-ag1`.
- Story prepared for `dev-story` execution with explicit technical and testing guardrails.
- Sprint status updated to `ready-for-dev` for story key `5-2-environment-and-criticality-tier-caps-ag1`.

### File List

- `artifact/implementation-artifacts/5-2-environment-and-criticality-tier-caps-ag1.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-03-06: Created Story 5.2 context document with AG1 implementation guardrails, artifact references, test plan, and latest-technology checks.
