# Story 2.7: Prometheus Unavailability & TelemetryDegradedEvent

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/operator,
I want the system to detect total Prometheus unavailability and emit a TelemetryDegradedEvent,
so that the pipeline does not emit misleading all-UNKNOWN cases and actions are safely capped until Prometheus recovers (FR67a).

## Acceptance Criteria

1. **Given** the pipeline attempts to query Prometheus  
   **When** Prometheus is totally unavailable (not individual missing series, but total source failure)  
   **Then** a `TelemetryDegradedEvent` is emitted containing: affected scope, reason, recovery status.

2. **And** the pipeline does **not** emit normal cases with all-UNKNOWN evidence.

3. **And** actions are capped to `OBSERVE/NOTIFY` until Prometheus recovers.

4. **And** `HealthRegistry` is updated with Prometheus status = `UNAVAILABLE` while degraded.

5. **And** when Prometheus recovers, the `TelemetryDegradedEvent` clears and normal evaluation resumes on the next interval.

6. **And** no backfill of missed intervals occurs after recovery.

7. **And** unit/integration tests verify event emission on unavailability, no all-UNKNOWN cases, action capping behavior, and recovery behavior (NFR-T2).

## Tasks / Subtasks

- [x] Task 1: Add total-outage detection in Stage 1 query path without breaking UNKNOWN semantics (AC: 1, 2)
  - [x] Distinguish **transport/source unavailability** from per-metric missing series.
  - [x] Treat connection/timeout/HTTP-source failures across the full query set as outage candidates.
  - [x] Keep partial data and per-metric missing series mapped to `EvidenceStatus.UNKNOWN` (Story 2.5 behavior unchanged).

- [x] Task 2: Emit `TelemetryDegradedEvent` and update health state on outage/recovery transitions (AC: 1, 4, 5)
  - [x] Create event payloads with `affected_scope="prometheus"`, actionable reason, and `recovery_status` (`pending`/`resolved`).
  - [x] Update `HealthRegistry` to `UNAVAILABLE` on outage and back to `HEALTHY` on recovery.
  - [x] Ensure event emission is transition-based (avoid duplicate noise each interval while already degraded).

- [x] Task 3: Prevent misleading case emission during total outage and enforce safe action posture (AC: 2, 3)
  - [x] Skip normal case generation when outage is active (no all-UNKNOWN case artifacts).
  - [x] Ensure downstream action posture is capped to `OBSERVE/NOTIFY` during outage windows.
  - [x] Preserve deterministic behavior and do not introduce ad-hoc fallback actions.

- [x] Task 4: Implement recovery semantics and no-backfill behavior (AC: 5, 6)
  - [x] On connectivity recovery, emit clear/resolved telemetry-degraded signal.
  - [x] Resume normal processing on the next scheduler boundary only.
  - [x] Do not replay or backfill missed evaluation intervals.

- [x] Task 5: Add tests for degraded and recovery flows (AC: 7)
  - [x] Unit tests for outage detection classifier (total outage vs partial metric miss).
  - [x] Unit tests for HealthRegistry transition + event payload correctness.
  - [x] Scheduler/stage tests confirming no normal-case output during outage and normal resume after recovery.
  - [x] Integration test that simulates Prometheus unavailability and validates expected logs/events/state changes.

- [x] Task 6: Quality gates
  - [x] Run focused tests for `evidence`, `scheduler`, and `health` modules.
  - [x] Run full `uv run pytest -q` and `uv run ruff check` before moving to review.

## Dev Notes

### Story Requirements

- This story implements **FR67a / FR67 / NFR-R2 / NFR-R3 / NFR-T2** behavior specifically for **total Prometheus source failure**.
- Scope boundary is explicit:
  - **In scope:** total Prometheus unavailability detection, degraded-mode eventing, health state transition, no all-UNKNOWN case emission, recovery clear behavior.
  - **Out of scope:** topology/routing changes, outbox redesign, AG5 Redis dedupe behavior, LLM/cold-path behavior.
- Critical distinction to preserve:
  - Individual missing metric series == `EvidenceStatus.UNKNOWN` (normal processing continues).
  - Total source failure == `TelemetryDegradedEvent` + safe capped behavior + no normal case emission.

### Developer Context Section

- Epic 2 sequence context:
  - Story 2.5 established UNKNOWN propagation as a first-class invariant.
  - Story 2.6 added Redis caching/read-through behavior around Stage 1/2 outputs.
  - Story 2.7 must layer outage semantics without regressing either behavior.
- Existing code signals this story is expected next:
  - `TelemetryDegradedEvent` model already exists in `models/events.py` but is not yet wired into pipeline execution paths.
  - Stage 1 currently logs per-metric query failures and returns empty lists; it does not yet represent total-source outage state.
- Implement with minimal-surface changes and keep deterministic stage boundaries.

### Technical Requirements

- Detect outage from **source connectivity failure semantics**, not from empty vectors alone.
- Treat these as outage candidates when they occur across the full metric query set within a cycle:
  - `URLError`, timeout, connection/refused/network I/O class failures.
  - Explicit non-success API responses from Prometheus query API.
- Do **not** classify as total outage when only a subset of metrics fails or returns empty results.
- Emit structured operational event fields consistently (`event_type`, `component`, `severity`, reason text).
- Maintain scheduler cadence logic:
  - 5-minute boundary alignment remains unchanged.
  - Missed intervals remain warnings.
  - No backfill after recovery.

### Architecture Compliance

- Preserve architecture invariants from planning artifacts:
  - Prometheus is sole telemetry source for Stage 1.
  - Total Prometheus unavailability is degraded-mode safety behavior, not normal UNKNOWN behavior.
  - `HealthRegistry` is the single source of component health truth.
  - Degraded handling must be explicit and observable.
- Keep hot-path deterministic and bounded:
  - No blocking retries that violate interval cadence.
  - No implicit or fabricated evidence.
- Keep action posture safe while degraded:
  - No path to high-urgency actions from outage-derived uncertainty.

### Library / Framework Requirements

- Python runtime and dependency baseline must follow project context (`Python >=3.13`, frozen Pydantic models, structlog patterns).
- Prometheus HTTP behavior references should align with official API contract (`/api/v1/query` envelope and error fields).
- Do not introduce new networking libraries for this story; stay with existing integration style unless justified.
- If surfacing connectivity probes, use documented Prometheus readiness endpoint semantics (`/-/ready`) and keep it optional/minimal.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/models/evidence.py` (if stage output needs explicit degraded metadata)
  - `src/aiops_triage_pipeline/models/events.py` (only if event model fields require tightening)
  - `src/aiops_triage_pipeline/health/registry.py` (consume existing API; avoid redesign)
- Primary test targets:
  - `tests/unit/pipeline/stages/test_evidence.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/health/test_registry.py`
  - `tests/integration/pipeline/test_evidence_prometheus_integration.py`
- Keep changes localized; do not expand into empty placeholder stages (`dispatch.py`, `outbox.py`, `topology.py`) in this story.

### Testing Requirements

- Add/adjust tests to prove:
  - total outage is detected only under full-source failure conditions,
  - partial missing-series behavior remains UNKNOWN propagation,
  - `TelemetryDegradedEvent` is emitted on outage and resolved on recovery,
  - `HealthRegistry` state transitions (`UNAVAILABLE` -> `HEALTHY`) are correct,
  - no normal all-UNKNOWN cases are emitted while outage is active,
  - no backfill occurs after recovery; next interval resumes normal behavior.
- Regression safety checks:
  - Existing Stage 1/2 UNKNOWN and findings-cache tests remain green.
  - Scheduler drift/missed-interval behavior remains unchanged.

### Previous Story Intelligence

From Story 2.6 (`2-6-redis-evidence-caching.md`):

- Keep Redis cache behavior degradable and warning-only; do not entangle Redis failure logic with Prometheus outage logic.
- Preserve deterministic keying and serialization patterns in stage outputs.
- Keep Stage 1/2 interfaces stable where possible; add explicit metadata rather than implicit behavior changes.
- Expect review scrutiny on regression risk in scheduler + evidence stage wiring.

### Git Intelligence Summary

Recent commit patterns (last 5):

- `9e00864` UNKNOWN propagation hardening across Stage 1/2 and gating.
- `6efacc1` Story 2.4 review fixes with sustained-state stability improvements.
- `1ebaaba`, `84088d0` Story 2.3 peak/cache implementation and review stabilization.
- `37843b2` Story 2.2 detector hardening.

Actionable implications for Story 2.7:

- Keep modifications concentrated in `pipeline/stages/evidence.py`, `pipeline/scheduler.py`, and focused tests.
- Maintain the established pattern of adding explicit regression tests for each changed semantic branch.
- Avoid broad refactors; this codebase has been evolving by narrow, review-driven deltas.

### Latest Tech Information

Verification date: **March 4, 2026**.

- Prometheus server latest release visible on official GitHub releases: **v3.10.0** (published February 24, 2026).
- Project baseline in `artifact/project-context.md` pins local-dev Prometheus at **v2.50.1**; this story should remain behavior-focused and not introduce version migration scope.
- Prometheus HTTP API guidance (official docs) confirms:
  - instant query endpoint: `GET /api/v1/query`
  - structured response envelope includes `status`, `data`, optional `errorType`/`error`, and optional warnings/info
- Prometheus management endpoint documentation confirms readiness endpoint `/-/ready` behavior (`200` when ready, `503` when not ready).
- Python Prometheus client latest on PyPI: **prometheus-client 0.24.1** (released January 14, 2026).

Implementation takeaway:

- Keep query/error handling aligned to documented API envelope and transport failures.
- Preserve compatibility with current pinned environment; do not fold dependency upgrades into this story.

### Project Context Reference

Mandatory guardrails from `artifact/project-context.md`:

- Never collapse UNKNOWN into PRESENT/zero.
- Keep deterministic guardrails authoritative; no ad-hoc action logic.
- Degraded dependencies must be explicit, observable, and safe.
- Use shared logging and health primitives; do not create parallel abstractions.
- Keep changes test-backed and localized.

### Story Completion Status

- Story context generation complete.
- Story file created at `artifact/implementation-artifacts/2-7-prometheus-unavailability-and-telemetrydegradedevent.md`.
- Status set to `done` after code-review fixes and verification.
- Completion note: full-source outage behavior, recovery transitions, and degraded action safety validated end-to-end.

## Project Structure Notes

- Prefer extending existing stage and scheduler orchestration instead of introducing a new orchestration layer.
- If additional stage metadata is needed (e.g., outage signal), represent it explicitly in `EvidenceStageOutput` or equivalent typed structure.
- Keep event model usage centralized (`models/events.py`) and avoid stringly-typed ad-hoc event payloads scattered across modules.

## References

- [Source: `artifact/planning-artifacts/epics.md#Story 2.7: Prometheus Unavailability & TelemetryDegradedEvent`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR67 / FR67a linkage)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-R2, NFR-R3, NFR-T2)]
- [Source: `artifact/planning-artifacts/architecture.md` (degraded-mode and HealthRegistry orchestration)]
- [Source: `artifact/project-context.md` (Critical Don't-Miss Rules, framework/testing rules)]
- [Source: `artifact/implementation-artifacts/2-6-redis-evidence-caching.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/evidence.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/models/events.py`]
- [Source: `tests/unit/pipeline/stages/test_evidence.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: `https://github.com/prometheus/prometheus/releases`]
- [Source: `https://prometheus.io/docs/prometheus/latest/querying/api/`]
- [Source: `https://prometheus.io/docs/prometheus/latest/management_api/`]
- [Source: `https://prometheus.io/docs/prometheus/latest/stability/`]
- [Source: `https://pypi.org/project/prometheus-client/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`.
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml` first backlog item in order.
- Selected story key: `2-7-prometheus-unavailability-and-telemetrydegradedevent`.
- Discovery protocol results:
  - `epics_content`: loaded from `artifact/planning-artifacts/epics.md` (selective whole-doc load)
  - `architecture_content`: loaded from `artifact/planning-artifacts/architecture.md` (selective whole-doc load)
  - `prd_content`: selectively loaded from PRD shards relevant to FR67/NFR-R2/NFR-T2
  - `ux_content`: no matching UX artifact found
  - `project_context`: loaded from `artifact/project-context.md`
- Previous story analyzed: `artifact/implementation-artifacts/2-6-redis-evidence-caching.md`.
- Git intelligence analyzed: last 5 commits with touched files.
- Web verification completed for current Prometheus and Python client references.
- Validation note: `_bmad/core/tasks/validate-workflow.xml` is not present in this repository; checklist-grounded manual validation applied.
- Dev-story implementation run executed via `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml` in YOLO mode after step confirmation.
- Stage 1 updates: added `PrometheusCollectionDiagnostics` and `collect_prometheus_samples_with_diagnostics(...)` to classify full-source outages by exception coverage across full query set.
- Scheduler updates: `run_evidence_stage_cycle(...)` now performs transition-based Prometheus health updates and emits `TelemetryDegradedEvent` (`pending`/`resolved`) on outage/recovery transitions.
- Evidence output updates: `EvidenceStageOutput` now carries `telemetry_degraded_active`, `telemetry_degraded_events`, and `max_safe_action` (`NOTIFY` during outage).
- Validation executed:
  - Focused suites: `uv run pytest -q tests/unit/pipeline/stages/test_evidence.py tests/unit/pipeline/test_scheduler.py tests/unit/health/test_registry.py tests/integration/pipeline/test_evidence_prometheus_integration.py` (53 passed).
  - Lint: `uv run ruff check src tests` (pass).

### Completion Notes List

- [x] Story context generated from epic, architecture, PRD, project-context, previous story, and git history.
- [x] Latest technical references verified from primary sources.
- [x] Implementation guardrails and file-level targets documented.
- [x] Story status set to `ready-for-dev`.
- [x] Implement story with `dev-story`.
- [x] Run `code-review` workflow after implementation.
- Added full-source Prometheus outage detection without regressing partial missing-series UNKNOWN behavior.
- Added transition-based Prometheus health updates (`UNAVAILABLE` on outage, `HEALTHY` on recovery) and telemetry degraded events.
- Added degraded-mode output metadata and safe action cap (`OBSERVE/NOTIFY` via `max_safe_action=NOTIFY`).
- Added/updated unit and integration tests for outage classification, event payload constraints, transition behavior, and recovery semantics.
- Enforced degraded action cap in gate-input assembly so PAGE/TICKET proposals are clamped during Prometheus outage.
- Tightened outage classification to count only transport failures and explicit Prometheus non-success API payloads as full-source outages.
- Extended `TelemetryDegradedEvent` with structured operational fields (`event_type`, `component`, `severity`) and validated both pending/resolved semantics.

### File List

- artifact/implementation-artifacts/2-7-prometheus-unavailability-and-telemetrydegradedevent.md
- artifact/implementation-artifacts/2-6-redis-evidence-caching.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/cache/__init__.py
- src/aiops_triage_pipeline/cache/evidence_window.py
- src/aiops_triage_pipeline/cache/findings_cache.py
- src/aiops_triage_pipeline/cache/peak_cache.py
- src/aiops_triage_pipeline/models/evidence.py
- src/aiops_triage_pipeline/models/events.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- src/aiops_triage_pipeline/pipeline/stages/anomaly.py
- src/aiops_triage_pipeline/pipeline/stages/evidence.py
- src/aiops_triage_pipeline/pipeline/stages/gating.py
- tests/integration/pipeline/test_evidence_prometheus_integration.py
- tests/unit/cache/test_evidence_window.py
- tests/unit/cache/test_findings_cache.py
- tests/unit/cache/test_peak_cache.py
- tests/unit/health/test_registry.py
- tests/unit/pipeline/stages/test_anomaly.py
- tests/unit/pipeline/stages/test_evidence.py
- tests/unit/pipeline/test_scheduler.py

## Senior Developer Review (AI)

### Outcome

Changes Requested → Fixed in this review pass.

### Findings

1. **CRITICAL:** `max_safe_action` was set during outage but not enforced in Stage 6 gate-input assembly, allowing uncapped `PAGE/TICKET` proposals to flow downstream (`src/aiops_triage_pipeline/pipeline/scheduler.py`, `src/aiops_triage_pipeline/pipeline/stages/gating.py`).
2. **HIGH:** Total-outage classification treated all `ValueError` exceptions as source-failure candidates, allowing payload-shape/config errors to be misclassified as Prometheus source outage (`src/aiops_triage_pipeline/pipeline/stages/evidence.py`).
3. **MEDIUM:** `TelemetryDegradedEvent` lacked structured operational fields required by story guardrails (`event_type`, `component`, `severity`) (`src/aiops_triage_pipeline/models/events.py`).

### Fixes Applied

- Added action-priority capping in `collect_gate_inputs_by_scope(...)` and wired `run_gate_input_stage_cycle(...)` to pass `evidence_output.max_safe_action`.
- Split diagnostics error handling: transport/network failures and explicit Prometheus non-success API payloads count toward total outage; generic shape-related `ValueError`s do not.
- Added structured fields to `TelemetryDegradedEvent`; pending events now use `severity="warning"` and recovery events use `severity="info"`.
- Added/updated tests covering cap enforcement, outage classification behavior, and event schema fields.
- Hardened `TelemetryDegradedEvent.affected_scope` to literal `prometheus` and added validation test for invalid scope values.
- Ran full regression suite to close residual testing gap (`uv run pytest -q`: 256 passed).

## Change Log

- 2026-03-04: Created Story 2.7 comprehensive implementation context and marked status `ready-for-dev`.
- 2026-03-04: Implemented Story 2.7 outage detection, transition-based telemetry degraded events, Prometheus health transitions, degraded action cap metadata, and verification tests; moved story to `review`.
- 2026-03-04: Completed adversarial code review; fixed uncapped degraded actions, tightened outage error classification, added structured TelemetryDegradedEvent fields, re-ran focused tests/lint, and moved story to `done`.
- 2026-03-04: Closed low-severity follow-ups by constraining `TelemetryDegradedEvent.affected_scope` and running full regression (`256 passed`).
