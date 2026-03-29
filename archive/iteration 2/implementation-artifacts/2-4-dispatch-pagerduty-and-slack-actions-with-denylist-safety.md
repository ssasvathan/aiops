# Story 2.4: Dispatch PagerDuty and Slack Actions with Denylist Safety

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,  
I want outbound action dispatch to be reliable and safe,  
so that external notifications are delivered without leaking denied content.

**Implements:** FR32, FR33, FR34, FR35

## Acceptance Criteria

1. **Given** an action decision requires `PAGE` or `NOTIFY`  
   **When** dispatch executes  
   **Then** PagerDuty and Slack payloads are generated from decision context  
   **And** denylist filtering is applied before every outbound payload is sent.

2. **Given** Slack delivery fails or is unavailable  
   **When** a NOTIFY/degraded/postmortem message is attempted  
   **Then** the system emits an equivalent structured log event fallback  
   **And** the pipeline continues without halting.

## Tasks / Subtasks

- [x] Task 1: Implement explicit `NOTIFY` dispatch path in Stage 7 (AC: 1)
  - [x] Extend `dispatch_action` in `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` so `final_action == Action.NOTIFY` triggers Slack notification dispatch (today only PAGE goes through PagerDuty and postmortem is orthogonal).
  - [x] Keep PAGE and postmortem behavior unchanged: PAGE still triggers `PagerDutyClient.send_page_trigger`, and `postmortem_required` still dispatches independently.
  - [x] Continue using topology fallback (`routing_key="unknown"` when `routing_context is None`) for outbound fields.
- [x] Task 2: Add Slack notification API for regular NOTIFY decisions with denylist safety (AC: 1, 2)
  - [x] Add a dedicated method to `src/aiops_triage_pipeline/integrations/slack.py` for NOTIFY action payloads (separate from degraded-mode and postmortem paths).
  - [x] Build payload fields from decision/routing context (`case_id`, `action_fingerprint`, `routing_key`, `support_channel`, reason codes) and sanitize via shared `apply_denylist(...)` before logging or webhook POST.
  - [x] Ensure OFF|LOG|MOCK|LIVE semantics match existing integration pattern.
- [x] Task 3: Enforce denylist consistently at both PagerDuty and Slack outbound boundaries (AC: 1)
  - [x] Apply shared denylist function to PagerDuty trigger payload shaping in `src/aiops_triage_pipeline/integrations/pagerduty.py` before outbound write (currently no denylist call on PagerDuty path).
  - [x] Preserve required PagerDuty contract semantics: `dedup_key == action_fingerprint`, `event_action == "trigger"`, service `routing_key` from settings.
  - [x] Keep denylist logic centralized in `src/aiops_triage_pipeline/denylist/enforcement.py`; do not create boundary-specific filtering logic.
- [x] Task 4: Add structured fallback logging guarantees for Slack failures/unavailability (AC: 2)
  - [x] Confirm/log a deterministic structured event for NOTIFY when webhook is missing or POST fails in LIVE mode.
  - [x] Confirm no exception propagates from Slack integration paths back to scheduler loop (dispatch must remain non-blocking).
  - [x] Include enough identifiers in fallback logs for audit traceability (`case_id`, `action_fingerprint`, integration mode, outcome/failure reason).
- [x] Task 5: Wire and validate runtime configuration contracts (AC: 1, 2)
  - [x] Keep using `INTEGRATION_MODE_SLACK`, `SLACK_WEBHOOK_URL`, and `PD_ROUTING_KEY` from `src/aiops_triage_pipeline/config/settings.py`.
  - [x] Ensure `src/aiops_triage_pipeline/__main__.py` hot-path wiring stays constructor-injected only (no module-level singleton wiring changes).
  - [x] Do not change action-cap logic or rule-engine outputs in this story.
- [x] Task 6: Expand unit tests for dispatch/integration behavior (AC: 1, 2)
  - [x] Extend `tests/unit/pipeline/stages/test_dispatch.py` with explicit NOTIFY -> Slack dispatch assertions and PAGE+postmortem coexistence regressions.
  - [x] Extend `tests/unit/integrations/test_slack_notification.py` (or split into clearer files) for NOTIFY payload path across OFF|LOG|MOCK|LIVE, including denylist redaction and HTTP failure fallback logs.
  - [x] Extend `tests/unit/integrations/test_pagerduty.py` to verify denylist-safe payload shaping while preserving dedup semantics.
  - [x] Add/adjust tests in `tests/unit/denylist/` only if shared denylist behavior itself changes.
- [x] Task 7: Run quality gates with zero skipped tests (AC: 1, 2)
  - [x] `uv run ruff check`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Verify full regression completes with `0 skipped` per sprint quality gate.

## Dev Notes

### Developer Context Section

- Story 2.4 is primarily a **dispatch hardening and integration-completeness** story.
- Current implementation state:
  - `dispatch_action` currently triggers PagerDuty only for `PAGE`, and Slack only for postmortem obligations (`postmortem_required`), not regular `NOTIFY` action dispatch.
  - Slack integration already has robust OFF|LOG|MOCK|LIVE handling and denylist-safe postmortem/degraded-mode paths.
  - PagerDuty integration currently posts Events V2 payloads with dedup behavior, but does not apply explicit denylist sanitization before outbound write.
- Do not redesign stage ordering or outbox architecture. Keep work localized to Stage 7 and integration adapters.

### Technical Requirements

- FR32: PAGE actions trigger PagerDuty Events V2 with dedup semantics keyed by action fingerprint.
- FR33: NOTIFY/degraded/postmortem notifications flow through Slack integration.
- FR34: Slack unavailability must degrade to structured log fallback; hot-path continues.
- FR35 / NFR-S2: Shared denylist enforcement is required at every outbound boundary (PagerDuty + Slack for this story).
- NFR-I2: Degradable integration failures must not halt pipeline cycle execution.
- NFR-I3: PagerDuty dedup uses action fingerprint as dedup key.

### Architecture Compliance

- Preserve integration mode framework (`OFF|LOG|MOCK|LIVE`) and default-safe behavior.
- Preserve composition-root dependency injection in `__main__.py`; no DI framework or globals.
- Keep cross-cutting denylist enforcement centralized in `apply_denylist(...)`.
- Do not alter guardrail authority (rule engine remains decision source; dispatch executes finalized decision only).

### Library / Framework Requirements

- Locked runtime dependencies from `pyproject.toml` and project context:
  - Python >= 3.13
  - SQLAlchemy == 2.0.47 (project lock; latest observed on 2026-03-22: 2.0.48)
  - pydantic == 2.12.5 (matches latest observed on 2026-03-22)
  - confluent-kafka == 2.13.0 (project lock; latest observed on 2026-03-22: 2.13.2)
  - structlog == 25.5.0 (matches latest observed on 2026-03-22)
- Do not upgrade dependencies in this story unless required for a security fix.

### File Structure Requirements

Primary implementation files:
- `src/aiops_triage_pipeline/pipeline/stages/dispatch.py`
- `src/aiops_triage_pipeline/integrations/slack.py`
- `src/aiops_triage_pipeline/integrations/pagerduty.py`

Support/reference files:
- `src/aiops_triage_pipeline/denylist/enforcement.py`
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/__main__.py`

Primary test files:
- `tests/unit/pipeline/stages/test_dispatch.py`
- `tests/unit/integrations/test_slack_notification.py`
- `tests/unit/integrations/test_pagerduty.py`

### Testing Requirements

- Add deterministic unit tests for:
  - `NOTIFY` dispatch route invokes Slack path with correct sanitized context.
  - Slack LIVE webhook failure logs structured fallback and does not raise.
  - PagerDuty payload remains dedup-correct and denylist-safe.
- Preserve existing passing tests; extend coverage rather than refactor unrelated modules.
- Run full regression with required Docker-enabled command and enforce `0 skipped`.

### Previous Story Intelligence

- Story 2.3 established outbox publish concurrency safety and reinforced strict quality-gate discipline (`ruff` + full pytest, 0 skipped).
- Keep Story 2.4 scope focused on dispatch/integration boundaries; do not intermingle outbox state-machine changes.
- Maintain completion discipline: explicit subtasks, explicit file list, no claim without test evidence.

### Git Intelligence Summary

Recent commits indicate Epic 2 work is being completed incrementally with focused story scopes and review loops:
- `0b670fd` review completion for Story 2.2
- `7aa68be` full workflow completion for Story 2.2
- `7d2f3e2` follow-up fixes/artifacts for Story 2.1

Actionable guidance:
- Keep the patch narrow to Stage 7 + integrations + matching tests.
- Preserve naming and structured logging conventions already used in integrations.

### Latest Tech Information

External lookup date: 2026-03-22.

- PagerDuty Events API v2 still uses `POST https://events.pagerduty.com/v2/enqueue` with trigger payload keys including `routing_key`, `event_action`, and `dedup_key`.
- Slack incoming webhooks continue to use HTTP POST of JSON payloads to webhook URLs, with documented non-200 error scenarios that should be handled explicitly.
- SQLAlchemy 2.x `Select.with_for_update(skip_locked=True)` remains the canonical API for SKIP LOCKED usage; keep current project lock unless coordinated upgrade.

### Project Context Reference

Applied `archive/project-context.md` constraints:
- Python 3.13 typing style and frozen Pydantic contracts.
- Shared denylist and structured logging conventions.
- No module-level mutable singletons.
- Integration safety defaults and non-blocking degraded behavior.
- Zero-skip full-suite gate discipline.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 2, Story 2.4]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR32-FR35]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-S2, NFR-I2, NFR-I3]
- [Source: `artifact/planning-artifacts/prd/event-driven-pipeline-specific-requirements.md` — outbound interfaces]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md` — Stage 7 dispatch boundaries]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/dispatch.py`]
- [Source: `src/aiops_triage_pipeline/integrations/pagerduty.py`]
- [Source: `src/aiops_triage_pipeline/integrations/slack.py`]
- [Source: `src/aiops_triage_pipeline/denylist/enforcement.py`]
- [Source: `tests/unit/pipeline/stages/test_dispatch.py`]
- [Source: `tests/unit/integrations/test_pagerduty.py`]
- [Source: `tests/unit/integrations/test_slack_notification.py`]
- [Source: `https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks`]
- [Source: `https://docs.sqlalchemy.org/en/20/core/selectable.html`]

## Dev Agent Record

### Agent Model Used

gpt-5-codex

### Debug Log References

- Create-story workflow executed in YOLO/full-auto mode for explicit story key `2-4-dispatch-pagerduty-and-slack-actions-with-denylist-safety`.
- Context assembled from Epic 2 Story 2.4, PRD FR/NFR definitions, architecture boundary docs, previous story (2.3), git history, and current source/test inspection.
- Dev implementation completed for Stage 7 dispatch and integrations: NOTIFY Slack dispatch path, PagerDuty denylist-safe payload shaping, and fallback logging hardening.
- Validation runs executed:
  - `uv run pytest -q tests/atdd/test_story_2_4_dispatch_pagerduty_and_slack_red_phase.py tests/unit/pipeline/stages/test_dispatch.py tests/unit/integrations/test_slack_notification.py tests/unit/integrations/test_pagerduty.py`
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Story artifact created with `ready-for-dev` status and comprehensive implementation guardrails for dispatch/integration safety.
- Sprint tracking should now move Story 2.4 from `backlog` to `ready-for-dev`.
- Scope intentionally constrained to this workflow step only (story creation and status transition).
- ATDD workflow `bmad-tea-testarch-atdd` executed in full-auto mode for Story 2.4.
- Added red-phase acceptance tests in `tests/atdd/test_story_2_4_dispatch_pagerduty_and_slack_red_phase.py` plus fixture support in `tests/atdd/fixtures/story_2_4_test_data.py`.
- Red-phase verification command executed: `uv run pytest -q tests/atdd/test_story_2_4_dispatch_pagerduty_and_slack_red_phase.py` → `3 failed` (expected for pre-implementation ATDD).
- ATDD artifacts generated: checklist and subagent-style JSON summaries under `artifact/test-artifacts/`.
- Sprint status transitioned from `ready-for-dev` to `in-progress` for story `2-4-dispatch-pagerduty-and-slack-actions-with-denylist-safety`.
- Implemented `NOTIFY` dispatch path in Stage 7 via `SlackClient.send_notification(...)` (with compatibility alias).
- Added denylist-aware PagerDuty outbound shaping while preserving dedup contract (`dedup_key == action_fingerprint`).
- Added deterministic Slack NOTIFY fallback logging for missing webhook and HTTP errors; no exception propagation.
- Extended unit coverage for dispatch, Slack NOTIFY mode matrix, and PagerDuty denylist behavior; updated ATDD story tests to green-phase expectations.
- Full project regression completed with zero skips: `927 passed`.
- Code review completed in full-auto mode; all identified CHML findings were fixed in code and tests.
- Hardened outbound safety by preserving PagerDuty dedup semantics while redacting denylisted `action_fingerprint` from outbound custom details/logs.
- Replaced raw exception-string logging in Slack/PagerDuty fallback paths with non-sensitive `error_type` fields.
- Aligned scheduler and integration tests with the hardened fallback logging contract.

### File List

- `artifact/implementation-artifacts/2-4-dispatch-pagerduty-and-slack-actions-with-denylist-safety.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `tests/atdd/test_story_2_4_dispatch_pagerduty_and_slack_red_phase.py`
- `tests/atdd/fixtures/story_2_4_test_data.py`
- `artifact/test-artifacts/atdd-checklist-2-4-dispatch-pagerduty-and-slack-actions-with-denylist-safety.md`
- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-22T20-40-57Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-22T20-40-57Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-22T20-40-57Z.json`
- `src/aiops_triage_pipeline/pipeline/stages/dispatch.py`
- `src/aiops_triage_pipeline/integrations/slack.py`
- `src/aiops_triage_pipeline/integrations/pagerduty.py`
- `tests/unit/pipeline/stages/test_dispatch.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/unit/integrations/test_slack_notification.py`
- `tests/unit/integrations/test_pagerduty.py`

## Story Completion Status

- Story status: `done`
- Completion note: Story 2.4 implementation and code-review gates are complete; CHML review findings were fixed and full regression passed with zero skips.

## Senior Developer Review (AI)

- Reviewer: `Sas`
- Date: `2026-03-22`
- Outcome: `Approve`
- Findings identified: 1 High, 1 Medium, 2 Low
- Findings resolved: 1 High, 1 Medium, 2 Low
- AC coverage verdict:
  - AC1: Implemented and validated; denylist applied at PagerDuty/Slack outbound boundaries with tests.
  - AC2: Implemented and validated; Slack fallback logging on missing webhook/send failure is structured and non-blocking.
- Notes:
  - Verified story claims against implementation and git-changed files.
  - Fixed denylist leakage risk in PagerDuty LIVE payload/log custom details while preserving `dedup_key == action_fingerprint`.
  - Hardened fallback logging to avoid raw exception-string leakage.
  - Re-ran lint + full Docker-enabled regression with zero skips.

## Change Log

- 2026-03-22: Completed `bmad-bmm-code-review` for Story 2.4, fixed all CHML findings, updated tests, and promoted story status to `done`.
