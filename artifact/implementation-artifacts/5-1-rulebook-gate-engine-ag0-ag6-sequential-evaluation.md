# Story 5.1: Rulebook Gate Engine (AG0-AG6 Sequential Evaluation)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,  
I want GateInput.v1 evaluated through Rulebook gates AG0-AG6 sequentially to produce an ActionDecision.v1,  
so that every action decision is deterministic, auditable, and follows the exact gate sequence (FR27).

## Acceptance Criteria

1. **Given** a GateInput.v1 envelope is assembled from evidence, topology, and case context  
   **When** the Rulebook engine evaluates the gates  
   **Then** gates AG0 through AG6 execute sequentially in order and no gate is skipped.
2. **And** the output is an ActionDecision.v1 containing: `final_action`, `env_cap_applied`, `gate_rule_ids`, `gate_reason_codes`, `action_fingerprint`, `postmortem_required`, `postmortem_mode`, `postmortem_reason_codes`.
3. **And** each gate can reduce the action level but never escalate it (monotonic downward).
4. **And** gate evaluation is deterministic policy computation with no external I/O except the AG5 dedupe hook.
5. **And** the gate engine completes within p99 <= 500ms (NFR-P3).
6. **And** unit tests verify: sequential gate execution order, ActionDecision.v1 field completeness, monotonic action reduction, and latency guardrails.

## Tasks / Subtasks

- [ ] Task 1: Add Stage 6 rulebook evaluation entrypoint and decision context model (AC: 1, 2, 3)
  - [ ] Extend `src/aiops_triage_pipeline/pipeline/stages/gating.py` with an evaluation API (for example `evaluate_rulebook_gates(...) -> ActionDecisionV1`) that accepts `GateInputV1` + `RulebookV1`.
  - [ ] Start from `proposed_action` and enforce monotonic reduction with a single shared action-rank helper (`OBSERVE < NOTIFY < TICKET < PAGE`).
  - [ ] Ensure `gate_rule_ids` always records AG0..AG6 in executed order and that the output always includes all required ActionDecision fields.

- [ ] Task 2: Implement AG0-AG6 sequential orchestration with policy-driven handlers (AC: 1, 2, 3, 4)
  - [ ] Execute gates strictly in policy order and fail fast when required gate IDs are missing or reordered.
  - [ ] Implement baseline per-gate evaluation hooks aligned to current contracts:
    - AG0: schema/invariant safety fallback behavior.
    - AG1: cap evaluation through policy maps.
    - AG2-AG4: evidence/sustained/confidence checks via `GateInputV1` fields.
    - AG5: dedupe decision through an injected dependency hook.
    - AG6: postmortem predicate fields only (must not escalate `final_action`).
  - [ ] Apply reason codes from gate effects and keep evaluation deterministic.

- [ ] Task 3: Define AG5 dedupe abstraction without hard-wiring infra in this story (AC: 4)
  - [ ] Add a narrow protocol/interface for dedupe lookup/write so Stage 6 remains testable and mostly pure.
  - [ ] Keep Redis/network specifics behind the abstraction; Story 5.5 will harden full dedupe TTL/store behavior.
  - [ ] Ensure dedupe store errors map to the configured safe cap path instead of crashing uncontrolled.

- [ ] Task 4: Wire scheduler-facing helper for gate decisions (AC: 1, 2, 4)
  - [ ] Add a scheduler helper that evaluates collected gate inputs and returns per-scope ActionDecision payloads.
  - [ ] Preserve existing Stage 1-3 and gate-input assembly behavior; add Stage 6 decision computation as an additive step.
  - [ ] Keep structured logging and correlation fields aligned with current scheduler/pipeline logging patterns.

- [ ] Task 5: Add latency measurement and guardrail logging (AC: 5)
  - [ ] Measure per-evaluation elapsed time using a monotonic clock.
  - [ ] Emit structured logs for evaluation duration and gate path.
  - [ ] Add warning/guardrail behavior when evaluation duration exceeds the NFR threshold.

- [ ] Task 6: Add unit tests for sequencing, output completeness, monotonicity, and error paths (AC: 1, 2, 3, 4, 6)
  - [ ] Add tests proving AG0..AG6 execute in strict order and none are skipped.
  - [ ] Add tests verifying action never escalates, including multi-gate cap interactions.
  - [ ] Add tests covering output completeness (`ActionDecisionV1` required fields) and reason code aggregation.
  - [ ] Add tests for AG5 dedupe hook outcomes: pass, duplicate suppression, and store-error cap behavior.
  - [ ] Add tests for AG6 postmortem flag behavior independent from final action escalation.

- [ ] Task 7: Add performance-oriented test coverage for Stage 6 budget confidence (AC: 5, 6)
  - [ ] Add deterministic micro-benchmark style test(s) that exercise realistic gate payloads and assert per-evaluation timing envelope for local CI conditions.
  - [ ] Keep assertions resilient (guardrail-oriented, not flaky hard-real-time) while still enforcing regression detection for obvious slowdowns.

- [ ] Task 8: Run quality gates
  - [ ] `uv run pytest -q tests/unit/pipeline/stages/test_gating.py tests/unit/pipeline/test_scheduler.py tests/unit/contracts/test_policy_models.py`
  - [ ] `uv run ruff check`

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-1-rulebook-gate-engine-ag0-ag6-sequential-evaluation`
  - Story ID: `5.1`
- Epic context: Epic 5 establishes deterministic safety gating and action execution guardrails (FR27-FR35, FR43-FR45, FR51).
- Existing implementation baseline in repo:
  - `pipeline/stages/gating.py` currently assembles `GateInputV1` payloads from stage outputs.
  - Rulebook contract and policy artifacts exist (`contracts/rulebook.py`, `config/policies/rulebook-v1.yaml`).
  - ActionDecision contract exists (`contracts/action_decision.py`).
  - No Stage 6 gate-evaluation engine currently exists; this story creates that engine foundation.

### Technical Requirements

- Implement FR27 core engine behavior first:
  - deterministic AG0-AG6 sequential evaluation,
  - explicit audit outputs (`gate_rule_ids`, `gate_reason_codes`),
  - monotonic action reduction only.
- Keep Stage 6 primarily computation-only:
  - no external I/O in AG0/AG1/AG2/AG3/AG4/AG6,
  - AG5 dedupe is the only integration hook.
- Preserve contract-first behavior:
  - consume `GateInputV1`,
  - emit `ActionDecisionV1`,
  - do not introduce ad-hoc payload shapes.
- Keep future story separation clean:
  - this story establishes and verifies the engine skeleton and deterministic sequencing behavior,
  - Stories 5.2-5.6 deepen specific gate semantics and policy details.
- Resolve action levels with one canonical priority mapping; never duplicate comparison logic across handlers.
- Keep error semantics explicit:
  - invalid policy/gate configuration should fail loudly and be test-covered,
  - degradable AG5 store behavior should cap safely, not silently pass.
- Existing artifact mismatch to account for during implementation planning:
  - `config/settings.py` defines env caps as `local/dev/uat/prod`,
  - `config/policies/rulebook-v1.yaml` currently uses `local/dev/stage/prod` and `dev: OBSERVE`.
  - For Story 5.1, keep engine policy-driven and avoid hardcoded env constants; align policy semantics in Story 5.2.

### Architecture Compliance

- Align with architecture mapping for FR27-FR35:
  - Stage 6 lives in `pipeline/stages/gating.py` with contracts in `contracts/{gate_input,action_decision,rulebook}.py`.
  - Rulebook remains deterministic and authoritative over action outputs.
- Respect cross-cutting invariants:
  - UNKNOWN-not-zero semantics must remain intact when evaluating evidence sufficiency.
  - Do not let diagnosis/cold-path behavior override gate outputs.
- Keep package boundaries intact:
  - do not pull infra-heavy concerns into config/contracts modules.
  - keep gating engine logic in pipeline stage layer with narrow dependency interfaces.
- Maintain auditability:
  - every evaluated gate path must be reconstructable from output fields and logs.

### Library / Framework Requirements

- Use existing project stack and pinned versions already defined in this repo:
  - `pydantic==2.12.5`
  - `pytest==9.0.2`
  - `redis==7.2.1` (for upcoming AG5 integration path)
  - Python runtime baseline: `>=3.13`
- For timing logic, follow Python datetime/time guidance:
  - prefer aware UTC datetimes (`datetime.now(timezone.utc)`),
  - avoid deprecated naive UTC constructors for new code paths.
- Do not add new gating libraries/frameworks; implement with existing stdlib + contracts.

### File Structure Requirements

- Primary targets:
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py` (Stage 6 evaluator + gate orchestration)
  - `src/aiops_triage_pipeline/pipeline/scheduler.py` (optional helper wiring for decision cycle)
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py` (exports if new Stage 6 APIs are added)
- Optional dependency seam target:
  - `src/aiops_triage_pipeline/cache/dedupe.py` (define protocol/stub abstraction only if needed now)
- Test targets:
  - `tests/unit/pipeline/stages/test_gating.py` (extend heavily for AG0-AG6 execution)
  - `tests/unit/pipeline/test_scheduler.py` (if scheduler wiring added)
  - `tests/unit/contracts/test_policy_models.py` (if policy-structure guardrails need updates)

### Testing Requirements

- Mandatory unit coverage:
  - strict AG0..AG6 execution order,
  - no skipped gates in normal flow,
  - monotonic reduction invariants across mixed gate effects,
  - ActionDecision required field completeness and deterministic contents,
  - AG5 abstraction behavior for duplicate and store-error paths,
  - AG6 postmortem fields set/reset behavior without final action escalation.
- Performance and reliability coverage:
  - guardrail test for Stage 6 evaluation budget trends (NFR-P3 awareness),
  - regression test for deterministic replay given same input + policy.
- Backward-compatibility checks:
  - existing gate-input assembly tests must keep passing,
  - existing CaseFile/outbox tests using `ActionDecisionV1` must not regress.

### Latest Tech Information

Verification date: 2026-03-06.

- `pytest` latest stable is `9.0.2` (released 2025-12-06), matching project pin.
  - pytest 9.0 introduced notable behavior changes (for example stricter async/plugin expectations and Python support changes), so keep tests/plugins explicit when extending Stage 6 tests.
- `pydantic` latest stable is `2.12.5` (released 2025-11-26), matching project pin.
  - Pydantic v2 remains the active contract/validation baseline in this repo.
- `redis` latest stable is `7.2.1` (released 2026-02-25), matching project pin.
  - This supports upcoming AG5 dedupe implementation without dependency drift.
- Python datetime guidance remains: prefer aware UTC datetimes; `datetime.utcnow()` is deprecated since Python 3.12.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Deterministic guardrails are authoritative; diagnosis/LLM paths must not override gate decisions.
- Preserve UNKNOWN semantics across confidence/gating decisions.
- Keep cross-cutting logic centralized (no duplicate policy evaluators).
- Fail loudly on critical invariants; use safe caps for degradable paths.
- For high-risk gating/contract logic, add targeted regression tests with each change.

### Project Structure Notes

- The repo is already structured for this story:
  - Stage helpers in `pipeline/stages/`,
  - frozen policy/event contracts in `contracts/`,
  - scheduler orchestration in `pipeline/scheduler.py`,
  - contract and stage tests in `tests/unit/contracts` and `tests/unit/pipeline/stages`.
- No UX artifacts are required for this backend-only story.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.1: Rulebook Gate Engine (AG0-AG6 Sequential Evaluation)`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR27-FR35, FR66)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-P3, NFR-T1, NFR-T5, NFR-T6)]
- [Source: `artifact/planning-artifacts/prd/glossary-terminology.md` (AG0-AG6 semantics, GateInput.v1, ActionDecision.v1)]
- [Source: `artifact/planning-artifacts/architecture.md` (Action Gating mapping, Stage 6 placement, deterministic guardrails)]
- [Source: `artifact/project-context.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/contracts/rulebook.py`]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py`]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `tests/unit/pipeline/stages/test_gating.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: https://pypi.org/project/pytest/]
- [Source: https://docs.pytest.org/en/stable/changelog.html]
- [Source: https://pypi.org/project/pydantic/]
- [Source: https://pypi.org/project/redis/]
- [Source: https://docs.python.org/3/library/datetime.html]

### Story Completion Status

- Story context generated with implementation guardrails for Epic 5 Story 5.1.
- Story file: `artifact/implementation-artifacts/5-1-rulebook-gate-engine-ag0-ag6-sequential-evaluation.md`.
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

### Completion Notes List

- Selected first backlog story in sprint order: `5-1-rulebook-gate-engine-ag0-ag6-sequential-evaluation`.
- Consolidated implementation context from epics, architecture, project context, and current codebase state.
- Added gate-engine-specific guardrails to prevent scope drift and regressions in deterministic action safety.
- Added current-version technical validation notes for pytest/pydantic/redis/python datetime guidance.

### File List

- `artifact/implementation-artifacts/5-1-rulebook-gate-engine-ag0-ag6-sequential-evaluation.md`
