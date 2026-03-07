# Story 5.8: Slack Notification & Structured Log Fallback

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want SOFT postmortem enforcement sent via Slack when PM_PEAK_SUSTAINED fires and structured log fallback when Slack is not configured,
so that postmortem obligations are communicated and no notification is silently lost (FR44, FR45).

## Acceptance Criteria

1. **Given** the ActionDecisionV1 has `postmortem_required=True` with `postmortem_mode=SOFT`
   **When** the notification is dispatched
   **Then** a postmortem enforcement notification is sent to Slack containing: `case_id`, `final_action`, `routing_key`, `support_channel`, `postmortem_required`, `reason_codes` (FR44).
2. **And** the Slack notification enforces the exposure denylist — denied fields/values are removed from the notification payload before formatting or logging (architecture decision 2B, FR25).
3. **When** Slack is not configured (LOG mode, no webhook URL) or unavailable (LIVE mode HTTP failure)
   **Then** a structured `NotificationEvent` is emitted to logs as JSON with the same denylist-filtered fields (FR45).
4. **And** the pipeline continues without interruption — Slack unavailability never blocks processing (NFR-R1).
5. **And** the integration respects `INTEGRATION_MODE_SLACK`: `OFF` (silent drop), `LOG` (structured log only, no HTTP), `MOCK` (log + mock_send_count increment, no HTTP), `LIVE` (log + HTTP POST to configured webhook).
6. **And** unit tests verify: Slack notification content and denylist compliance, structured log fallback, Slack unavailability handling, each integration mode behavior (OFF/LOG/MOCK/LIVE).
7. **And** when `postmortem_required=False`, no Slack notification or NotificationEvent is emitted from the postmortem dispatch path.

## Tasks / Subtasks

- [x] Task 1: Add `NotificationEvent` model to `models/events.py` (AC: 3)
  - [x] Define `NotificationEvent(BaseModel, frozen=True)` with fields: `event_type: Literal["NotificationEvent"] = "NotificationEvent"`, `case_id: str`, `final_action: str`, `routing_key: str`, `support_channel: str | None`, `postmortem_required: bool`, `reason_codes: tuple[str, ...]`.
  - [x] Model is frozen and immutable — consistent with `DegradedModeEvent` and `TelemetryDegradedEvent` pattern.

- [x] Task 2: Add `SLACK_WEBHOOK_URL` setting to `config/settings.py` (AC: 5)
  - [x] Add `SLACK_WEBHOOK_URL: str | None = None` to `Settings`.
  - [x] Log `SLACK_WEBHOOK_URL` presence (never the value) in `log_active_config`: `"[CONFIGURED]"` if set, `"[NOT SET]"` otherwise — mirrors `PD_ROUTING_KEY` pattern.

- [x] Task 3: Implement `send_postmortem_notification(...)` in `integrations/slack.py` (AC: 1–5)
  - [x] Add method `send_postmortem_notification(*, case_id, final_action, routing_key, support_channel, postmortem_required, reason_codes, denylist)` to `SlackClient`.
  - [x] Build notification fields dict from the six AC-required fields.
  - [x] Apply `apply_denylist(fields, denylist)` from `denylist.enforcement` — use sanitized dict for all downstream formatting and logging.
  - [x] OFF mode: silent drop — no log, no HTTP call.
  - [x] LOG/MOCK/LIVE modes: emit structured log event `"postmortem_notification_dispatch"` with all sanitized fields + `slack_mode`.
  - [x] LOG mode: return after structured log (no HTTP).
  - [x] MOCK mode: increment `_mock_send_count`, return (no HTTP).
  - [x] LIVE mode with no webhook: log warning `"postmortem_notification_no_webhook"`, return — no crash.
  - [x] LIVE mode with webhook: POST sanitized payload to webhook; log outcome + any HTTP error; catch all exceptions and log as warning — do NOT propagate (Slack is degradable per NFR-R1).
  - [x] `reason_codes` must be serialized as a list (not tuple) in the log/webhook payload for JSON compatibility.

- [x] Task 4: Extend `dispatch_action()` in `pipeline/stages/dispatch.py` (AC: 1, 4, 7)
  - [x] Add `slack_client: SlackClient` and `denylist: DenylistV1` keyword-only parameters to `dispatch_action(...)`.
  - [x] After the PAGE/non-PAGE dispatch block: check `decision.postmortem_required`.
  - [x] If `postmortem_required=True`: call `slack_client.send_postmortem_notification(...)` with `case_id`, `decision.final_action.value`, `topology_routing_key`, `routing_context.support_channel if routing_context else None`, `decision.postmortem_required`, `decision.postmortem_reason_codes`, `denylist`.
  - [x] If `postmortem_required=False`: no Slack call, no log entry from this path.
  - [x] Postmortem notification is orthogonal to PAGE action — a PAGE decision may ALSO trigger postmortem notification if `postmortem_required=True`; these are independent dispatch paths.
  - [x] Import `SlackClient` from `integrations.slack` and `DenylistV1` from `denylist.loader` — no circular deps (dispatch.py is in pipeline/stages/, which is the consumer of integrations/).

- [x] Task 5: Unit tests for `send_postmortem_notification` in `tests/unit/integrations/test_slack_notification.py` (AC: 1–6)
  - [x] Test OFF mode: silent drop — no log entries, no HTTP call, mock_send_count=0.
  - [x] Test LOG mode: structured log `"postmortem_notification_dispatch"` emitted with all six fields, no HTTP call.
  - [x] Test MOCK mode: structured log emitted, mock_send_count incremented to 1, no HTTP call.
  - [x] Test LIVE mode (mocked urllib): HTTP POST sent, log emitted with outcome, mock_send_count stays 0.
  - [x] Test LIVE mode no webhook: warning `"postmortem_notification_no_webhook"` logged, no HTTP call, no exception.
  - [x] Test LIVE mode HTTP error: exception caught, warning logged, does NOT propagate.
  - [x] Test denylist enforcement — field name denied: denied field absent from log event fields.
  - [x] Test denylist enforcement — value pattern denied: field with matching value absent from log event fields.
  - [x] Test `reason_codes` appears as list (not tuple) in log output.
  - [x] Test OFF mode when `postmortem_required=False` field is in payload: still silently drops.

- [x] Task 6: Extend `tests/unit/pipeline/stages/test_dispatch.py` (AC: 4, 6, 7)
  - [x] Test: `postmortem_required=True` → `slack_client.send_postmortem_notification` called with correct `case_id`, `final_action`, `routing_key`, `support_channel`, `postmortem_required=True`, `reason_codes`.
  - [x] Test: `postmortem_required=False` → Slack client NOT called.
  - [x] Test: `final_action=PAGE` with `postmortem_required=True` → both PD trigger AND Slack notification dispatched.
  - [x] Test: `final_action=NOTIFY` (non-PAGE) with `postmortem_required=True` → PD NOT called, Slack IS called.
  - [x] Test: `routing_context=None` with `postmortem_required=True` → `support_channel=None` passed to Slack client, no crash.
  - [x] Use mock `SlackClient` (or real SlackClient in MOCK mode) to assert call behavior without HTTP.

- [x] Task 7: Run quality gates with zero skips (AC: all)
  - [x] `uv run pytest -q tests/unit/integrations/test_slack_notification.py` — 13 passed
  - [x] `uv run pytest -q tests/unit/pipeline/stages/test_dispatch.py` — 14 passed
  - [x] `uv run ruff check` — All checks passed
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` — 578 passed, 0 skipped

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-8-slack-notification-and-structured-log-fallback`
  - Story ID: `5.8`
- Epic context: Epic 5 covers Deterministic Safety Gating & Action Execution (AG0–AG6 + notification dispatch). Story 5.7 implemented PagerDuty PAGE dispatch. Story 5.8 completes the notification side: SOFT postmortem enforcement via Slack or structured log fallback.
- **Critical insight — scope boundary**: Story 5.8 adds the `send_postmortem_notification(...)` method to the EXISTING `SlackClient` in `integrations/slack.py`. Do NOT replace or modify `send_degraded_mode_event(...)`. The two methods are independent: one handles operational degraded-mode events (Story 5.5), the other handles postmortem obligation notifications (Story 5.8).
- **Critical insight — dispatch.py extension**: `dispatch_action()` currently has two parameters: `pd_client` and `routing_context`. Story 5.8 adds `slack_client: SlackClient` and `denylist: DenylistV1` as additional keyword-only parameters. All existing callers in tests must be updated with these new params.
- **Critical insight — denylist required**: The AC and architecture decision 2B explicitly require denylist enforcement on Slack payload at the Slack formatting boundary. The `send_postmortem_notification` method must accept a `DenylistV1` instance and call `apply_denylist(...)` before any output. This is not optional.
- **Critical insight — NotificationEvent as structured log**: `NotificationEvent` is not emitted to Kafka or object storage — it is serialized as a structured log event field. The log entry carries the `NotificationEvent` fields directly. You do NOT need to call `.model_dump()` and pass the result; instead embed the fields in the structlog call directly (mirroring how `DegradedModeEvent` is logged in `send_degraded_mode_event`).
- **Critical insight — postmortem is orthogonal to final_action**: A case can have `final_action=PAGE` AND `postmortem_required=True`. In that case, Stage 7 must call BOTH the PD adapter AND the Slack notification. Similarly, `final_action=OBSERVE` with `postmortem_required=True` → only Slack fires (per architecture). This is by design — the postmortem check block is sequentially AFTER the PD/non-PD block.

### Technical Requirements

- `NotificationEvent` model fields (from FR45 and AC fields):
  ```python
  class NotificationEvent(BaseModel, frozen=True):
      event_type: Literal["NotificationEvent"] = "NotificationEvent"
      case_id: str
      final_action: str
      routing_key: str
      support_channel: str | None
      postmortem_required: bool
      reason_codes: tuple[str, ...]
  ```
- `send_postmortem_notification` signature:
  ```python
  def send_postmortem_notification(
      self,
      *,
      case_id: str,
      final_action: str,
      routing_key: str,
      support_channel: str | None,
      postmortem_required: bool,
      reason_codes: tuple[str, ...],
      denylist: DenylistV1,
  ) -> None:
  ```
- Build notification fields dict before denylist:
  ```python
  raw_fields: dict[str, Any] = {
      "case_id": case_id,
      "final_action": final_action,
      "routing_key": routing_key,
      "support_channel": support_channel,
      "postmortem_required": postmortem_required,
      "reason_codes": list(reason_codes),  # serialize tuple → list for JSON
  }
  sanitized = apply_denylist(raw_fields, denylist)
  ```
- Slack Webhook payload (LIVE mode) — formatted text message:
  ```python
  {
      "text": (
          f":memo: *Postmortem Obligation — SOFT Enforcement*\n"
          f"Case: `{sanitized.get('case_id', '[redacted]')}`\n"
          f"Action: `{sanitized.get('final_action', '[redacted]')}`\n"
          f"Routing: `{sanitized.get('routing_key', '[redacted]')}`\n"
          f"Support Channel: {sanitized.get('support_channel') or 'N/A'}\n"
          f"Reason Codes: {sanitized.get('reason_codes', [])}"
      )
  }
  ```
- Structured log event for LOG/MOCK/LIVE modes (always emitted before HTTP in LIVE):
  ```python
  logger.info(
      "postmortem_notification_dispatch",
      slack_mode=self._mode.value,
      **sanitized,  # all denylist-filtered fields spread in
  )
  ```
- No webhook warning:
  ```python
  logger.warning(
      "postmortem_notification_no_webhook",
      slack_mode=self._mode.value,
  )
  ```
- HTTP error log:
  ```python
  logger.warning(
      "postmortem_notification_send_failed",
      slack_mode=self._mode.value,
      error=str(exc),
  )
  ```
- `urllib.request` with `timeout=5` — same as `_send_live` in `send_degraded_mode_event`.
- Updated `dispatch_action` signature:
  ```python
  def dispatch_action(
      *,
      case_id: str,
      decision: ActionDecisionV1,
      routing_context: TopologyRoutingContext | None,
      pd_client: PagerDutyClient,
      slack_client: SlackClient,
      denylist: DenylistV1,
  ) -> None:
  ```

### Architecture Compliance

- `integrations/slack.py` → may import from `contracts/`, `models/`, `logging/`, `config/`, `denylist/`. Must NOT import from `pipeline/`. No new circular deps.
- `pipeline/stages/dispatch.py` → imports `SlackClient` from `integrations.slack`, `DenylistV1` from `denylist.loader`. These are already safe import paths.
- Denylist enforcement: `apply_denylist(...)` from `denylist/enforcement.py` is the only enforcement function. No per-method reimplementation. [Source: architecture decision 2B; `project-context.md` rule "All outbound boundary shaping must use shared apply_denylist(...)"].
- Slack is a degradable integration (NFR-R1): `SlackUnavailable(DegradableError)` exception class exists in architecture error taxonomy but is not currently wired. For Story 5.8, HTTP failures are caught as bare `Exception` and logged as warnings — same pattern as PagerDuty. Do NOT raise or update HealthRegistry for Slack failures in this story scope.
- `INTEGRATION_MODE_SLACK` is already in `Settings` (line 77). Only `SLACK_WEBHOOK_URL` is missing.
- All integration modes default to `LOG` (non-destructive) — do not change the default.

### Library / Framework Requirements

Verification date: 2026-03-06.

- No new runtime dependencies. All needed: `urllib.request` (stdlib), `json` (stdlib), existing `structlog`, existing `pydantic`.
- Python 3.13 typing: `str | None`, `tuple[str, ...]`, `dict[str, Any]`.
- Pydantic 2.12.5: `frozen=True` on `NotificationEvent`. `Literal["NotificationEvent"]` for `event_type` discriminator field — consistent with `TelemetryDegradedEvent` pattern.
- pytest 9.0.2 + pytest-asyncio 1.3.0: `asyncio_mode=auto`. All new tests are synchronous — no `async def` needed.
- `structlog.testing.capture_logs()` context manager for log assertion in tests — same pattern as `test_pagerduty.py`.
- `unittest.mock.patch` for `urllib.request.urlopen` in LIVE mode tests.
- Patch target for Slack urlopen: `"aiops_triage_pipeline.integrations.slack.urllib.request.urlopen"`.

### File Structure Requirements

- **New files to create:**
  - `tests/unit/integrations/test_slack_notification.py` — unit tests for `send_postmortem_notification` (no test_slack.py exists yet; create fresh file scoped to Story 5.8 method only)

- **Files to modify:**
  - `src/aiops_triage_pipeline/models/events.py` — add `NotificationEvent` model (after `TelemetryDegradedEvent`)
  - `src/aiops_triage_pipeline/integrations/slack.py` — add `send_postmortem_notification(...)` method to `SlackClient`; add imports for `apply_denylist`, `DenylistV1`, `Any`
  - `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` — add `slack_client` and `denylist` params to `dispatch_action()`; add postmortem notification block; add imports
  - `src/aiops_triage_pipeline/config/settings.py` — add `SLACK_WEBHOOK_URL: str | None = None`; update `log_active_config`
  - `tests/unit/pipeline/stages/test_dispatch.py` — extend existing tests to pass `slack_client` and `denylist`; add postmortem notification tests

- **Files to read (do not modify):**
  - `src/aiops_triage_pipeline/integrations/slack.py` — existing `send_degraded_mode_event` pattern
  - `src/aiops_triage_pipeline/denylist/enforcement.py` — `apply_denylist(...)` signature
  - `src/aiops_triage_pipeline/denylist/loader.py` — `DenylistV1` model
  - `src/aiops_triage_pipeline/contracts/action_decision.py` — `ActionDecisionV1.postmortem_required`, `postmortem_mode`, `postmortem_reason_codes`
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py` — `TopologyRoutingContext.support_channel`
  - `tests/unit/integrations/test_pagerduty.py` — reference test pattern (structlog.testing, patch urlopen, helper functions)
  - `tests/unit/pipeline/stages/test_dispatch.py` — existing dispatch tests (must extend, not break)

### Previous Story Intelligence

From Story 5.7 (`5-7-pagerduty-page-trigger-execution.md`):

- `dispatch_action()` signature is currently: `(*, case_id, decision, routing_context, pd_client)`. Story 5.8 adds `slack_client` and `denylist` as keyword-only params. All 9 existing `test_dispatch.py` tests call `dispatch_action(...)` and must be updated to pass these new kwargs. Use a real `SlackClient(mode=SlackIntegrationMode.OFF)` as default in test helpers so no Slack side-effects occur in existing tests.
- Code review remediations from 5.7: M1 (`case_id` as distinct audit field), M2 (log `mode` + `action` fields), M3 (pass logger through rather than re-fetching). Apply the same discipline to Story 5.8 — pass `logger` rather than calling `get_logger()` repeatedly inside the method.
- Full regression was 560 tests (unit + integration) at end of Story 5.7. Story 5.8 adds ~10 new unit tests. Full regression target: all pass, 0 skipped.
- `model_copy(update={...})` is the established pattern for varying frozen model fixtures. Use it in tests for `ActionDecisionV1` variants with `postmortem_required=True/False`.

From Story 5.6 (AG6 postmortem predicate):

- AG6 sets `postmortem_required=True`, `postmortem_mode="SOFT"`, `postmortem_reason_codes=("PM_PEAK_SUSTAINED",)` when all conditions met. Story 5.8 consumes these fields — never re-evaluates the predicate.
- `postmortem_reason_codes` is a `tuple[str, ...]` on the contract model. Serialize as `list(reason_codes)` in the notification payload for JSON compatibility.
- Story 5.8 does NOT change gating logic or `ActionDecisionV1` contract — it only adds notification dispatch.

Epic 5 patterns:

- Each story adds exactly the files listed in its scope. No cross-module refactoring beyond the explicit changes.
- Structured logging naming: `get_logger("integrations.slack")` is already used in `slack.py`. Reuse it for the new method.
- Denylist: `apply_denylist` returns a plain `dict[str, Any]`. The sanitized dict may be missing keys if they were denied — use `.get(key, fallback)` when formatting the Slack message text.

### Git Intelligence Summary

Recent commits (most recent first):

- `a13f023` story 5.7: apply code-review remediations
- `af72d23` story 5.7: implement PagerDuty PAGE trigger execution
- `059b480` story 5.6: apply code-review remediations
- `99cce21` story 5.6: verify AG6 predicate and expand boundary test coverage
- `575ea4e` story 5.5: apply code-review remediations

Actionable patterns:

- Stories 5.5, 5.6, 5.7 all went through code-review remediations in separate commits. Common review findings: missing log fields, inconsistent audit fields, dead code (models not used in serialization path). Write tight, complete tests up front to minimize round-trips.
- Story 5.7 code review caught: `PageTriggerPayload` was dead code because `_send_live` bypassed it. In Story 5.8, ensure the notification fields dict is genuinely constructed from the sanitized dict and the denylist output is actually used (not built and ignored).
- Story 5.7 code review caught: missing `case_id` as distinct param (M1). Story 5.8 has `case_id` as an explicit parameter from the start — do not conflate it with `action_fingerprint`.
- Test file naming: previous stories used `test_pagerduty.py` for the adapter and `test_dispatch.py` for the stage. For Story 5.8, create `test_slack_notification.py` (not `test_slack.py`) to clearly scope it to the new method — a future story may add tests for `send_degraded_mode_event` separately.

### Latest Tech Information

Verification date: 2026-03-06.

- Slack Incoming Webhooks: POST to the configured webhook URL with `Content-Type: application/json`. Body: `{"text": "..."}`. Response: `200 OK` with body `"ok"`. Errors: non-200 status codes with text body.
- `urllib.request.urlopen` with `timeout=5` — established stdlib HTTP pattern in this project. Catch bare `Exception` to handle both `urllib.error.URLError` and `urllib.error.HTTPError` — same pattern as `pagerduty.py:_send_live`.
- Python 3.13: `dict.get(key, default)` for safe access on denylist-sanitized dicts.
- structlog 25.5.0: `structlog.testing.capture_logs()` returns list of dicts. Access log entries by `entry["event"]` for the event name and remaining keys for structured fields. Use `next(e for e in logs if e["event"] == "postmortem_notification_dispatch")` pattern to find specific entries.
- Pydantic 2.12.5: `tuple[str, ...]` fields on frozen models serialize as lists in `.model_dump()` (by default). Do not rely on Pydantic serialization for log output — explicitly cast `list(reason_codes)` in the raw_fields dict.
- Ruff: line length 100, target py313, lint selection `E,F,I,N,W`. `Any` from `typing` required (not `builtins`). Add `from typing import Any` if not already imported in `slack.py`.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- **Denylist rule**: "All outbound boundary shaping must use shared `apply_denylist(...)`. No boundary-specific denylist reimplementations." — `send_postmortem_notification` MUST call `apply_denylist(...)`.
- **Integration safety**: "External integrations must implement `OFF | LOG | MOCK | LIVE` semantics consistently. Default-safe operation remains LOG." — Follow this exactly; `INTEGRATION_MODE_SLACK` already defaults to LOG.
- **Never fail silently on degradable faults**: "Degradable failures must emit health/degraded signals and capped behavior." — Slack HTTP errors must be caught and logged; pipeline must continue.
- **Never leak sensitive data**: `SLACK_WEBHOOK_URL` is a secret — log presence only (`[CONFIGURED]`/`[NOT SET]`), never the raw value.
- **Consistency over novelty**: Reuse `get_logger("integrations.slack")`, reuse `apply_denylist(...)`, follow `send_degraded_mode_event` + `_send_live` structural pattern.
- **Contract-first**: `ActionDecisionV1` is frozen — dispatch reads fields, never mutates. `NotificationEvent` must also be frozen.
- **Python 3.13 typing**: `X | None`, `tuple[str, ...]`, `dict[str, Any]`.
- **Test discipline**: "No placeholder-only coverage for production logic." — Cover all integration modes and the denylist enforcement path explicitly.

### Project Structure Notes

- `tests/unit/integrations/__init__.py` already exists (confirmed by `test_prometheus.py`, `test_kafka.py`, `test_pagerduty.py` present). Create `test_slack_notification.py` alongside them — no `__init__.py` changes needed.
- `tests/unit/pipeline/stages/__init__.py` already exists (confirmed by `test_dispatch.py` present). Only extend `test_dispatch.py`, do not create new stage test files.
- `integrations/slack.py` currently imports: `json`, `urllib.request`, `Enum`, `get_logger`, `DegradedModeEvent`. Story 5.8 adds: `from typing import Any`, `from aiops_triage_pipeline.denylist.enforcement import apply_denylist`, `from aiops_triage_pipeline.denylist.loader import DenylistV1`. Add these imports.
- `dispatch.py` currently imports: `ActionDecisionV1`, `Action`, `PagerDutyClient`, `get_logger`, `TopologyRoutingContext`. Story 5.8 adds: `from aiops_triage_pipeline.integrations.slack import SlackClient`, `from aiops_triage_pipeline.denylist.loader import DenylistV1`. Verify no circular imports (dispatch.py is in `pipeline/stages/`, importing from `integrations/` and `denylist/` is safe per architecture).

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.8: Slack Notification & Structured Log Fallback`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR44, FR45)]
- [Source: `artifact/planning-artifacts/architecture.md` (Notification & Action Execution FR43–FR50; denylist enforcement decision 2B; SlackUnavailable DegradableError taxonomy; dispatch.py source tree; INTEGRATION_MODE_SLACK 5D)]
- [Source: `artifact/project-context.md`]
- [Source: `src/aiops_triage_pipeline/integrations/slack.py` (SlackClient pattern)]
- [Source: `src/aiops_triage_pipeline/denylist/enforcement.py` (apply_denylist signature)]
- [Source: `src/aiops_triage_pipeline/denylist/loader.py` (DenylistV1 model)]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py` (ActionDecisionV1.postmortem_required/mode/reason_codes)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py` (TopologyRoutingContext.support_channel)]
- [Source: `src/aiops_triage_pipeline/config/settings.py` (INTEGRATION_MODE_SLACK, SLACK_WEBHOOK_URL gap)]
- [Source: `src/aiops_triage_pipeline/models/events.py` (DegradedModeEvent, TelemetryDegradedEvent patterns)]
- [Source: `artifact/implementation-artifacts/5-7-pagerduty-page-trigger-execution.md`]
- [Source: `artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md`]
- [Source: `tests/unit/integrations/test_pagerduty.py` (test fixture + structlog pattern)]
- [Source: `tests/unit/pipeline/stages/test_dispatch.py` (existing dispatch tests to extend)]

### Story Completion Status

- Story context generated for Epic 5, Story 5.8.
- Story file: `artifact/implementation-artifacts/5-8-slack-notification-and-structured-log-fallback.md`
- Story status set to: `ready-for-dev`
- Completion note: Ultimate context engine analysis completed — comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
- Core planning artifacts analyzed:
  - `artifact/planning-artifacts/epics.md` (Story 5.8 at line 955)
  - `artifact/planning-artifacts/prd/functional-requirements.md` (FR44, FR45)
  - `artifact/planning-artifacts/architecture.md` (denylist 2B, INTEGRATION_MODE_SLACK 5D, Notification FR43–FR50)
  - `artifact/project-context.md`
  - `src/aiops_triage_pipeline/integrations/slack.py` (SlackClient reference pattern)
  - `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` (current state post-5.7)
  - `src/aiops_triage_pipeline/contracts/action_decision.py` (postmortem fields)
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py` (support_channel field)
  - `src/aiops_triage_pipeline/denylist/enforcement.py` (apply_denylist)
  - `src/aiops_triage_pipeline/config/settings.py` (current settings, SLACK_WEBHOOK_URL gap)
  - `src/aiops_triage_pipeline/models/events.py` (event model patterns)
  - `artifact/implementation-artifacts/5-7-pagerduty-page-trigger-execution.md` (previous story)
  - `artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md` (AG6 context)
  - `tests/unit/integrations/test_pagerduty.py` (test fixture pattern)

### Completion Notes List

- Added `NotificationEvent` frozen Pydantic model to `models/events.py` (event_type discriminator, all 6 AC fields, `reason_codes` as `tuple[str, ...]`).
- Added `SLACK_WEBHOOK_URL: str | None = None` to `Settings` and masked presence logging in `log_active_config`.
- Implemented `send_postmortem_notification(...)` on `SlackClient`: OFF silent-drop, LOG/MOCK/LIVE structured log via `apply_denylist`, LIVE webhook POST with `timeout=5`, all exceptions caught and logged as warnings (NFR-R1 compliant). `reason_codes` serialized as `list` for JSON compatibility.
- Extended `dispatch_action()` with `slack_client: SlackClient` and `denylist: DenylistV1` params; postmortem block is orthogonal to PD block (fires for any `postmortem_required=True` regardless of `final_action`).
- Created 13 unit tests in `test_slack_notification.py` covering all 4 modes, both denylist enforcement paths, reason_codes list serialization, no-webhook warning, and HTTP error swallowing.
- Extended `test_dispatch.py` with 5 postmortem tests + `_dispatch` helper (sentinel pattern for `routing_context=None`); all 9 existing tests preserved and passing.
- Full regression: 578 passed, 0 skipped (18 new tests added vs 560 at Story 5.7 completion).

### File List

- `src/aiops_triage_pipeline/models/events.py` — added `NotificationEvent` model
- `src/aiops_triage_pipeline/config/settings.py` — added `SLACK_WEBHOOK_URL`; updated `log_active_config`
- `src/aiops_triage_pipeline/integrations/slack.py` — added `send_postmortem_notification` method; added imports (`Any`, `apply_denylist`, `DenylistV1`)
- `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` — extended `dispatch_action` signature with `slack_client`, `denylist`; added postmortem dispatch block; added imports
- `tests/unit/integrations/test_slack_notification.py` — new file: 13 unit tests for `send_postmortem_notification`
- `tests/unit/pipeline/stages/test_dispatch.py` — extended: `_dispatch` helper, 5 new postmortem tests, all existing tests updated to use helper

## Change Log

- 2026-03-06: Story 5.8 implemented — Slack postmortem notification and structured log fallback. Added `NotificationEvent` model, `SLACK_WEBHOOK_URL` setting, `send_postmortem_notification` on `SlackClient`, postmortem dispatch block in `dispatch_action`. 18 new unit tests; full regression 578 passed, 0 skipped.
