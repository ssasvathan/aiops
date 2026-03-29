---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-03-22'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/2-4-dispatch-pagerduty-and-slack-actions-with-denylist-safety.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/pipeline/stages/dispatch.py
  - src/aiops_triage_pipeline/integrations/slack.py
  - src/aiops_triage_pipeline/integrations/pagerduty.py
  - tests/unit/pipeline/stages/test_dispatch.py
  - tests/unit/integrations/test_slack_notification.py
  - tests/unit/integrations/test_pagerduty.py
  - _bmad/tea/config.yaml
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/data-factories.md
---

# ATDD Checklist - Epic 2, Story 2.4: Dispatch PagerDuty and Slack Actions with Denylist Safety

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Backend acceptance/unit (pytest)
**TDD Phase:** RED

## Story Summary

Story 2.4 closes dispatch safety gaps in Stage 7 by adding explicit NOTIFY->Slack dispatch,
consistent denylist enforcement on both Slack and PagerDuty boundaries, and deterministic fallback
logging when Slack is unavailable.

**As an** on-call engineer  
**I want** outbound action dispatch to be reliable and safe  
**So that** external notifications are delivered without leaking denied content

## Acceptance Criteria

1. Given an action decision requires PAGE or NOTIFY, when dispatch executes, then PagerDuty and
   Slack payloads are generated from decision context and denylist filtering is applied before
   outbound send.
2. Given Slack delivery fails/unavailable, when NOTIFY/degraded/postmortem message is attempted,
   then equivalent structured fallback is emitted and pipeline continues.

## Stack Detection / Mode

- `detected_stack`: backend
- `tea_execution_mode`: auto -> sequential (backend adaptation)
- Generation mode: AI generation only (no browser recording)

## Test Strategy

- P0 acceptance tests target missing NOTIFY dispatch path and denylist boundary enforcement.
- P1 acceptance test targets missing dedicated Slack notify API for regular NOTIFY actions.
- No browser E2E tests: backend service with no UI surface.

## Failing Tests Created (RED Phase)

### Backend Acceptance Tests (3)

**File:** `tests/atdd/test_story_2_4_dispatch_pagerduty_and_slack_red_phase.py`

- `test_p0_notify_action_dispatches_regular_slack_notification_with_denylist`
  - **Status:** RED
  - **Failure:** `dispatch_action` does not invoke regular Slack NOTIFY path.
- `test_p0_pagerduty_live_payload_is_denylist_sanitized_before_outbound_send`
  - **Status:** RED
  - **Failure:** PagerDuty payload still contains denylisted secret values.
- `test_p1_slack_client_exposes_regular_notify_api`
  - **Status:** RED
  - **Failure:** `SlackClient` has no dedicated regular NOTIFY API (`send_notification`).

## Fixtures Created

- `tests/atdd/fixtures/story_2_4_test_data.py`
  - `build_dispatch_decision(...)`
  - `build_routing_context()`
  - `build_strict_denylist()`

## Mock Requirements

- PagerDuty HTTP send is intercepted in-test via patch on
  `aiops_triage_pipeline.integrations.pagerduty.urllib.request.urlopen`.
- Slack regular-notify path currently does not exist; tests model expected API contract.

## Implementation Checklist

### Test: `test_p0_notify_action_dispatches_regular_slack_notification_with_denylist`

- [ ] Add explicit NOTIFY dispatch branch in `dispatch_action`.
- [ ] Add regular Slack notify method invocation from Stage 7.
- [ ] Pass denylist + routing/support channel + fingerprint context.

### Test: `test_p0_pagerduty_live_payload_is_denylist_sanitized_before_outbound_send`

- [ ] Introduce denylist sanitization in PagerDuty payload shaping.
- [ ] Ensure `dedup_key == action_fingerprint` remains unchanged.
- [ ] Ensure redaction occurs before logging and HTTP POST payload write.

### Test: `test_p1_slack_client_exposes_regular_notify_api`

- [ ] Add dedicated non-postmortem NOTIFY API to `SlackClient`.
- [ ] Maintain OFF|LOG|MOCK|LIVE semantics.
- [ ] Add fallback structured warning logs for missing webhook / send failure.

## Running Tests

```bash
# Story 2.4 ATDD red-phase verification
uv run pytest -q tests/atdd/test_story_2_4_dispatch_pagerduty_and_slack_red_phase.py
```

## Test Execution Evidence

**Command:** `uv run pytest -q tests/atdd/test_story_2_4_dispatch_pagerduty_and_slack_red_phase.py`

**Result:**

```text
FFF
3 failed in 0.55s
```

**Failure indicators:**

- NOTIFY route assertion failed (`notify_calls == []`)
- PagerDuty payload still contains `"secret"`
- `hasattr(SlackClient, "send_notification") == False`

## Generated Artifacts

- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-22T20-40-57Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-22T20-40-57Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-22T20-40-57Z.json`
- `artifact/test-artifacts/atdd-checklist-2-4-dispatch-pagerduty-and-slack-actions-with-denylist-safety.md`

## Validation Notes

- Prerequisites satisfied: story has clear ACs; backend pytest framework exists.
- Temp artifacts were written under `artifact/test-artifacts/` (not random temp paths).
- No CLI browser sessions used; no cleanup required.

## Completion Summary

ATDD red phase is complete for Story 2.4 with 3 deterministic failing acceptance tests that capture
all key implementation gaps for NOTIFY dispatch, denylist-safe PagerDuty payloads, and Slack
NOTIFY API surface.
