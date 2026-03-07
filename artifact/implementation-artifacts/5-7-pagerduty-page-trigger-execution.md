# Story 5.7: PagerDuty PAGE Trigger Execution

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want PAGE actions to trigger PagerDuty with a stable pd_incident_id,
so that high-severity incidents are routed to on-call responders and can be correlated with downstream ServiceNow records (FR43).

## Acceptance Criteria

1. **Given** the ActionDecision.v1 has `final_action=PAGE`
   **When** the Action Executor (Stage 7 dispatch) processes the decision
   **Then** a PAGE trigger is sent to PagerDuty with a stable `pd_incident_id` derived from the case — implemented as the `dedup_key` (set to `action_fingerprint`), which PD uses to deduplicate and correlate incidents.
2. **And** the PD trigger includes the topology `routing_key` for correct team routing (included in the trigger payload as context).
3. **And** the integration respects the `INTEGRATION_MODE_PD` setting: `OFF` (silent drop), `LOG` (structured log, no HTTP), `MOCK` (log + mock_send_count increment, no HTTP), `LIVE` (log + HTTP POST to PD Events V2).
4. **And** in `LOG` mode, the PD trigger payload is logged as structured JSON without making external calls.
5. **And** in `MOCK` mode, the trigger is simulated with a success response (mock_send_count incremented).
6. **And** PD API calls are logged with: timestamp, `case_id`, `action_fingerprint`, action, mode, outcome, latency (NFR-S6).
7. **And** non-PAGE actions (`TICKET`, `NOTIFY`, `OBSERVE`) do NOT trigger PagerDuty — dispatch stage only calls the PD adapter when `final_action == PAGE`.
8. **And** unit tests verify: trigger payload correctness, `pd_incident_id` (dedup_key) stability = `action_fingerprint`, each integration mode behavior (OFF/LOG/MOCK/LIVE), non-PAGE actions skip PD trigger.

## Tasks / Subtasks

- [x] Task 1: Implement `PagerDutyClient` in `integrations/pagerduty.py` (AC: 1–6)
  - [x] Define `PagerDutyIntegrationMode` enum: `OFF`, `LOG`, `MOCK`, `LIVE` (mirrors `SlackIntegrationMode` pattern in `slack.py`).
  - [x] Define `PageTriggerPayload` (frozen Pydantic model): `routing_key`, `dedup_key`, `event_action: Literal["trigger"]`, `payload` (summary, severity, custom_details).
  - [x] Implement `PagerDutyClient.__init__(mode, api_key, pd_routing_key)` — `api_key` used as `routing_key` for PD Events V2 API; topology `routing_key` goes into trigger `custom_details`.
  - [x] Implement `send_page_trigger(case_id, action_fingerprint, routing_key, summary)` → always emits structured log; HTTP call only in LIVE mode.
  - [x] In LIVE mode: POST to PD Events V2 endpoint (`https://events.pagerduty.com/v2/enqueue`) with `dedup_key=action_fingerprint`; log outcome + latency; catch and log HTTP errors without raising (non-critical path fault should not halt pipeline).
  - [x] Track `mock_send_count` for MOCK mode assertion in tests.

- [x] Task 2: Add `PD_ROUTING_KEY` setting to `config/settings.py` (AC: 3)
  - [x] Add `PD_ROUTING_KEY: str | None = None` to `Settings` (the PD Events V2 integration/service key).
  - [x] Log `PD_ROUTING_KEY` presence (not value — redact as `[CONFIGURED]` or `[NOT SET]`) in `log_active_config`.
  - [x] LIVE mode with `PD_ROUTING_KEY=None` must log a warning and skip HTTP call (safe default).

- [x] Task 3: Implement Stage 7 `dispatch.py` (AC: 1, 7)
  - [x] Define `dispatch_action(decision: ActionDecisionV1, routing_context: TopologyRoutingContext | None, pd_client: PagerDutyClient)` function.
  - [x] If `decision.final_action == Action.PAGE` → call `pd_client.send_page_trigger(...)` using `decision.action_fingerprint` as `dedup_key` and `routing_context.routing_key` (or `"unknown"` if context absent) as team routing metadata.
  - [x] Non-PAGE actions: no PD trigger — log structured entry noting action was dispatched without PD.
  - [x] Log dispatch result with: `case_id`, `final_action`, `action_fingerprint`, `mode`, `outcome`.

- [x] Task 4: Unit tests for `PagerDutyClient` in `tests/unit/integrations/test_pagerduty.py` (AC: 1–6, 8)
  - [x] Test OFF mode: `send_page_trigger` produces no log entries and no HTTP calls.
  - [x] Test LOG mode: structured log entry emitted, no HTTP call, mock_send_count remains 0.
  - [x] Test MOCK mode: structured log entry emitted, mock_send_count incremented, no HTTP call.
  - [x] Test LIVE mode (mocked urllib): HTTP POST sent to correct URL, payload contains `dedup_key=action_fingerprint`, log entry emitted with outcome.
  - [x] Test LIVE mode with `pd_routing_key=None`: warning logged, HTTP call skipped (safe default).
  - [x] Test LIVE mode HTTP error: exception caught, warning logged, does not propagate.
  - [x] Test payload `dedup_key` stability: same `action_fingerprint` → same `dedup_key` across calls.

- [x] Task 5: Unit tests for dispatch stage in `tests/unit/pipeline/stages/test_dispatch.py` (AC: 7, 8)
  - [x] Test: `final_action=PAGE` → `pd_client.send_page_trigger` called with correct args.
  - [x] Test: `final_action=TICKET` → PD adapter not called.
  - [x] Test: `final_action=NOTIFY` → PD adapter not called.
  - [x] Test: `final_action=OBSERVE` → PD adapter not called.
  - [x] Test: `routing_context=None` → dispatch still works; uses `"unknown"` as routing_key fallback.

- [x] Task 6: Run quality gates with zero skips (AC: all)
  - [x] `uv run pytest -q tests/unit/integrations/test_pagerduty.py` — 14 passed
  - [x] `uv run pytest -q tests/unit/pipeline/stages/test_dispatch.py` — 9 passed
  - [x] `uv run ruff check` — All checks passed
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` — 560 passed, 0 skipped

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `5-7-pagerduty-page-trigger-execution`
  - Story ID: `5.7`
- Epic context: Epic 5 covers Deterministic Safety Gating & Action Execution (AG0–AG6 + notification dispatch). This story implements the **action execution side** — Stage 7 of the hot-path pipeline — as opposed to Stories 5.1–5.6 which implemented the gating engine.
- **Critical insight**: `pagerduty.py`, `dispatch.py`, and `integrations/base.py` are ALL empty stubs (1 line each). This story writes all three from scratch. The `test_dispatch.py` test file does not yet exist.
- The PagerDuty adapter must follow the `SlackClient` pattern in `integrations/slack.py` exactly — same OFF/LOG/MOCK/LIVE enum, same structured-first logging approach, same HTTP-only-in-LIVE discipline.
- `action_fingerprint` (from `ActionDecisionV1`) is the stable case identity token → use it as PD `dedup_key`. This directly satisfies the "stable pd_incident_id" AC: PD uses `dedup_key` to correlate/deduplicate incidents.
- `routing_key` in ACs refers to `TopologyRoutingContext.routing_key` — the ownership routing key from Stage 3 topology resolution. It is passed as context metadata in the PD trigger payload (`custom_details`), NOT as the PD service integration key. The PD service key is `PD_ROUTING_KEY` from settings.
- `integrations/base.py` is a stub. Story 5.7 may optionally populate it with a shared base adapter pattern, but the minimum requirement is a working `PagerDutyClient`. Follow the `SlackClient` self-contained pattern for now.

### Technical Requirements

- PD Events V2 API endpoint: `https://events.pagerduty.com/v2/enqueue` (POST)
- PD trigger payload structure:
  ```json
  {
    "routing_key": "<PD_ROUTING_KEY from settings>",
    "dedup_key": "<action_fingerprint>",
    "event_action": "trigger",
    "payload": {
      "summary": "<human-readable description>",
      "severity": "critical",
      "source": "aiops-triage-pipeline",
      "custom_details": {
        "case_id": "<case_id>",
        "topology_routing_key": "<TopologyRoutingContext.routing_key>",
        "action_fingerprint": "<action_fingerprint>"
      }
    }
  }
  ```
- Use `urllib.request` (stdlib) for HTTP — no new dependencies required. Mirror the `slack.py` `_send_live` pattern.
- PD API response: 202 Accepted on success. Log `dedup_key` from response body (`{"status":"success","dedup_key":"..."}`) as `pd_incident_id` for audit traceability (NFR-S6).
- Latency measurement: capture `time.monotonic()` before/after HTTP call; log as `latency_ms`.
- Non-PAGE dispatch: log a structured `action_dispatched` entry with `final_action` and `case_id` for audit completeness even when no external call is made.

### Architecture Compliance

- Stage 7 (`dispatch.py`) is the final stage in the hot-path pipeline:
  `Evidence → Peak → Topology → CaseFile → Outbox → Gating → Dispatch`
- `dispatch.py` imports from `integrations/pagerduty.py` and `contracts/action_decision.py` — no circular dependencies.
- `dispatch.py` may import `pipeline/stages/topology.py`'s `TopologyRoutingContext` for routing metadata.
- All outbound integrations must implement `OFF | LOG | MOCK | LIVE` semantics per architecture decision 5D and `project-context.md` rule: "External integrations must implement OFF | LOG | MOCK | LIVE semantics consistently."
- Default-safe: `INTEGRATION_MODE_PD` defaults to `LOG` in `Settings` (already set). LIVE mode with no `PD_ROUTING_KEY` must degrade gracefully (warning log, no crash).
- Import rules (from architecture): `integrations/` may import from `contracts/`, `models/`, `logging/`, `config/`. `integrations/` must NOT import from `pipeline/` (avoid circular path). `dispatch.py` (in `pipeline/stages/`) is the consumer of `integrations/pagerduty.py`.
- `HealthRegistry` is available via `health/registry.py` — dispatch stage may update it on PD integration health, but this is NOT required for Story 5.7 scope (Story 5.9 E2E integration will validate the full chain).

### Library / Framework Requirements

Verification date: 2026-03-06.

- No new runtime dependencies required. `urllib.request` (stdlib) handles HTTP, mirroring `slack.py`.
- Python 3.13: use `X | None` type hints, built-in generics.
- Pydantic 2.12.5: `PageTriggerPayload` should be `frozen=True`. For test fixture construction, use `model_copy(update={...})` pattern established in Epic 5.
- pytest 9.0.2 + pytest-asyncio 1.3.0: `asyncio_mode=auto`. PagerDutyClient and dispatch tests are synchronous — no `async def` needed.
- `time.monotonic()` for latency measurement — no `datetime` overhead.
- `unittest.mock.patch` for `urllib.request.urlopen` in LIVE mode tests — same pattern as Kafka/Slack unit tests.

### File Structure Requirements

- **New files to create:**
  - `src/aiops_triage_pipeline/integrations/pagerduty.py` — PagerDutyClient (currently 1-line stub)
  - `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` — Stage 7 dispatch (currently 1-line stub)
  - `tests/unit/pipeline/stages/test_dispatch.py` — Stage 7 unit tests (does not exist)
  - `tests/unit/integrations/test_pagerduty.py` — PagerDutyClient unit tests (does not exist)

- **Files to modify:**
  - `src/aiops_triage_pipeline/config/settings.py` — add `PD_ROUTING_KEY: str | None = None`; update `log_active_config` to log its presence.

- **Files to read (do not modify):**
  - `src/aiops_triage_pipeline/contracts/action_decision.py` — `ActionDecisionV1` fields
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py` — `TopologyRoutingContext` fields
  - `src/aiops_triage_pipeline/integrations/slack.py` — reference implementation for OFF/LOG/MOCK/LIVE pattern
  - `src/aiops_triage_pipeline/logging/setup.py` — `get_logger()` usage pattern
  - `tests/unit/integrations/test_kafka.py` — reference for integration unit test style

### Testing Requirements

- `test_pagerduty.py` fixture pattern: construct `PagerDutyClient(mode=..., pd_routing_key="test-key")`.
- Mock `urllib.request.urlopen` using `unittest.mock.patch("aiops_triage_pipeline.integrations.pagerduty.urllib.request.urlopen")` for LIVE mode tests.
- Assert structured log output using `caplog` or structlog test capture — verify key fields: `case_id`, `action_fingerprint`, `mode`, `outcome`.
- `test_dispatch.py` fixture pattern: construct a minimal `ActionDecisionV1` using real fields. For `final_action=PAGE` tests, pass a mock `PagerDutyClient` (or real one in MOCK mode) and assert `mock_send_count == 1` or mock call args.
- All tests must pass zero-skip. No `pytest.skip` calls.
- Test file locations must mirror source: `tests/unit/integrations/test_pagerduty.py` and `tests/unit/pipeline/stages/test_dispatch.py`.
- `__init__.py` in `tests/unit/pipeline/stages/` already exists (other stage tests are present). Verify `tests/unit/integrations/__init__.py` exists before creating `test_pagerduty.py`.

### Previous Story Intelligence

From Story 5.6 (`artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md`):

- AG6 sets `postmortem_required`, `postmortem_mode`, `postmortem_reason_codes` on `ActionDecisionV1`. Story 5.7 does NOT act on postmortem fields — that is Story 5.8's scope. Only `final_action` matters for dispatch routing here.
- Code review found: add defensive checks and explicit scope comments — apply same discipline to dispatch and PD adapter.
- Full regression suite was 538 tests at end of Story 5.6. New tests for Story 5.7 will expand this baseline.
- `model_copy(update={...})` is the established fixture variation pattern for frozen models.

From Story 5.5 (AG5 — Redis dedupe):

- `action_fingerprint` is the stable identity key used for Redis dedupe TTL keying. It is also the `dedup_key` for PD — this is architecturally intentional: the same fingerprint that prevents repeat PD pages (AG5) also ties the PD incident to the case identity.
- DegradedModeEvent / SlackClient for degraded-mode notifications is the sibling integration pattern — follow it precisely.
- Keep change set minimal. Story 5.7 is bounded: `pagerduty.py`, `dispatch.py`, two test files, one settings field.

Epic 5 implementation pattern:

- Each story adds exactly the files listed in its scope — no cross-module refactoring.
- Structured logging uses `get_logger("integrations.pagerduty")` and `get_logger("pipeline.stages.dispatch")` naming convention.
- Integration test coverage for LIVE mode (real PD API) is NOT in scope for Story 5.7 — unit tests with mocked HTTP cover the behavior. E2E pipeline test (Story 5.9) will validate full hot-path.

### Git Intelligence Summary

Recent commits (most recent first):

- `059b480` story 5.6: apply code-review remediations
- `99cce21` story 5.6: verify AG6 predicate and expand boundary test coverage
- `575ea4e` story 5.5: apply code-review remediations
- `8934e61` story 5.5: implement AG5 action deduplication and Redis degraded mode
- `fa284b6` chore(story): create story 5.5 context

Actionable patterns for Story 5.7:

- Stories 5.5 and 5.6 both went through code-review remediations in separate commits — expect the same for 5.7. Write tight, complete tests up front to minimize remediation round-trips.
- Story 5.5 touched `integrations/slack.py` as part of AG5 DegradedModeEvent dispatch. That file is now stable — use it as the reference, do not modify it.
- Story 5.6 was narrow (gating.py + test_gating.py only). Story 5.7 is broader: new integration adapter + new pipeline stage + two new test files + settings change. Budget accordingly.
- Reviewer will scrutinize: LIVE mode with missing `PD_ROUTING_KEY` (must not crash), HTTP error handling (must not propagate), non-PAGE action no-op (must not call PD), `dedup_key` = `action_fingerprint` (traceability invariant).

### Latest Tech Information

Verification date: 2026-03-06.

- PagerDuty Events API V2: POST `https://events.pagerduty.com/v2/enqueue`. Request body: JSON with `routing_key`, `dedup_key`, `event_action`, `payload`. Response 202: `{"status":"success","message":"Event processed","dedup_key":"<key>"}`. Response 400+: error body with `message` field.
- `dedup_key` in PD Events V2 is the idempotency key — if a trigger with the same `dedup_key` is sent while an incident is open, PD adds an alert to the existing incident rather than creating a new one. This is the mechanism for "stable pd_incident_id".
- `urllib.request.urlopen` with `timeout=5` (seconds) is the established stdlib HTTP pattern in this project (see `slack.py:111`). Use the same timeout.
- Python 3.13: `time.monotonic()` returns a float in seconds; multiply by 1000 for ms: `latency_ms = round((end - start) * 1000, 2)`.
- No new pip packages required — this is purely stdlib + existing project libraries.
- Ruff lint target `py313`, line length 100. `N818` is ignored (intentional). Imports: `E,F,I,N,W` selection.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- External integrations must implement `OFF | LOG | MOCK | LIVE` semantics consistently — PagerDutyClient must mirror this exactly.
- Default-safe operation remains LOG unless explicitly configured — `INTEGRATION_MODE_PD` defaults to LOG (already in Settings).
- Never weaken integration safety posture: prevent unintended LIVE calls in local/dev execution paths. LIVE mode with `PD_ROUTING_KEY=None` must log warning and skip HTTP.
- Never leak sensitive data: `PD_ROUTING_KEY` is a secret — log presence only (`[CONFIGURED]`/`[NOT SET]`), never the value.
- Never fail silently on critical-path faults: HTTP errors in LIVE mode should be caught, logged as warnings, and not propagate (PD is degradable, not critical-halt).
- Consistency over novelty: reuse `get_logger()` from `logging/setup.py`, follow `slack.py` structure, do not introduce parallel logging patterns.
- Contract-first: `ActionDecisionV1` and `TopologyRoutingContext` are frozen models — do not mutate them in dispatch logic.
- Use Python 3.13 typing: `X | None`, built-in generics like `dict[str, Any]`.

### Project Structure Notes

- `tests/unit/integrations/__init__.py` already exists (confirmed by glob: test_prometheus.py, test_kafka.py are present). Create `test_pagerduty.py` alongside them.
- `tests/unit/pipeline/stages/` already has `test_gating.py` and others — `test_dispatch.py` can be created directly alongside.
- No frontend or UX artifacts required.
- Confirm `tests/unit/pipeline/stages/__init__.py` exists before creating `test_dispatch.py` (it almost certainly does given other stage tests exist, but verify).
- The `integrations/` source package has: `prometheus.py`, `kafka.py`, `pagerduty.py` (stub), `slack.py`. New `pagerduty.py` implementation slots in naturally.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.7: PagerDuty PAGE Trigger Execution`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR43)]
- [Source: `artifact/planning-artifacts/architecture.md` (Notification & Action Execution, FR43–FR50; Infrastructure 5D; Source tree dispatch.py, pagerduty.py)]
- [Source: `artifact/project-context.md`]
- [Source: `src/aiops_triage_pipeline/integrations/slack.py` (OFF/LOG/MOCK/LIVE reference pattern)]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py` (ActionDecisionV1 fields)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py` (TopologyRoutingContext.routing_key)]
- [Source: `src/aiops_triage_pipeline/config/settings.py` (INTEGRATION_MODE_PD, IntegrationMode enum)]
- [Source: `artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md`]
- [Source: `artifact/implementation-artifacts/5-5-action-deduplication-and-redis-degraded-mode-ag5.md`]

### Story Completion Status

- Story context generated for Epic 5 Story 5.7.
- Story file: `artifact/implementation-artifacts/5-7-pagerduty-page-trigger-execution.md`.
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
  - `src/aiops_triage_pipeline/integrations/slack.py` (reference pattern)
  - `src/aiops_triage_pipeline/integrations/pagerduty.py` (stub — new implementation)
  - `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` (stub — new implementation)
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py` (TopologyRoutingContext)
  - `src/aiops_triage_pipeline/contracts/action_decision.py`
  - `src/aiops_triage_pipeline/config/settings.py`
  - `artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md`

### Completion Notes List

- Implemented `PagerDutyClient` in `integrations/pagerduty.py` following the `SlackClient` OFF/LOG/MOCK/LIVE pattern exactly. `dedup_key` is always set to `action_fingerprint` (stable pd_incident_id per FR43). LIVE mode uses `urllib.request` with 5s timeout, logs latency_ms, catches all HTTP errors without propagating.
- Added `PD_ROUTING_KEY: str | None = None` to `Settings` and updated `log_active_config` to emit `[CONFIGURED]`/`[NOT SET]` (never the raw secret).
- Implemented Stage 7 `dispatch.py`: `dispatch_action()` routes PAGE to `pd_client.send_page_trigger()` and logs an `action_dispatched` audit entry for all actions. Non-PAGE actions produce no PD trigger. `routing_context=None` safely falls back to `"unknown"` routing key.
- 14 unit tests for `PagerDutyClient` (all modes, HTTP error handling, dedup_key stability), 9 unit tests for dispatch stage (all Action variants, None routing context, real MOCK mode client).
- Full regression: 560 passed, 0 skipped. Lint: all checks passed.

### File List

- `src/aiops_triage_pipeline/integrations/pagerduty.py` (new — PagerDutyClient implementation)
- `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` (new — Stage 7 dispatch)
- `src/aiops_triage_pipeline/config/settings.py` (modified — added PD_ROUTING_KEY field and log_active_config entry)
- `tests/unit/integrations/test_pagerduty.py` (new — 14 unit tests for PagerDutyClient)
- `tests/unit/pipeline/stages/test_dispatch.py` (new — 9 unit tests for dispatch stage)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified — status: in-progress → review)
- `artifact/implementation-artifacts/5-7-pagerduty-page-trigger-execution.md` (modified — story file updates)
