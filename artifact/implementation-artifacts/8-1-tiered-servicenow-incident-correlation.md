# Story 8.1: Tiered ServiceNow Incident Correlation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want PAGE cases correlated with PagerDuty-created ServiceNow Incidents using a three-tier search strategy,
so that the system reliably finds the correct SN Incident even when the primary correlation field is not populated (FR46).

## Acceptance Criteria

1. **Given** a PAGE action has been executed with a stable `pd_incident_id`
   **When** SN Incident correlation is initiated
   **Then** Tier 1 searches for the Incident using the PD correlation field on the SN Incident record
2. **And** if Tier 1 fails, Tier 2 searches using keyword matching against Incident short_description/description
3. **And** if Tier 2 fails, Tier 3 searches using time-window + routing heuristic (recent Incidents matching routing_key within a configurable time window)
4. **And** the tier that produced the match is recorded in the linkage result
5. **And** the integration respects INTEGRATION_MODE_SN (OFF/LOG/MOCK/LIVE)
6. **And** all SN API calls are logged with: timestamp, request_id, case_id, action, outcome, latency (NFR-S6)
7. **And** SN search uses least-privilege access: READ on incident only (NFR-S6)
8. **And** unit tests verify: Tier 1 match, Tier 1 miss -> Tier 2 match, Tier 2 miss -> Tier 3 match, all tiers miss, each integration mode behavior

## Tasks / Subtasks

- [x] Task 1: Implement tiered SN incident correlation adapter (AC: 1, 2, 3, 4, 7)
  - [x] Implement `ServiceNowClient` in `src/aiops_triage_pipeline/integrations/servicenow.py` with a single public correlation entrypoint (for example: `correlate_incident(...)`)
  - [x] Implement Tier 1 query (PD correlation field exact match) with field name configurable from policy/contract data
  - [x] Implement Tier 2 query (keyword match against incident `short_description` and `description`; include `work_notes` only if configured)
  - [x] Implement Tier 3 query (time window + routing-key heuristic) using contract-configured window
  - [x] Return structured correlation result containing: `matched: bool`, `matched_tier: "tier1"|"tier2"|"tier3"|"none"`, `incident_sys_id: str | None`, and reason metadata
  - [x] Enforce read-only behavior for this story (GET/search-only for incident table; no create/update/delete APIs)

- [x] Task 2: Respect integration modes and logging contract (AC: 5, 6)
  - [x] Reuse existing mode semantics (`OFF|LOG|MOCK|LIVE`) from `src/aiops_triage_pipeline/config/settings.py`
  - [x] `OFF`: return skipped/no-op result with no outbound HTTP calls
  - [x] `LOG`: log intended search actions and return deterministic no-op result with no outbound HTTP calls
  - [x] `MOCK`: use deterministic in-memory/mock fixtures for tier outcomes (no network)
  - [x] `LIVE`: perform real ServiceNow table queries against incident records with bounded timeout
  - [x] Emit structured log events for each tier attempt including: `timestamp`, `request_id`, `case_id`, `action`, `outcome`, `latency_ms`, `tier`

- [x] Task 3: Align policy + contract with correlation requirements (AC: 1, 3, 5)
  - [x] Extend `src/aiops_triage_pipeline/contracts/sn_linkage.py` with explicit, typed correlation configuration fields needed by implementation (for example: incident table, PD correlation field name, tier3 window)
  - [x] Update `config/policies/servicenow-linkage-contract-v1.yaml` to include the new fields and sane defaults
  - [x] Add/adjust `tests/unit/contracts/test_policy_models.py` expectations to validate new SN linkage fields and maintain frozen-model guarantees

- [x] Task 4: Implement and verify unit-test coverage for all tier paths (AC: 8)
  - [x] Create `tests/unit/integrations/test_servicenow.py`
  - [x] Add tests for: Tier 1 hit, Tier 1 miss -> Tier 2 hit, Tier 2 miss -> Tier 3 hit, all tiers miss
  - [x] Add tests for each integration mode behavior (`OFF`, `LOG`, `MOCK`, `LIVE`) with explicit assertions on outbound call count
  - [x] Add tests asserting all tier attempts log required audit fields (`request_id`, `case_id`, `action`, `outcome`, `latency_ms`)
  - [x] Add tests asserting read-only incident access (no POST/PATCH/DELETE/PUT in this story)

- [x] Task 5: Quality gates with zero-skip posture
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Confirm full regression completes with `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `8-1-tiered-servicenow-incident-correlation`
- Story ID: `8.1`
- Epic context: Epic 8 starts ServiceNow postmortem automation. This story only delivers correlation search behavior (Tier 1 -> Tier 2 -> Tier 3) and guardrails for mode handling + audit logging.
- Existing implementation baseline:
  - `src/aiops_triage_pipeline/integrations/servicenow.py` is currently empty (stub)
  - `src/aiops_triage_pipeline/integrations/base.py` is currently empty (stub)
  - `src/aiops_triage_pipeline/contracts/sn_linkage.py` exists but is minimal (`enabled`, `max_correlation_window_days`, `correlation_strategy`, `mi_creation_allowed`)
  - `INTEGRATION_MODE_SN` already exists in settings (`src/aiops_triage_pipeline/config/settings.py`)
  - `PagerDutyClient` already establishes stable `pd_incident_id` behavior through dedup key semantics (`src/aiops_triage_pipeline/integrations/pagerduty.py`)
- Critical scope boundary:
  - Do not implement Problem/PIR create-update in this story (that belongs to Story 8.2)
  - Do not implement retry/state-machine persistence in this story (that belongs to Story 8.3)
  - Keep MI-1 posture intact: never add Major Incident creation logic

### Technical Requirements

1. Correlation entrypoint must accept at least: `case_id`, `pd_incident_id`, `routing_key`, and correlation context needed for Tier 2/3.
2. Tier execution order is strict and short-circuited: Tier 1 then Tier 2 then Tier 3; stop at first match.
3. Correlation result object must include matched tier attribution for downstream metrics/story 8.4.
4. Time-window heuristic for Tier 3 must be configurable via policy/contract data, not hard-coded.
5. All outbound ServiceNow calls in this story are read-only incident searches.
6. Each tier attempt must carry one generated `request_id` across logs for traceability.
7. Errors from ServiceNow search should surface as structured outcomes (for example: `error`, `not_found`) without breaking deterministic action gating already completed in hot path.

### Architecture Compliance

- Keep hot-path determinism intact:
  - Correlation is enrichment behavior and must not alter Stage 6 gating decisions already made.
- Respect package boundaries from architecture:
  - Place correlation adapter in `integrations/servicenow.py`
  - Keep pipeline orchestration logic out of adapter internals
- Preserve shared cross-cutting behavior:
  - Use project logging patterns (`structlog` event fields + correlation context)
  - Keep denylist behavior centralized (`apply_denylist`) for future Story 8.2 text payload operations; do not fork boundary logic
- Preserve MI-1 posture:
  - No automated MI creation endpoints, methods, or tokens

### Library / Framework Requirements

- Use existing pinned stack only (no new dependencies):
  - `pydantic==2.12.5`
  - `structlog==25.5.0`
  - `httpx==0.28.1` is already available if HTTP client abstraction is needed
- Keep integration mode values aligned with `IntegrationMode` enum in `config/settings.py`.
- Use ServiceNow Table API search semantics for incident reads and filtered queries.
- Preserve PagerDuty dedup key semantics as the `pd_incident_id` source for Tier 1 correlation input.

### File Structure Requirements

Files expected to be created/updated:

- `src/aiops_triage_pipeline/integrations/servicenow.py` (primary implementation)
- `src/aiops_triage_pipeline/contracts/sn_linkage.py` (typed correlation config additions)
- `config/policies/servicenow-linkage-contract-v1.yaml` (policy defaults for correlation tiers)
- `tests/unit/integrations/test_servicenow.py` (new test suite)
- `tests/unit/contracts/test_policy_models.py` (update SN linkage policy expectations as needed)

Files to avoid changing in this story:

- `src/aiops_triage_pipeline/integrations/pagerduty.py` (unless strictly required for non-breaking data handoff)
- `src/aiops_triage_pipeline/pipeline/stages/gating.py` (gating behavior is out of scope)
- Any code path that could introduce MI object creation

### Testing Requirements

Minimum required unit coverage:

1. Tier 1 direct match (PD field present) returns `matched_tier="tier1"`.
2. Tier 1 miss + Tier 2 keyword match returns `matched_tier="tier2"`.
3. Tier 1/Tier 2 miss + Tier 3 time-window routing match returns `matched_tier="tier3"`.
4. All tiers miss returns `matched_tier="none"` with explicit not-linked outcome.
5. `OFF` mode: no HTTP calls; deterministic skipped result.
6. `LOG` mode: no HTTP calls; logs planned action.
7. `MOCK` mode: deterministic mocked outcomes per configured fixture.
8. `LIVE` mode: uses read-only incident API search and captures request/latency outcome.
9. Log schema assertions per AC/NFR-S6 fields (`request_id`, `case_id`, `action`, `outcome`, `latency_ms`, tier).

### Latest Tech Information

Research timestamp: 2026-03-08.

- ServiceNow Zurich family is current for this project’s timing, with published Zurich patch stream active through at least Zurich Patch 5 (January 12, 2026). Implementation should target current Zurich API docs and avoid relying on legacy family behavior.
- ServiceNow Table API supports default and versioned URL forms (`/api/now/table/{tableName}` and `/api/now/{api_version}/table/{tableName}`) for incident record reads/searches.
- PagerDuty Events API v2 ingestion endpoint remains `https://events.pagerduty.com/v2/enqueue`.
- PagerDuty dedup behavior relies on `dedup_key` identity semantics; this must stay stable because Story 8.1 Tier 1 depends on PD correlation identity.
- PagerDuty Rulesets/EPA deprecation path is complete (Rulesets and classic Event Rules end-of-life on January 31, 2025), so any event routing assumptions should align with Event Orchestration-era behavior.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Keep deterministic guardrails authoritative; enrichment cannot override gating outcomes.
- Reuse existing patterns and avoid parallel implementations for logging, policy loading, and shared utilities.
- Keep integration defaults non-destructive by mode and preserve explicit configuration behavior.
- Maintain structured logging discipline and never log secrets.
- Any contract/policy changes must include targeted unit tests.

### Project Structure Notes

- `integrations/servicenow.py` is the canonical implementation location for this story.
- `contracts/sn_linkage.py` and `config/policies/servicenow-linkage-contract-v1.yaml` are the correct config schema + defaults pair.
- Unit tests belong under `tests/unit/integrations/` and should avoid external network dependencies.

### References

- [Source: `artifact/planning-artifacts/epics.md` (Epic 8, Story 8.1 ACs)]
- [Source: `artifact/planning-artifacts/architecture.md` (notifications mapping, integrations package boundaries, mode framework, logging constraints)]
- [Source: `artifact/project-context.md` (critical implementation rules and anti-patterns)]
- [Source: `src/aiops_triage_pipeline/integrations/pagerduty.py` (stable PD dedup identity behavior)]
- [Source: `src/aiops_triage_pipeline/config/settings.py` (`INTEGRATION_MODE_SN`, enum mode semantics)]
- [Source: `src/aiops_triage_pipeline/contracts/sn_linkage.py` (current minimal SN linkage contract)]
- [ServiceNow Zurich release notes and patch references: https://www.servicenow.com/docs/bundle/zurich-release-notes/page/release-notes/overview/c_WhatIsNewInThisReleaseFamily.html]
- [PagerDuty Events API endpoint and migration context: https://support.pagerduty.com/main/docs/rulesets-advanced-event-rules-and-generating-events-api-vs-events-api-v2]
- [PagerDuty dedup/event behavior references: https://support.pagerduty.com/main/docs/event-management]

### Story Completion Status

- Story document created: `artifact/implementation-artifacts/8-1-tiered-servicenow-incident-correlation.md`
- Workflow status set for handoff: `ready-for-dev`
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Loaded workflow config: `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`
- Loaded instruction set: `_bmad/bmm/workflows/4-implementation/create-story/instructions.xml`
- Story discovered from sprint backlog order: `8-1-tiered-servicenow-incident-correlation`
- Core context sources analyzed:
  - `artifact/planning-artifacts/epics.md`
  - `artifact/planning-artifacts/architecture.md`
  - `artifact/planning-artifacts/prd/*.md` (SN linkage and phased requirements)
  - `artifact/project-context.md`
- Code baseline analyzed:
  - `src/aiops_triage_pipeline/integrations/servicenow.py` (stub)
  - `src/aiops_triage_pipeline/integrations/base.py` (stub)
  - `src/aiops_triage_pipeline/integrations/pagerduty.py`
  - `src/aiops_triage_pipeline/config/settings.py`
  - `src/aiops_triage_pipeline/contracts/sn_linkage.py`
- Red phase validation: `uv run pytest -q tests/unit/integrations/test_servicenow.py tests/unit/models/test_case_file_labels.py tests/unit/contracts/test_policy_models.py -q` (failed as expected before implementation)
- Quality gates executed:
  - `uv run ruff check`
  - `uv run pytest -q -m "not integration"`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Implemented `ServiceNowClient` tiered incident correlation (`tier1` -> `tier2` -> `tier3`) with short-circuit matching and structured result payload.
- Added integration mode behavior (`OFF|LOG|MOCK|LIVE`) with deterministic no-op handling for non-LIVE modes and bounded timeout reads in LIVE mode.
- Enforced read-only incident access via GET-only ServiceNow Table API requests for this story scope.
- Added structured tier-attempt logging fields required by AC/NFR-S6: `timestamp`, `request_id`, `case_id`, `action`, `outcome`, `latency_ms`, `tier`.
- Extended `ServiceNowLinkageContractV1` and policy defaults with typed correlation configuration (incident table, tier fields, tier3 window, timeout, limits).
- Added unit tests for all tier-path permutations, mode behavior, audit log fields, and read-only request assertions.
- Updated MI-1 posture guard test to validate no automated MI creation/write-path behavior while allowing read-only incident correlation.
- Passed full quality gate with zero skips: `765 passed`.

### File List

- artifact/implementation-artifacts/8-1-tiered-servicenow-incident-correlation.md
- artifact/implementation-artifacts/sprint-status.yaml
- config/policies/servicenow-linkage-contract-v1.yaml
- src/aiops_triage_pipeline/contracts/sn_linkage.py
- src/aiops_triage_pipeline/integrations/servicenow.py
- tests/unit/contracts/test_policy_models.py
- tests/unit/integrations/test_servicenow.py
- tests/unit/models/test_case_file_labels.py

### Change Log

- 2026-03-08: Implemented Story 8.1 tiered ServiceNow incident correlation adapter, expanded SN linkage contract/policy config, added unit coverage, and passed full regression with 0 skipped tests.
