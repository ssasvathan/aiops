# Story 5.6: Postmortem Predicate Evaluation (AG6)

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the PM_PEAK_SUSTAINED predicate evaluated for selective postmortem obligation,
so that only high-impact cases (peak, sustained, TIER_0 in PROD) trigger postmortem tracking (FR35).

## Acceptance Criteria

1. **Given** the Rulebook engine reaches AG6
   **When** the postmortem predicate is evaluated
   **Then** `PM_PEAK_SUSTAINED` fires when: peak=true AND sustained=true AND criticality_tier=TIER_0 AND environment=PROD (FR35).
2. **And** when the predicate fires, `ActionDecisionV1` sets: `postmortem_required=True`, `postmortem_mode="SOFT"` (Phase 1A), and `postmortem_reason_codes=("PM_PEAK_SUSTAINED",)`.
3. **And** when the predicate does NOT fire (any condition missing), `postmortem_required=False`, `postmortem_mode=None`, `postmortem_reason_codes=()`.
4. **And** AG6 does **not** change `final_action` — it only sets postmortem fields.
5. **And** unit tests verify: predicate fires with all conditions met; predicate does not fire when any individual condition is missing (peak=False, peak=None, sustained=False, env!=PROD, criticality_tier!=TIER_0); postmortem fields correctly set in all cases.

## Tasks / Subtasks

- [x] Task 1: Audit AG6 implementation in gating.py against all ACs (AC: 1–4)
  - [x] Verify AG6 block (lines ~172–198 of `pipeline/stages/gating.py`) correctly evaluates PM_PEAK_SUSTAINED predicate.
  - [x] Verify `allow_action_change=False` is applied on both `on_pass` and `on_fail` branches.
  - [x] Verify post-evaluation logic sets `postmortem_mode="SOFT"` when `postmortem_required=True` and mode is None.
  - [x] Verify `on_fail` clears `postmortem_mode` and `postmortem_reason_codes` when `postmortem_required=False`.
  - [x] Fix any gaps found; no new external dependencies are expected.

- [x] Task 2: Verify AG6 policy artifact completeness (AC: 1, 2, 3)
  - [x] Confirm `config/policies/rulebook-v1.yaml` AG6 gate has: `on_pass.set_postmortem_required=true`, `on_pass.set_postmortem_reason_codes: [PM_PEAK_SUSTAINED]`, `on_fail.set_postmortem_required: false`.
  - [x] Confirm AG6 `on_pass` does NOT set `force_postmortem_mode` — "SOFT" is applied by post-processing in `evaluate_rulebook_gates` (Phase 1A default).
  - [x] Update policy if any gap found; keep `contracts/rulebook.py` validators consistent.

- [x] Task 3: Expand unit test coverage for all AG6 boundary conditions (AC: 5)
  - [x] Add test: predicate fires — all conditions met (PROD + TIER_0 + peak=True + sustained=True) → postmortem_required=True, postmortem_mode="SOFT", reason_codes=("PM_PEAK_SUSTAINED",), final_action unchanged.
  - [x] Add test: predicate does not fire — peak=False → postmortem_required=False.
  - [x] Add test: predicate does not fire — peak=None (UNKNOWN) → postmortem_required=False.
  - [x] Add test: predicate does not fire — sustained=False → postmortem_required=False.
  - [x] Add test: predicate does not fire — env=DEV → postmortem_required=False.
  - [x] Add test: predicate does not fire — env=UAT → postmortem_required=False.
  - [x] Add test: predicate does not fire — criticality_tier=TIER_1 → postmortem_required=False.
  - [x] Add test: predicate does not fire — criticality_tier=TIER_2 → postmortem_required=False.
  - [x] Add test: predicate does not fire — criticality_tier=UNKNOWN → postmortem_required=False.
  - [x] Add test: AG6 does not escalate final_action when predicate fires (OBSERVE stays OBSERVE).
  - [x] Add test: AG6 does not escalate final_action when predicate does not fire.
  - [x] Verify existing tests `test_evaluate_rulebook_gates_ag6_sets_postmortem_without_action_escalation` and `test_evaluate_rulebook_gates_ag0_invalid_input_prevents_postmortem_trigger` still pass without modification.

- [x] Task 4: Run quality gates with zero skips
  - [x] `uv run pytest -q tests/unit/pipeline/stages/test_gating.py`
  - [x] `uv run ruff check`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-6-postmortem-predicate-evaluation-ag6`
  - Story ID: `5.6`
- Epic context: Epic 5 enforces deterministic action safety (AG0–AG6) and storm-control guardrails.
- **Critical insight**: The AG6 implementation is already present in `pipeline/stages/gating.py` (lines ~172–198) as part of the gating scaffold built in earlier stories. This story's work is primarily **comprehensive test coverage** and **implementation verification** against the formal AC, not net-new logic.
- Existing AG6 scaffold state (as of Sprint 5.5):
  - `_EvaluationState` has `postmortem_required`, `postmortem_mode`, `postmortem_reason_codes` fields.
  - AG6 block in `evaluate_rulebook_gates` evaluates: `state.input_valid AND env=PROD AND tier=TIER_0 → if peak is True AND sustained → on_pass else on_fail`.
  - Post-processing sets `postmortem_mode="SOFT"` when `required=True` and mode is `None`.
  - `ActionDecisionV1` has `postmortem_required`, `postmortem_mode`, `postmortem_reason_codes` fields (frozen contract, no change expected).
  - Rulebook-v1.yaml already has AG6 gate with `on_pass`/`on_fail` effects.
  - Two basic AG6 tests exist in `tests/unit/pipeline/stages/test_gating.py`; comprehensive boundary coverage is missing.

### Technical Requirements

- AG6 predicate logic **must** match FR35 exactly:
  - `PM_PEAK_SUSTAINED` = `peak is True AND sustained is True AND criticality_tier == TIER_0 AND env == PROD`.
  - Note: `peak is True` (not just truthy) — `peak=None` must NOT fire the predicate.
  - Note: `state.input_valid` must also be True — AG0 failure must prevent AG6.
- AG6 **must not** change `final_action` under any condition (`allow_action_change=False` on both branches).
- `postmortem_mode` resolution is Phase-1A-specific:
  - When `postmortem_required=True` and `force_postmortem_mode` is unset in on_pass → mode is set to `"SOFT"` by post-processing in `evaluate_rulebook_gates` (lines ~195–196 of gating.py).
  - This design separates Phase 1A ("SOFT") from future Phase 1B ("HARD") without policy changes.
- `postmortem_mode=None` and `postmortem_reason_codes=()` when `postmortem_required=False`.
- AG0-AG6 sequence and monotonic reduction invariants must remain unchanged.

### Architecture Compliance

- AG6 evaluation is contained within `pipeline/stages/gating.py` `evaluate_rulebook_gates()`.
- `ActionDecisionV1` (`contracts/action_decision.py`) is a frozen contract — no field additions or modifications expected for this story.
- `GateEffect` model (`contracts/rulebook.py`) already supports `set_postmortem_required`, `set_postmortem_reason_codes`, `force_postmortem_mode`.
- Rulebook gate policy is in `config/policies/rulebook-v1.yaml` — AG6 section already present.
- No Redis, Slack, or external integration involvement — AG6 is a pure in-memory predicate evaluation.
- Hot path: AG6 is part of Stage 6 in the synchronous gate evaluation loop.

### Library / Framework Requirements

Verification date: 2026-03-06.

- No new dependencies required for this story.
- All work is within existing Python 3.13, Pydantic 2.12.5, pytest 9.0.2 + pytest-asyncio 1.3.0 stack.
- Use `GateInputV1.model_copy(update={...})` for test fixture derivation — already established pattern in `test_gating.py`.

### File Structure Requirements

- Primary implementation targets (audit and potential minor fixes only):
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py` — AG6 block lines ~172–198 and post-processing ~193–198.
  - `config/policies/rulebook-v1.yaml` — AG6 gate section.
- Test targets (primary work):
  - `tests/unit/pipeline/stages/test_gating.py` — extend with comprehensive AG6 boundary tests.
- Contracts (read-only verification, no changes expected):
  - `src/aiops_triage_pipeline/contracts/action_decision.py`
  - `src/aiops_triage_pipeline/contracts/rulebook.py`

### Testing Requirements

- All new tests must use `_gate_input_for_eval()` as the baseline fixture (returns PROD+TIER_0+sustained=True+peak=True+proposed_action=PAGE).
- Use `.model_copy(update={...})` to vary individual conditions.
- Tests for predicate NOT firing should assert: `postmortem_required is False`, `postmortem_mode is None`, `postmortem_reason_codes == ()`.
- Tests for predicate firing should assert: `postmortem_required is True`, `postmortem_mode == "SOFT"`, `postmortem_reason_codes == ("PM_PEAK_SUSTAINED",)`.
- All predicate tests must also assert `final_action` is unchanged from what AG0-AG5 produce (AG6 must never escalate).
- Existing tests must not break — especially the two AG6 tests already present at lines ~433 and ~445.
- Full regression suite must pass with zero skipped tests.
- Environment needed: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock` for integration container tests.

### Previous Story Intelligence

From Story 5.5 (`artifact/implementation-artifacts/5-5-action-deduplication-and-redis-degraded-mode-ag5.md`):

- Keep gate evaluation monotonic and deterministic; AG5 must only suppress or cap, never escalate — same principle applies to AG6 (action-read-only).
- Preserve precise, explicit reason-code behavior; reviewers required extra depth.
- Scheduler-level tests guard downstream interactions; stage-level tests guard gate semantics.
- Code-review found: guard against dead code, incorrect return types, untested integration paths — apply same discipline here.

From Story 5.4 (AG4):

- High-urgency gating changes receive adversarial review; design test coverage up front.
- Policy artifact updates and gate logic changes must be in sync in the same story.

Epic 5 implementation pattern:

- Each gating story has expanded `test_gating.py` with targeted parametrize or named test functions.
- `model_copy(update={...})` is the standard for fixture variation — do not build new fixtures from scratch.

### Git Intelligence Summary

Recent commits (most recent first):

- `575ea4e` story 5.5: apply code-review remediations
- `8934e61` story 5.5: implement AG5 action deduplication and Redis degraded mode
- `fa284b6` chore(story): create story 5.5 context
- `f0460fb` story 5.4: apply code-review remediations
- `c7f2d05` Implement AG4 sustained/confidence gating with granular reason codes

Actionable patterns for Story 5.6:

- Story 5.5 touched `gating.py`, `cache/dedupe.py`, `integrations/slack.py`, `contracts/`, `scheduler.py`. Story 5.6 is narrow: gating.py + test_gating.py only.
- Expect reviewer scrutiny on: boundary conditions for peak=None vs peak=False, `allow_action_change=False` coverage, and postmortem_mode "SOFT" path.
- Keep change set minimal — no cross-module refactoring.

### Latest Tech Information

Verification date: 2026-03-06.

- Python 3.13 typing applies: `bool | None` for `peak` field (already typed in `GateInputV1`).
- Pydantic 2.12.5: `model_copy(update={...})` is the correct frozen-model variation API — `model_copy` returns a new instance with fields replaced.
- pytest 9.0.2 + pytest-asyncio 1.3.0: `asyncio_mode=auto` is project-configured. AG6 tests are synchronous (no async needed since `evaluate_rulebook_gates` is sync).
- No external library changes needed.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Deterministic gate engine remains authoritative; no LLM path can override action decisions (AG6 is postmortem-only, does not touch action).
- Keep cross-cutting patterns centralized: structured logging conventions, shared health registry semantics.
- High-risk changes (gating/contracts) require targeted regressions and full quality gates.
- Never bypass deterministic guardrails: `allow_action_change=False` on AG6 is a structural invariant.
- Never collapse UNKNOWN into PRESENT/zero: `peak=None` (UNKNOWN) must not trigger postmortem — ensure predicate checks `peak is True` (strict identity), not `bool(peak)`.
- Use Python 3.13 typing style: `X | None`, built-in generics.
- Keep contract models immutable (`frozen=True`) — `ActionDecisionV1` and `GateInputV1` must not be mutated.

### Project Structure Notes

- No new files expected. All work is:
  1. Verification pass on `gating.py` and `rulebook-v1.yaml`.
  2. Test additions in `test_gating.py`.
- No frontend or UX artifacts required.
- `_gate_input_for_eval()` fixture is defined at line ~113 in `test_gating.py`:
  - Baseline: `env=PROD, criticality_tier=TIER_0, sustained=True, peak=True, proposed_action=PAGE, diagnosis_confidence=0.95`.
  - All four PM_PEAK_SUSTAINED conditions are met → baseline fires the predicate.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.6: Postmortem Predicate Evaluation (AG6)`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR35)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-T4)]
- [Source: `artifact/planning-artifacts/architecture.md` (Action Gating & Safety, FR27–FR35)]
- [Source: `artifact/project-context.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py` (AG6 block ~172–198, post-processing ~193–198)]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py`]
- [Source: `src/aiops_triage_pipeline/contracts/rulebook.py`]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py`]
- [Source: `config/policies/rulebook-v1.yaml` (AG6 gate section)]
- [Source: `tests/unit/pipeline/stages/test_gating.py` (existing AG6 tests ~433–456, fixture ~113–139)]
- [Source: `artifact/implementation-artifacts/5-5-action-deduplication-and-redis-degraded-mode-ag5.md`]

### Story Completion Status

- Story context generated for Epic 5 Story 5.6.
- Story file: `artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md`.
- Story status set to: `ready-for-dev`.
- Completion note: Ultimate context engine analysis completed — comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
- Core planning artifacts:
  - `artifact/planning-artifacts/epics.md`
  - `artifact/planning-artifacts/architecture.md`
  - `artifact/project-context.md`
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `src/aiops_triage_pipeline/contracts/action_decision.py`
  - `src/aiops_triage_pipeline/contracts/rulebook.py`
  - `config/policies/rulebook-v1.yaml`
  - `tests/unit/pipeline/stages/test_gating.py`
  - `artifact/implementation-artifacts/5-5-action-deduplication-and-redis-degraded-mode-ag5.md`

### Completion Notes List

- Tasks 1 & 2 (audit): No implementation gaps found. AG6 block (gating.py lines 172–191) correctly implements PM_PEAK_SUSTAINED predicate with strict `peak is True` identity check, `allow_action_change=False` on both branches, and post-processing for "SOFT" mode. `rulebook-v1.yaml` AG6 section is complete and consistent with implementation.
- Task 3 (tests): Added 11 new boundary-condition tests to `test_gating.py`:
  - `test_evaluate_rulebook_gates_ag6_predicate_fires_when_all_conditions_met` — asserts all postmortem fields and final_action unchanged
  - `test_evaluate_rulebook_gates_ag6_predicate_does_not_fire_when_any_condition_missing` — parametrized (8 cases): peak=False, peak=None, sustained=False, env=DEV, env=UAT, tier=TIER_1, tier=TIER_2, tier=UNKNOWN
  - `test_evaluate_rulebook_gates_ag6_no_action_escalation_when_predicate_does_not_fire` — verifies final_action=PAGE when peak=False
  - Existing tests `test_evaluate_rulebook_gates_ag6_sets_postmortem_without_action_escalation` and `test_evaluate_rulebook_gates_ag0_invalid_input_prevents_postmortem_trigger` confirmed passing without modification
- Task 4 (quality gates): `pytest -q test_gating.py` 53/53 passed; `ruff check` all passed; full suite 538/538 passed, 0 skipped.

### File List

- `tests/unit/pipeline/stages/test_gating.py` (modified — added AG6 boundary condition tests)

## Change Log

- 2026-03-06: Story 5.6 implementation complete. AG6 audit confirmed no gaps; added 11 new boundary-condition tests covering all PM_PEAK_SUSTAINED predicate conditions (peak=False/None, sustained=False, env=DEV/UAT, tier=TIER_1/TIER_2/UNKNOWN) plus predicate-fires and no-action-escalation assertions. Full regression suite: 538 passed, 0 skipped.
