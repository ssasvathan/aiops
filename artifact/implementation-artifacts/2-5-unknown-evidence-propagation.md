# Story 2.5: UNKNOWN Evidence Propagation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->


## Story

As a platform operator,
I want missing Prometheus series mapped to EvidenceStatus=UNKNOWN and propagated through all computation layers,
so that missing data is never silently treated as zero and downstream decisions correctly reflect uncertainty (FR5, FR6).

## Acceptance Criteria

1. **Given** a Prometheus query returns missing series for a specific metric  
   **When** evidence is assembled  
   **Then** the missing series maps to `EvidenceStatus=UNKNOWN` and is never treated as zero.

2. **And** UNKNOWN propagates through peak classification (peak status becomes UNKNOWN where required evidence is missing).

3. **And** UNKNOWN propagates through sustained computation (sustained status and reason codes reflect uncertainty, never false certainty).

4. **And** UNKNOWN propagates through confidence computation (confidence is downgraded according to policy, not defaulted upward).

5. **And** an `evidence_status_map` is produced for each case mapping every evidence primitive to `PRESENT | UNKNOWN | ABSENT | STALE`.

6. **And** unit/integration tests verify end-to-end UNKNOWN propagation: missing series -> evidence -> peak -> sustained -> confidence -> gate input.

## Tasks / Subtasks

- [x] Task 1: Add explicit evidence-status representation in Stage 1 output (AC: 1, 5)
  - [x] Extend Stage 1 data model to carry `evidence_status_map` per normalized scope/case payload.
  - [x] Ensure missing metric series becomes `EvidenceStatus.UNKNOWN`, not implicit empty list semantics.
  - [x] Preserve immutability guarantees (`frozen=True`, nested mapping freeze).

- [x] Task 2: Wire UNKNOWN-aware propagation into Stage 2 peak/sustained computation (AC: 2, 3)
  - [x] Ensure missing required evidence produces UNKNOWN-oriented peak context/reason codes instead of OFF_PEAK defaults.
  - [x] Ensure sustained logic does not convert evidence gaps into stable non-anomalous truth.
  - [x] Keep deterministic keying and interval rules from Story 2.4 unchanged.

- [x] Task 3: Carry evidence status into gate-facing contracts (AC: 4, 5)
  - [x] Ensure `GateInputV1.evidence_status_map` receives stage-derived statuses, not reconstructed ad hoc values.
  - [x] Keep contract validation strict and schema-first; no unvalidated dynamic fields.

- [x] Task 4: Preserve degraded-mode boundaries for total Prometheus outage vs partial missing series (AC: 1, 4)
  - [x] Keep partial missing-series behavior as UNKNOWN propagation.
  - [x] Keep total Prometheus unavailability behavior as TelemetryDegradedEvent + action cap path (existing semantics).

- [x] Task 5: Add focused tests (AC: 6)
  - [x] Unit tests in evidence stage for missing series -> `EvidenceStatus.UNKNOWN` mapping.
  - [x] Unit tests in Stage 2 for UNKNOWN propagation to peak context/confidence-facing outputs.
  - [x] Scheduler/integration tests proving Stage 1 -> Stage 2 -> gate input flow preserves UNKNOWN.

- [x] Task 6: Quality gates
  - [x] Run `uv run pytest -q tests/unit/pipeline/stages/test_evidence.py tests/unit/pipeline/stages/test_peak.py tests/unit/pipeline/test_scheduler.py`.
  - [x] Run `uv run pytest -q tests/integration/pipeline/test_evidence_prometheus_integration.py`.
  - [x] Run `uv run pytest -q` and `uv run ruff check`.


## Dev Notes

### Developer Context Section

- This story is the FR5/FR6 integrity checkpoint for Epic 2: no layer may collapse missing telemetry into zero or PRESENT.
- Story 2.4 already established sustained streak logic and cache persistence; Story 2.5 must augment semantics without breaking deterministic streak behavior.
- UNKNOWN propagation is a cross-layer concern: Stage 1 evidence normalization, Stage 2 peak/sustained interpretation, and gate-input assembly must agree on status vocabulary.
- Keep scope constrained to propagation correctness; do not redesign AG engine behavior in this story.
- Preserve hot-path determinism and non-blocking posture (cold-path LLM remains advisory and independent).


### Technical Requirements

- Introduce a canonical evidence-status mapping flow rooted in Stage 1 output and reused downstream; avoid recomputing status independently in each stage.
- Use `EvidenceStatus` enum values from contracts (`PRESENT`, `UNKNOWN`, `ABSENT`, `STALE`) consistently.
- Define deterministic mapping rules for this story:
  - metric key queried + sample(s) present -> `PRESENT`
  - metric key queried + no sample for scope -> `UNKNOWN`
  - reserve `ABSENT`/`STALE` for their explicit semantics (do not overload in this story)
- Ensure peak classification uses UNKNOWN-safe behavior when required metrics are missing.
- Ensure confidence calculations do not rise above policy floor when unknown evidence participates in decision context.
- Keep serialization and validation at I/O boundaries only; in-memory models remain frozen and immutable.


### Architecture Compliance

- Maintain architecture layering:
  - evidence collection/normalization in `pipeline/stages/evidence.py`
  - stage-2 interpretation in `pipeline/stages/peak.py`
  - immutable data models in `models/`
  - policy/contracts in `contracts/`
- Preserve 5-minute cadence assumptions from rulebook/NFR-P2; no hidden ad hoc timing logic.
- Preserve degraded-mode distinction:
  - partial missing series -> UNKNOWN propagation
  - total Prometheus unavailability -> TelemetryDegradedEvent path and capped actions
- Do not introduce parallel rule evaluators or bypass existing gate-input contract path.
- Keep structured warning logs with stable `event_type` fields for observability and troubleshooting.


### Library / Framework Requirements

- Python runtime and typing style remain project-standard (`>=3.13`, modern `X | None` syntax).
- Pydantic v2 model discipline remains mandatory (`frozen=True`, explicit typed fields, validators for structural invariants only).
- Redis cache interactions must keep best-effort behavior (warn and continue on cache failure; never crash hot path).
- Prometheus semantics must remain standards-aligned: missing vectors are treated as missing data, not numeric zeros.
- Do not upgrade dependencies in this story unless required for correctness/security; this story is behavior-focused.


### File Structure Requirements

- Primary implementation files:
  - `src/aiops_triage_pipeline/models/evidence.py`
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
  - `src/aiops_triage_pipeline/pipeline/stages/peak.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
- Contract touchpoints (if needed for type plumbing only):
  - `src/aiops_triage_pipeline/contracts/gate_input.py`
  - `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
- Test files to add/update:
  - `tests/unit/pipeline/stages/test_evidence.py`
  - `tests/unit/pipeline/stages/test_peak.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/integration/pipeline/test_evidence_prometheus_integration.py`


### Testing Requirements

- Unit test scenarios:
  - Missing series for a required metric maps to `EvidenceStatus.UNKNOWN`.
  - UNKNOWN evidence influences peak context and reason codes correctly.
  - Sustained state does not produce false certainty when prerequisite evidence is UNKNOWN.
  - `evidence_status_map` contains deterministic keys and enum values.
- Scheduler/flow tests:
  - Stage 1 output containing UNKNOWN propagates through Stage 2 and into gate-facing structures.
  - Existing sustained-history behavior from Story 2.4 remains unchanged for fully-present evidence.
- Integration tests:
  - End-to-end with local Prometheus/mock samples covering partial missing telemetry and ensuring no zero-default behavior.
- Regression gates:
  - Full pytest + lint pass required before moving to review.


### Previous Story Intelligence

- Story 2.4 established the sustained pipeline primitives already in production path:
  - deterministic sustained identity keying `(env, cluster_id, topic/group, anomaly_family)`
  - policy-driven `sustained_intervals_required`
  - Redis-backed evidence-window persistence with graceful degraded behavior
- Reuse and preserve from Story 2.4:
  - `compute_sustained_status_by_key(...)` sequencing and reset semantics
  - `build_sustained_window_state_by_key(...)` mapping and scheduler wiring
  - warning-and-continue cache failure behavior
- Avoid known regression patterns:
  - do not add hidden disk I/O in hot-path cycle functions
  - do not let cache exceptions escape hot path
  - do not introduce ambiguous status transformations between stages


### Git Intelligence Summary

- Recent commit trend shows review-hardening after each story, then done-state transition:
  - `6efacc1` Story 2.4: code-review fixes and done
  - `1ebaaba` Story 2.3: code-review fixes and done
  - `84088d0` Story 2.3 implementation
  - `37843b2` Story 2.2 review hardening
  - `4b44231` Story 2.2 review fixes and done
- Practical guidance for Story 2.5:
  - keep changeset narrow around evidence-status propagation
  - preserve existing file ownership boundaries
  - add tests first for missing-series behavior to prevent semantic drift


### Latest Tech Information

Verification date: **March 3, 2026**.

- Prometheus:
  - Latest tagged release observed: `v3.9.1`.
  - Current LTS line observed in releases: `v3.5.1`.
  - Story impact: keep query/missing-series handling standards-compliant and version-agnostic.
- Pydantic:
  - Latest PyPI release observed: `2.12.5`.
  - Story impact: continue immutable model-first approach already used in this codebase.
- redis-py:
  - Latest PyPI release observed: `7.1.1`.
  - Redis docs mark `SETEX` as deprecated in favor of `SET key value EX seconds`.
  - Story impact: for any new TTL writes, prefer non-deprecated call shape while preserving existing compatibility.
- pytest:
  - Latest PyPI release observed: `9.0.2`.
  - Story impact: existing test stack stays aligned; no tooling migration required in this story.


### Project Context Reference

- `artifact/project-context.md` is authoritative for this implementation pass.
- Mandatory guardrails to enforce in this story:
  - never collapse UNKNOWN into zero/PRESENT
  - preserve deterministic guardrails and hot-path safety
  - keep shared enforcement patterns (logging, health, policy contracts)
  - add/update targeted tests for any behavior change in evidence/gating pathways


### Story Completion Status

- Story context generation complete.
- Status set to `ready-for-dev`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created**.

## Project Structure Notes

- This story should extend existing Stage 1/Stage 2 paths instead of creating new parallel modules.
- Keep UNKNOWN semantics centralized and reusable to prevent drift between evidence, peak, and gate-input assembly.

## References

- [Source: `artifact/planning-artifacts/epics.md#Story 2.5: UNKNOWN Evidence Propagation`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 2: Evidence Collection & Signal Validation`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR5, FR6, FR31, FR67)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-P2, NFR-T2)]
- [Source: `artifact/planning-artifacts/prd/project-scoping-phased-development.md` (Phase 0 acceptance criteria)]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` (UNKNOWN propagation boundaries)]
- [Source: `artifact/planning-artifacts/architecture.md` (technical stack, package boundaries, degraded-mode patterns)]
- [Source: `artifact/project-context.md` (Critical Don't-Miss Rules; Testing Rules; Framework Rules)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/evidence.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/peak.py`]
- [Source: `src/aiops_triage_pipeline/models/evidence.py`]
- [Source: `src/aiops_triage_pipeline/models/peak.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `config/policies/prometheus-metrics-contract-v1.yaml`]
- [Source: `https://github.com/prometheus/prometheus/releases`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://pypi.org/project/redis/`]
- [Source: `https://redis.io/docs/latest/commands/setex/`]
- [Source: `https://pypi.org/project/pytest/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with `workflow-config=_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`.
- Story auto-selected from sprint backlog order: `2-5-unknown-evidence-propagation`.
- Inputs loaded via discover protocol: epics, architecture, selective PRD shards, project context, previous story, git history.
- Latest technical references checked against official sources on March 3, 2026.
- Implemented Stage 1 evidence status propagation in `models/evidence.py` and `pipeline/stages/evidence.py` with immutable nested maps.
- Implemented Stage 2 UNKNOWN-aware propagation in `pipeline/stages/peak.py` and `models/peak.py` including required-evidence reason codes and sustained uncertainty handling.
- Updated scheduler wiring in `pipeline/scheduler.py` to pass stage-derived evidence status into Stage 2 output.
- Implemented Stage 6 gate-input assembly in `pipeline/stages/gating.py`, wiring stage-derived `evidence_status_map` into `GateInputV1`.
- Added tests across evidence, peak, scheduler, and integration pipeline flow for UNKNOWN propagation.
- Executed quality gates:
  - `uv run pytest -q tests/unit/pipeline/stages/test_evidence.py tests/unit/pipeline/stages/test_peak.py tests/unit/pipeline/test_scheduler.py`
  - `uv run pytest -q tests/integration/pipeline/test_evidence_prometheus_integration.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Senior Developer Review (AI)

- Review date: 2026-03-03
- Outcome: Approved after fixes.
- Fixed in this review pass:
  - Sustained evidence handling no longer increments streak under insufficient evidence.
  - Unknown-evidence streak handling now respects interval-gap resets.
  - Group-scoped sustained evidence evaluation no longer fails solely due to unrelated topic scopes.
  - Stage 1 -> Stage 2 -> Stage 6 gate-input flow now preserves stage-derived `evidence_status_map` into `GateInputV1`.
  - Added targeted regression tests for the above sustained/UNKNOWN edge cases.
- Remaining follow-up: none.

### Completion Notes List

- [x] Story context generated with exhaustive artifact grounding.
- [x] Status set to `ready-for-dev` in story file.
- [x] Implement story in `dev-story`.
- [x] Run `code-review` after implementation.
- [x] Added UNKNOWN propagation tests and passed all quality gates (`230 passed, 1 skipped`; Ruff clean).
- [x] Completed gate-input evidence-status propagation and end-to-end gate-input coverage.

### File List

- artifact/implementation-artifacts/2-5-unknown-evidence-propagation.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/models/evidence.py
- src/aiops_triage_pipeline/models/peak.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- src/aiops_triage_pipeline/pipeline/stages/evidence.py
- src/aiops_triage_pipeline/pipeline/stages/gating.py
- src/aiops_triage_pipeline/pipeline/stages/peak.py
- tests/integration/pipeline/test_evidence_prometheus_integration.py
- tests/unit/pipeline/stages/test_evidence.py
- tests/unit/pipeline/stages/test_gating.py
- tests/unit/pipeline/stages/test_peak.py
- tests/unit/pipeline/test_scheduler.py

### Change Log

- 2026-03-03: Implemented Story 2.5 UNKNOWN evidence propagation across Stage 1 and Stage 2; added immutable `evidence_status_map_by_scope` plumbing and UNKNOWN reason-code handling for peak/sustained paths.
- 2026-03-03: Added and passed focused + full test gates (`222 passed, 1 skipped`) and `uv run ruff check` for regression safety.
- 2026-03-03: Applied code-review fixes for sustained UNKNOWN behavior (streak hold semantics, gap-reset behavior, group-scope evidence evaluation) and added regression tests; quality gates rerun (`225 passed, 1 skipped`).
- 2026-03-03: Implemented gate-input assembly stage to propagate stage-derived evidence statuses into `GateInputV1`; added scheduler/integration gate-input UNKNOWN-flow tests and reran quality gates (`230 passed, 1 skipped`).
