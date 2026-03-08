# Story 8.3: SN Linkage Retry & State Machine

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,  
I want SN linkage to retry with exponential backoff over a 2-hour window with FAILED_FINAL escalation,  
so that transient SN unavailability is handled gracefully and persistent failures are escalated for human attention (FR48, FR49).

## Acceptance Criteria

1. **Given** an SN linkage attempt has been initiated  
   **When** the linkage state machine processes the case  
   **Then** state transitions follow: `PENDING -> SEARCHING -> LINKED` (success path) (FR49)
2. **And** on transient failure: `SEARCHING -> FAILED_TEMP -> SEARCHING` (retry path) (FR49)
3. **And** on permanent failure: `SEARCHING -> FAILED_FINAL` (after 2-hour retry window exhausted) (FR49)
4. **And** retries use exponential backoff with jitter over the 2-hour window (FR48)
5. **And** FAILED_FINAL triggers Slack escalation (exposure-safe; denylist enforced on escalation message) (FR48)
6. **And** FAILED_TEMP cases resume retry on next cycle; FAILED_FINAL cases remain terminal (human review required)
7. **And** linkage state is persisted and survives process restart
8. **And** SN linkage is deployable as an add-on to Phase 1A without redeploying the hot-path pipeline (NFR-O5)
9. **And** unit tests verify: each state transition, exponential backoff timing, jitter application, 2-hour window expiry to FAILED_FINAL, Slack escalation content + denylist compliance, and state persistence across restart

## Tasks / Subtasks

- [x] Task 1: Extend SN linkage contract and models for retry-state semantics (AC: 1, 2, 3, 4, 6, 7)
  - [x] Extend `src/aiops_triage_pipeline/contracts/sn_linkage.py` with explicit retry-state policy knobs for Phase 1B:
    - [x] `retry_window_minutes` (default 120)
    - [x] `retry_base_seconds`, `retry_max_seconds`, `retry_jitter_ratio`
    - [x] Optional transient error classifications (e.g., timeout, connection error, HTTP 429/5xx)
  - [x] Update `config/policies/servicenow-linkage-contract-v1.yaml` with defaults aligned to FR48/FR49.
  - [x] Extend linkage outcome/state models so state machine transitions are represented explicitly without breaking existing 8.2 payload compatibility.
  - [x] Keep MI-1 posture invariants intact (`mi_creation_allowed=false` remains enforced).

- [x] Task 2: Implement deterministic SN linkage retry state machine (AC: 1, 2, 3, 4, 6)
  - [x] Add a dedicated state machine module (for example `src/aiops_triage_pipeline/pipeline/stages/linkage_state_machine.py`) with explicit transition guards:
    - [x] `PENDING -> SEARCHING -> LINKED`
    - [x] `SEARCHING -> FAILED_TEMP -> SEARCHING` while within retry window
    - [x] `SEARCHING -> FAILED_FINAL` when retry window expires
  - [x] Reuse the deterministic backoff+jitter pattern already established in `src/aiops_triage_pipeline/outbox/state_machine.py` (`compute_retry_delay_seconds`) instead of inventing a new algorithm.
  - [x] Ensure deterministic scheduling and testability: next-attempt timestamps must be reproducible from state + attempt counter + case identity.
  - [x] Classify transient vs terminal failures in a structured way and emit machine-parseable reason codes.

- [x] Task 3: Persist linkage retry state durably and recover on restart (AC: 6, 7, 8)
  - [x] Implement durable state storage (Postgres-backed) for linkage retry records so state survives process restart.
  - [x] Follow architecture conventions for hand-rolled DDL and SQLAlchemy Core patterns used by outbox modules.
  - [x] Ensure restart recovery logic resumes `FAILED_TEMP` retry candidates and preserves `FAILED_FINAL` as terminal.
  - [x] Keep hot-path independence: linkage state persistence must not block or alter hot-path triage/gating execution.

- [x] Task 4: Integrate state machine with existing SN correlation/upsert flow and linkage stage persistence (AC: 1, 2, 3, 6, 7)
  - [x] Update `src/aiops_triage_pipeline/pipeline/stages/linkage.py` orchestration to drive correlation + upsert through the new state machine lifecycle.
  - [x] Preserve prior story behavior from 8.1/8.2:
    - [x] Tiered incident correlation remains read-only on incident table.
    - [x] Problem/PIR upsert remains idempotent and write-scope-limited.
  - [x] Persist final linkage outcome to `cases/{case_id}/linkage.json` with append-only/write-once semantics and valid hash-chain dependencies.
  - [x] Ensure repeated retries for the same final state are idempotent and do not create divergent linkage artifacts.

- [x] Task 5: Implement FAILED_FINAL escalation through Slack with denylist enforcement (AC: 5)
  - [x] Add explicit FAILED_FINAL escalation dispatch path (Slack + structured log fallback) using existing integration mode semantics (`OFF|LOG|MOCK|LIVE`).
  - [x] Enforce exposure controls via shared `apply_denylist(...)` before escalation payload/log emission.
  - [x] Include audit fields required by NFR-S6 (`timestamp`, `request_id`, `case_id`, `action`, `outcome`, `latency`) and linkage context fields needed for incident triage.
  - [x] Treat Slack delivery failures as degradable events: never block pipeline progress.

- [x] Task 6: Add comprehensive tests for transitions, timing, persistence, and escalation (AC: 9)
  - [x] Add/extend unit tests for state transition table coverage (`PENDING`, `SEARCHING`, `FAILED_TEMP`, `LINKED`, `FAILED_FINAL`).
  - [x] Add deterministic backoff/jitter tests validating attempt progression and 2-hour expiry behavior.
  - [x] Add persistence tests proving restart recovery (reload persisted retry state and resume correctly).
  - [x] Add escalation tests validating denylist-safe FAILED_FINAL payload content and integration mode behavior.
  - [x] Preserve non-regression coverage for 8.1/8.2 correlation and idempotent upsert behavior.

- [x] Task 7: Run quality gates with zero-skip posture
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Confirm full regression completes with `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `8-3-sn-linkage-retry-and-state-machine`
- Story ID: `8.3`
- Epic context: Epic 8 sequence is now:
  - 8.1 completed tiered SN incident correlation.
  - 8.2 completed idempotent Problem/PIR upsert and linkage stage persistence.
  - 8.3 adds persistent retry-state control, 2-hour expiry, and FAILED_FINAL escalation.
  - 8.4 will add fallback-rate metrics and SLO observability.
- Current baseline from code:
  - `ServiceNowClient.correlate_incident(...)` and `upsert_problem_and_pir_tasks(...)` are implemented in `src/aiops_triage_pipeline/integrations/servicenow.py`.
  - `execute_servicenow_linkage_and_persist(...)` exists in `src/aiops_triage_pipeline/pipeline/stages/linkage.py`.
  - `CaseFileLinkageV1` and linkage stage write/read/hash validation are implemented (`models/case_file.py`, `storage/casefile_io.py`, `pipeline/stages/casefile.py`).
  - Outbox already implements deterministic exponential backoff with bounded jitter (`outbox/state_machine.py`) and should be reused for consistency.

### Technical Requirements

1. Implement explicit SN linkage state machine transitions required by FR49, including transient and terminal paths.
2. Retry cadence must use exponential backoff with jitter within a strict 2-hour window (FR48).
3. Transient failures must move to `FAILED_TEMP` and be retried on later cycles until expiry.
4. Retry-window exhaustion must transition to terminal `FAILED_FINAL`.
5. `FAILED_FINAL` must trigger exposure-safe Slack escalation with denylist filtering.
6. Linkage retry state must be durably persisted and recoverable across process restart.
7. Hot-path determinism remains authoritative; SN linkage remains cold-path/add-on behavior (NFR-O5, FR66 context).
8. Preserve MI-1 posture: no automated major incident creation path.
9. Preserve idempotent Problem/PIR behavior and read/write scope boundaries introduced in 8.1/8.2.
10. Structured audit logging must include required NFR-S6 fields on each linkage attempt/transition/escalation.
11. HTTP 429/5xx/timeouts should be treated as transient candidates unless policy marks otherwise.
12. If upstream returns explicit retry hints (e.g., `Retry-After`), schedule must respect policy bounds and not violate the 2-hour terminal window.

### Architecture Compliance

- Keep deployment independence:
  - SN linkage retry processing remains independently deployable/restartable cold-path behavior (NFR-O5).
  - No hot-path pipeline redeploy requirement to activate linkage add-on behavior.
- Keep package boundaries:
  - ServiceNow API behavior in `integrations/servicenow.py`.
  - Retry orchestration in linkage stage modules.
  - Durable state store with SQLAlchemy Core and hand-rolled DDL patterns consistent with outbox architecture.
- Keep append-only CaseFile model:
  - `linkage.json` remains write-once final stage artifact.
  - Hash-chain dependency rules remain enforced.
- Keep cross-cutting safety:
  - Shared denylist enforcement function only.
  - Structured logging and correlation fields preserved.
  - Degradable failure handling without silent behavior.

### Library / Framework Requirements

- Reuse existing pinned stack and project conventions (no new framework churn expected):
  - Python 3.13
  - pydantic 2.12.5
  - SQLAlchemy 2.0.47 (Core style)
  - structlog 25.5.0
  - pydantic-settings ~2.13.1
- Reuse existing deterministic backoff pattern from outbox state machine utilities.
- Continue using current integration mode contract (`OFF|LOG|MOCK|LIVE`) for ServiceNow and Slack paths.

### File Structure Requirements

Files expected to be created/updated:

- `src/aiops_triage_pipeline/contracts/sn_linkage.py`
- `config/policies/servicenow-linkage-contract-v1.yaml`
- `src/aiops_triage_pipeline/integrations/servicenow.py`
- `src/aiops_triage_pipeline/pipeline/stages/linkage.py`
- `src/aiops_triage_pipeline/models/case_file.py` (if explicit linkage state fields are introduced)
- `src/aiops_triage_pipeline/storage/casefile_io.py` (if linkage schema/hash inputs change)
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` (if linkage validation fields expand)
- `tests/unit/integrations/test_servicenow.py`
- `tests/unit/pipeline/stages/test_linkage.py`
- `tests/unit/contracts/test_policy_models.py`
- New state-machine persistence test module(s) in `tests/unit/` and/or `tests/integration/` as needed

Files to avoid changing in this story:

- `src/aiops_triage_pipeline/pipeline/stages/gating.py` (deterministic action authority is out of scope)
- `src/aiops_triage_pipeline/integrations/pagerduty.py` (unless strict handoff adjustments are required)
- Unrelated epic/story artifacts

### Testing Requirements

Minimum required coverage:

1. `PENDING -> SEARCHING -> LINKED` success path.
2. `SEARCHING -> FAILED_TEMP -> SEARCHING` transient retry path.
3. `SEARCHING -> FAILED_FINAL` transition when retry window is exhausted.
4. Deterministic exponential backoff and bounded jitter behavior for multiple attempts.
5. 2-hour window enforcement with no retry scheduled after terminal threshold.
6. Persisted retry state survives process restart and resumes correctly.
7. FAILED_FINAL escalation sends denylist-safe Slack payload (or structured log fallback).
8. OFF/LOG/MOCK/LIVE behavior remains deterministic and non-destructive in non-LIVE modes.
9. Existing 8.1/8.2 tests continue passing (tiered correlation + idempotent upsert non-regression).
10. Linkage stage hash-chain and write-once invariants remain valid for final persisted linkage artifacts.

### Previous Story Intelligence

Extracted from stories 8.1 and 8.2:

- Keep ServiceNow read/write scope strict: incident table read-only; problem/task writes only.
- Preserve deterministic selection and idempotent upsert behavior based on stable external IDs.
- Fail fast on invalid input and duplicate external-id lookup ambiguity.
- Keep linkage persistence write-once and hash-chain safe; avoid mutating already-persisted stage artifacts.
- Keep denylist enforcement explicit in code and tests for all outbound SN/Slack payloads.
- Keep mode-aware behavior stable; default-safe modes must not emit outbound side effects.

### Git Intelligence Summary

Recent commits indicate where to continue implementation:

- `04df332` finalized 8.2 linkage persistence and review fixes across `servicenow.py`, linkage stage, casefile model/storage, and tests.
- `d87532d` hardened correlation logic and contract behavior in 8.1.
- `a0ac885` introduced initial ServiceNow correlation implementation and contract/policy expansion.

Actionable implication:

- Build 8.3 directly on existing ServiceNow + linkage stage modules; do not fork alternate pathways.
- Preserve established contract-first update pattern (contract + policy + code + tests together).

### Latest Tech Information

Research timestamp: 2026-03-08.

- ServiceNow Table API supports the core operations required for this story (`GET`, `POST`, `PATCH`) with query controls such as `sysparm_query`, `sysparm_fields`, and `sysparm_limit`.
- ServiceNow REST API rate-limiting documentation describes 429 handling signals including `Retry-After` and `X-RateLimit-*` headers; this should be treated as transient failure input for retry scheduling.
- Slack incoming webhooks are rate-limited (documented baseline of roughly 1 request/second per webhook); 429 responses may include `Retry-After`.
- Exponential backoff with jitter remains current best-practice for distributed retry behavior to avoid synchronized retry storms.

Implementation takeaway:

- Treat ServiceNow 429/5xx/timeout conditions as transient (`FAILED_TEMP`) while within retry window.
- Respect retry hints (`Retry-After`) when available, bounded by policy and 2-hour terminal window.
- Keep FAILED_FINAL Slack escalation resilient and exposure-safe, with non-blocking failure behavior.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Reuse shared denylist enforcement and avoid boundary-specific reimplementation.
- Preserve deterministic guardrail authority (SN linkage cannot override hot-path decisioning).
- Keep integration defaults non-destructive and mode-driven.
- Maintain structured logging with correlation-safe fields and no secret leakage.
- Any contract/policy behavior changes must include targeted tests.

### Project Structure Notes

- Existing linkage orchestration entrypoint in `pipeline/stages/linkage.py` should remain the integration point for state-machine wiring.
- Existing ServiceNow adapter in `integrations/servicenow.py` should remain the single implementation surface for SN API calls.
- Existing outbox retry utility provides a proven deterministic jitter pattern and should be reused for consistency.
- Final linkage artifact remains `cases/{case_id}/linkage.json`; intermediate retry state should be persisted separately in durable storage.

### References

- [Source: `artifact/planning-artifacts/epics.md` (Epic 8, Story 8.3 acceptance criteria)]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR48, FR49, FR50)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-S5, NFR-S6, NFR-O5, NFR-R1/R3)]
- [Source: `artifact/planning-artifacts/prd/project-scoping-phased-development.md` (Phase 1B exit criteria)]
- [Source: `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md` (cold-path staging model)]
- [Source: `artifact/planning-artifacts/prd/user-journeys.md` (FAILED_FINAL audit and escalation path)]
- [Source: `artifact/project-context.md` (implementation guardrails and testing posture)]
- [Source: `artifact/implementation-artifacts/8-2-idempotent-problem-and-pir-task-upsert.md` (previous-story learnings)]
- [Source: `artifact/implementation-artifacts/8-1-tiered-servicenow-incident-correlation.md` (correlation baseline and constraints)]
- ServiceNow Table API docs: https://www.servicenow.com/docs/bundle/zurich-api-reference/page/integrate/inbound-rest/concept/c_TableAPI.html
- ServiceNow REST API rate-limit headers: https://www.servicenow.com/docs/bundle/zurich-platform-administration/page/administer/contextual-security/reference/r_MonitorRateLimits.html
- Slack webhook rate limits: https://api.slack.com/apis/rate-limits
- Exponential backoff + jitter guidance: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

### Story Completion Status

- Story document created: `artifact/implementation-artifacts/8-3-sn-linkage-retry-and-state-machine.md`
- Workflow status set for handoff: `ready-for-dev`
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Implemented SN linkage retry policy knobs in contract + policy artifact.
- Added durable retry-state modules:
  - `src/aiops_triage_pipeline/linkage/schema.py`
  - `src/aiops_triage_pipeline/linkage/state_machine.py`
  - `src/aiops_triage_pipeline/linkage/repository.py`
- Updated linkage orchestration in `src/aiops_triage_pipeline/pipeline/stages/linkage.py` to use retry state machine + terminal-only linkage stage persistence.
- Extended ServiceNow transport error metadata extraction (`http_status`, `retry_after_seconds`) in `src/aiops_triage_pipeline/integrations/servicenow.py`.
- Added FAILED_FINAL Slack escalation path in `src/aiops_triage_pipeline/integrations/slack.py`.
- Review remediation (2026-03-08): fixed FAILED_FINAL escalation coverage for all terminal outcomes, enforced denylist on fallback escalation logs, and added terminal-state linkage.json recovery when restart finds LINKED/FAILED_FINAL without stage artifact.
- Validation commands executed:
  - `uv run ruff check`
  - `uv run pytest -q -m "not integration"`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Implemented retry-state contract knobs: retry window/base/max/jitter and transient error classifications.
- Implemented deterministic state transitions `PENDING -> SEARCHING -> LINKED`, `SEARCHING -> FAILED_TEMP -> SEARCHING`, and `SEARCHING -> FAILED_FINAL`.
- Added durable Postgres/SQLAlchemy Core retry-state storage with restart recovery query support (`FAILED_TEMP` due candidates).
- Integrated linkage stage with durable retry orchestration, terminal idempotency guards, and final-only linkage.json persistence.
- Added FAILED_FINAL escalation path with denylist-safe Slack payload handling and structured-log fallback.
- Hardened terminal recovery: restart path now rehydrates missing terminal linkage.json from durable retry state for both `LINKED` and `FAILED_FINAL`.
- Expanded AC9 timing coverage with deterministic exponential progression checks, jitter bound assertions, and bounded `Retry-After` scheduling tests.
- Added/updated tests for contracts, ServiceNow error classification metadata, retry state machine, retry repository, linkage stage retry lifecycle, and Slack escalation behavior.
- Quality gates passed:
  - `uv run ruff check` -> pass
  - `uv run pytest -q -m "not integration"` -> `788 passed, 19 deselected`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` -> `807 passed`, `0 skipped`

### File List

- artifact/implementation-artifacts/8-3-sn-linkage-retry-and-state-machine.md
- artifact/implementation-artifacts/sprint-status.yaml
- config/policies/servicenow-linkage-contract-v1.yaml
- src/aiops_triage_pipeline/contracts/sn_linkage.py
- src/aiops_triage_pipeline/integrations/servicenow.py
- src/aiops_triage_pipeline/integrations/slack.py
- src/aiops_triage_pipeline/linkage/__init__.py
- src/aiops_triage_pipeline/linkage/schema.py
- src/aiops_triage_pipeline/linkage/state_machine.py
- src/aiops_triage_pipeline/linkage/repository.py
- src/aiops_triage_pipeline/pipeline/stages/linkage.py
- tests/unit/contracts/test_policy_models.py
- tests/unit/integrations/test_servicenow.py
- tests/unit/integrations/test_slack_notification.py
- tests/unit/linkage/test_state_machine.py
- tests/unit/linkage/test_repository.py
- tests/unit/pipeline/stages/test_linkage.py

## Change Log

- 2026-03-08: Implemented Story 8.3 retry-state machine, durable linkage retry persistence, terminal FAILED_FINAL escalation, and full regression validation with zero skips.
- 2026-03-08: Completed code-review remediation; fixed terminal escalation/denylist gaps, added restart-stage recovery for terminal states, and strengthened AC9 retry/backoff test coverage.
