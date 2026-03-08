# Story 8.2: Idempotent Problem & PIR Task Upsert

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want SN Problem and PIR tasks created or updated idempotently for correlated Incidents,
so that postmortem tracking is automated without creating duplicate records on retry (FR47).

## Acceptance Criteria

1. **Given** an SN Incident has been correlated via tiered search
   **When** Problem and PIR task creation is triggered
   **Then** a Problem record is created or updated using `external_id` keying with no duplicates on retry (FR47)
2. **And** PIR task(s) are created or updated under the Problem using `external_id` keying with no duplicates on retry
3. **And** Problem and PIR descriptions enforce the exposure denylist (no sensitive sink endpoints, credentials, or restricted hostnames) (NFR-S5)
4. **And** SN integration uses least-privilege access: CRUD on problem/task only, no broad admin roles
5. **And** all SN API calls (create, update) are logged with: timestamp, request_id, case_id, sys_ids touched, action, outcome, latency (NFR-S6)
6. **And** linkage results are written to `cases/{case_id}/linkage.json` as a write-once stage file
7. **And** unit tests verify: idempotent create (first call creates, second call updates same record), denylist enforcement on descriptions, linkage.json write with hash chain

## Tasks / Subtasks

- [x] Task 1: Implement idempotent SN Problem and PIR upsert operations in ServiceNow adapter (AC: 1, 2, 4, 5)
  - [x] Extend `src/aiops_triage_pipeline/integrations/servicenow.py` with explicit write-path methods for Problem and PIR task upsert (separate from 8.1 incident correlation path)
  - [x] Define deterministic `external_id` generation rules for Problem and PIR task records from stable case identifiers (for example: `case_id`, `pd_incident_id`, and task type)
  - [x] Implement upsert logic as: lookup by `external_id` -> create if absent -> update same record if present
  - [x] Keep all calls bounded by configured timeout and max-result limits from contract/policy model
  - [x] Ensure incident table remains read-only in this story; write scope limited to Problem and PIR task tables only

- [x] Task 2: Enforce denylist and MI-1 safety on all SN payloads (AC: 3, 4)
  - [x] Apply shared `apply_denylist(...)` before constructing Problem and PIR description/body fields
  - [x] Add hard guardrails so no code path can create Major Incident records (FR67b / MI-1 posture)
  - [x] Ensure Problem/PIR payload composition uses only required operational context and excludes secrets/sensitive values
  - [x] Preserve least-privilege assumptions in adapter behavior and config expectations

- [x] Task 3: Persist linkage stage output with write-once semantics and useful linkage metadata (AC: 6, 7)
  - [x] Extend `CaseFileLinkageV1` in `src/aiops_triage_pipeline/models/case_file.py` with SN linkage fields needed by FR47 flows (for example incident/problem/task sys_ids and external_id references), while preserving hash-chain invariants
  - [x] Update serialization/hash utilities in `src/aiops_triage_pipeline/storage/casefile_io.py` and stage persistence checks in `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
  - [x] Ensure linkage stage persists through existing create-only write path (`persist_casefile_linkage_stage`) and remains idempotent for retry of identical payload
  - [x] Keep backward compatibility behavior explicit for previously written linkage payloads used in existing tests

- [x] Task 4: Add orchestration surface for 8.2 without breaking hot-path determinism (AC: 1, 2, 6)
  - [x] Introduce/extend a linkage orchestration function (cold-path/add-on scope) that consumes 8.1 correlation output and executes Problem/PIR upsert
  - [x] Ensure failures return structured linkage outcomes without impacting deterministic gating/action decisions already completed in hot path
  - [x] Ensure `INTEGRATION_MODE_SN` semantics remain consistent with existing OFF/LOG/MOCK/LIVE mode behavior

- [x] Task 5: Add and update tests for idempotent upsert, denylist enforcement, and linkage persistence (AC: 7)
  - [x] Extend `tests/unit/integrations/test_servicenow.py` with create/update idempotency scenarios for Problem and PIR tasks
  - [x] Add denylist-focused tests proving sensitive fields are redacted/excluded before SN write payload submission
  - [x] Update `tests/unit/pipeline/stages/test_casefile.py` and `tests/unit/storage/test_casefile_io.py` for enriched linkage payload and hash stability
  - [x] Update contract/policy tests in `tests/unit/contracts/test_policy_models.py` for any new SN linkage settings required by 8.2
  - [x] Keep or extend MI-1 posture tests in `tests/unit/models/test_case_file_labels.py` to prove no automated MI creation path is introduced

- [x] Task 6: Run quality gates with zero-skip posture
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Confirm full regression completes with `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `8-2-idempotent-problem-and-pir-task-upsert`
- Story ID: `8.2`
- Epic context: Epic 8 implements ServiceNow postmortem automation in sequence:
  - 8.1 completed tiered incident correlation (read-only incident search)
  - 8.2 adds idempotent Problem and PIR write path
  - 8.3 adds retry/state machine
  - 8.4 adds fallback-rate metrics
- Current baseline from code:
  - `ServiceNowClient.correlate_incident(...)` exists in `src/aiops_triage_pipeline/integrations/servicenow.py`
  - Correlation is GET-only and currently scoped to incident search
  - `CaseFileLinkageV1` currently carries only `linkage_status` and `linkage_reason` plus hash fields
  - Linkage stage persistence functions already exist and enforce write-once/hash-chain behavior
  - `INTEGRATION_MODE_SN` is already available in `config/settings.py` with default `LOG`
- Critical scope boundary:
  - Do not implement retry state machine in this story (belongs to 8.3)
  - Do not implement fallback-rate metrics in this story (belongs to 8.4)
  - Do not change deterministic gate/action authority; SN linkage is enrichment workflow

### Technical Requirements

1. Problem and PIR task upsert must be idempotent by deterministic `external_id` keys.
2. Repeat execution with same case input must update existing SN records, not create duplicates.
3. All write payload fields routed to SN must pass through shared `apply_denylist(...)`.
4. Structured logs for SN writes must include `timestamp`, `request_id`, `case_id`, `sys_ids touched`, `action`, `outcome`, and `latency`.
5. `INTEGRATION_MODE_SN` OFF/LOG/MOCK/LIVE behavior must remain deterministic and safe by default.
6. Linkage stage output must be persisted to `cases/{case_id}/linkage.json` with write-once semantics and valid hash chain.
7. Any required linkage schema expansion must preserve canonical hash computation and stage validation behavior.
8. Incident correlation behavior from story 8.1 must remain intact and non-regressing.
9. MI-1 posture must remain hard-enforced: no automated Major Incident create/update path.
10. Hot-path completion cannot depend on SN write success/failure.

### Architecture Compliance

- Keep package boundaries:
  - Adapter logic in `integrations/servicenow.py`
  - CaseFile payload changes in `models/case_file.py`
  - Serialization and write-once semantics in `storage/casefile_io.py` and `pipeline/stages/casefile.py`
- Reuse existing cross-cutting services:
  - Shared denylist enforcement function
  - Existing structured logger conventions
  - Existing integration mode configuration via settings
- Preserve append-only CaseFile stage model:
  - `linkage.json` as independent stage file
  - Hash-chain dependency on `triage.json` (and optional `diagnosis.json` when present)
- Preserve safety architecture:
  - Deterministic gates remain action authority
  - ServiceNow automation is additive and non-authoritative

### Library / Framework Requirements

- Use current pinned stack in repository (no dependency churn for this story):
  - Python 3.13
  - pydantic 2.12.5
  - structlog 25.5.0
  - pydantic-settings ~2.13.1
- Continue using stdlib HTTP approach in current SN adapter unless strong reason exists to refactor.
- Keep ServiceNow integration mode and config semantics aligned with `IntegrationMode` in `config/settings.py`.
- Preserve PagerDuty dedup identity assumptions from story 8.1 because upstream correlation identity remains input to 8.2.

### File Structure Requirements

Files expected to be created/updated:

- `src/aiops_triage_pipeline/integrations/servicenow.py` (add Problem/PIR upsert path)
- `src/aiops_triage_pipeline/models/case_file.py` (enrich linkage payload model if needed)
- `src/aiops_triage_pipeline/storage/casefile_io.py` (hash/validation updates for linkage schema changes)
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` (stage validation/persistence wiring if needed)
- `config/policies/servicenow-linkage-contract-v1.yaml` (if new typed knobs are needed)
- `src/aiops_triage_pipeline/contracts/sn_linkage.py` (if policy contract shape changes)
- `tests/unit/integrations/test_servicenow.py`
- `tests/unit/storage/test_casefile_io.py`
- `tests/unit/pipeline/stages/test_casefile.py`
- `tests/unit/contracts/test_policy_models.py`
- `tests/unit/models/test_case_file_labels.py` (MI-1 guardrail coverage)

Files to avoid changing in this story:

- `src/aiops_triage_pipeline/pipeline/stages/gating.py` (out of scope)
- `src/aiops_triage_pipeline/integrations/pagerduty.py` (unless non-breaking handoff adjustment is strictly required)
- Any unrelated epic/story implementation artifacts

### Testing Requirements

Minimum required unit coverage:

1. Problem upsert create path: no existing `external_id` -> create and return created sys_id.
2. Problem upsert update path: existing `external_id` -> update same record and return same sys_id.
3. PIR task upsert create/update path with idempotent `external_id`.
4. Denylist enforcement on Problem and PIR descriptions (sensitive keys/values removed).
5. Structured logging assertions include required NFR-S6 fields plus touched sys_ids.
6. OFF/LOG/MOCK modes do not issue destructive network calls.
7. LIVE mode issues expected table API methods/paths for Problem/PIR only.
8. Linkage stage persistence validates enriched payload hash and dependency hashes.
9. Existing 8.1 correlation tests continue passing (no regression in tiered search behavior).
10. MI-1 posture tests continue passing (no code path for Major Incident creation).

Integration expectations:

- Any integration test added for linkage writes must remain deterministic and avoid external SN dependency by mock/stubbed boundaries.
- Full suite quality gate must run with Docker-enabled command and end with 0 skips.

### Previous Story Intelligence

Learnings extracted from Story 8.1 implementation and review closure:

- Keep SN query/write fields minimal (`sysparm_fields` constrained to required fields only).
- Preserve deterministic selection behavior whenever multiple SN records are returned (stable ranking/selection logic).
- Validate required identifiers at API boundary and fail fast with structured outcomes before outbound calls.
- Keep correlation strategy driven by typed policy contract values, not hard-coded tier flow.
- Preserve strict read/write scope boundaries in adapter methods to avoid accidental behavior bleed.
- Keep evidence-safe behavior explicit in tests, not implied in comments.

### Git Intelligence Summary

Recent commit analysis relevant to this story:

- `d87532d` fixed 8.1 review findings in `integrations/servicenow.py`, `contracts/sn_linkage.py`, and tests.
- `a0ac885` introduced 8.1 tiered correlation and initial SN linkage contract/policy expansion.
- `bb9a1d5` created 8.1 story context and moved sprint status to ready-for-dev.

Actionable implications for 8.2:

- Continue iterating in the same files touched by 8.1 to preserve continuity and reduce integration risk.
- Treat the existing 8.1 tests as non-regression contract tests while adding 8.2 upsert coverage.
- Keep contract-first approach: if runtime behavior changes, update contract/policy model and tests together.

### Latest Tech Information

Research timestamp: 2026-03-08.

- ServiceNow Table API (Zurich docs) explicitly supports:
  - `GET /now/table/{tableName}` for list queries
  - `POST /now/table/{tableName}` for create
  - `PATCH /now/table/{tableName}/{sys_id}` for update
  - Query controls including `sysparm_query`, `sysparm_fields`, and `sysparm_limit`
  - Input behavior control via `sysparm_input_display_value` for create/update calls
- ServiceNow Table API access is ACL/role-governed, so least-privilege role scoping remains mandatory for write path design.
- PagerDuty Events API v2 endpoint remains `https://events.pagerduty.com/v2/enqueue`, and dedup identity semantics remain anchored on `dedup_key`.

Implementation takeaway:

- 8.2 should keep deterministic external_id identity and predictable upsert semantics while using explicit create/update Table API paths.
- Keep payload fields intentionally minimal and denylist-filtered before outbound submission.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Reuse shared denylist enforcement function, do not fork per boundary.
- Preserve deterministic guardrail authority (SN linkage cannot override gate decisions).
- Keep default integration safety posture non-destructive (`LOG` by default).
- Maintain structured, machine-parseable logging and never log secrets.
- Add targeted tests for contract/config/schema behavior changes in the same change.

### Project Structure Notes

- Existing implementation already anchors SN integration at `src/aiops_triage_pipeline/integrations/servicenow.py`; 8.2 should extend this module instead of creating parallel adapters.
- Linkage stage write/hashing logic exists and should be reused (`pipeline/stages/casefile.py`, `storage/casefile_io.py`).
- If linkage schema expands, model and storage tests must evolve together to keep hash determinism and deserialization stable.

### References

- [Source: `artifact/planning-artifacts/epics.md` (Epic 8, Story 8.2 ACs)]
- [Source: `artifact/planning-artifacts/architecture.md` (integration boundaries, denylist, structure, testing patterns)]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR47, FR67)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-S5, NFR-S6)]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` (MI-1 posture, least privilege, denylist governance)]
- [Source: `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md` (linkage stage lifecycle)]
- [Source: `artifact/project-context.md` (stack, guardrails, testing and safety rules)]
- [Source: `artifact/implementation-artifacts/8-1-tiered-servicenow-incident-correlation.md` (previous-story learnings and follow-ups)]
- [ServiceNow Table API docs: https://www.servicenow.com/docs/bundle/zurich-api-reference/page/integrate/inbound-rest/concept/c_TableAPI.html]
- [PagerDuty Events API v2 endpoint migration note: https://support.pagerduty.com/main/docs/service-integration-guide-events-api-v2]

### Story Completion Status

- Story document created: `artifact/implementation-artifacts/8-2-idempotent-problem-and-pir-task-upsert.md`
- Workflow status set for handoff: `review`
- Completion note: Implementation complete, quality gates passing, ready for code review.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Loaded workflow config: `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`
- Loaded instructions: `_bmad/bmm/workflows/4-implementation/dev-story/instructions.xml`
- Story discovered from sprint backlog order and marked in-progress: `8-2-idempotent-problem-and-pir-task-upsert`
- Implemented Task 1-5 code paths and test updates across ServiceNow adapter, SN contract, casefile model/storage, and unit tests.
- Quality gate runs executed:
  - `uv run ruff check` (pass)
  - `uv run pytest -q tests/unit/integrations/test_servicenow.py tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py tests/unit/contracts/test_policy_models.py tests/unit/models/test_case_file_labels.py` (130 passed)
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix:///home/sas/.docker/desktop/docker.sock uv run pytest -q -m "not integration" -rs` (767 passed, 19 deselected, 0 skipped)
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix:///home/sas/.docker/desktop/docker.sock uv run pytest -q -rs` (786 passed, 0 skipped)
- Prerequisite diagnostics:
  - `DOCKER_HOST=unix:///home/sas/.docker/desktop/docker.sock docker info --format '{{json .ServerVersion}}'` returned `"29.2.0"`.
  - `http://localhost:9090/-/ready` returned `200`.

### Completion Notes List

- Added idempotent ServiceNow write path for Problem and PIR task records with deterministic `external_id` generation and lookup->create/update behavior.
- Added structured write logging fields required by NFR-S6 (`timestamp`, `request_id`, `case_id`, `sys_ids_touched`, `action`, `outcome`, `latency_ms`).
- Added denylist enforcement on write payload composition and explicit MI-1 guardrails in adapter and contract validation.
- Added cold-path orchestration method returning structured linkage outcomes without raising.
- Added linkage orchestration stage surface that performs ServiceNow upsert and persists `linkage.json` write-once in one flow.
- Expanded `CaseFileLinkageV1` schema and linkage persistence metadata for ServiceNow linkage identifiers while preserving hash-chain semantics and legacy payload compatibility.
- Fixed PIR task payload description to record `problem_sys_id` (not incident sys_id), preserving accurate linkage audit context.
- Added duplicate `external_id` guardrail: multiple existing records now fail fast as lookup errors instead of silently updating an arbitrary record.
- Added input guardrail for empty PIR task sets to avoid false `linked` outcomes without PIR task upsert.
- Updated and extended unit tests across integration, storage, pipeline stage, contract, and MI-1 posture coverage.
- Completed full regression with zero skipped tests after environment prerequisites recovered.

### File List

- artifact/implementation-artifacts/8-2-idempotent-problem-and-pir-task-upsert.md
- artifact/implementation-artifacts/sprint-status.yaml
- config/policies/servicenow-linkage-contract-v1.yaml
- src/aiops_triage_pipeline/contracts/sn_linkage.py
- src/aiops_triage_pipeline/integrations/servicenow.py
- src/aiops_triage_pipeline/models/case_file.py
- src/aiops_triage_pipeline/pipeline/stages/__init__.py
- src/aiops_triage_pipeline/pipeline/stages/linkage.py
- src/aiops_triage_pipeline/storage/casefile_io.py
- tests/unit/contracts/test_policy_models.py
- tests/unit/integrations/test_servicenow.py
- tests/unit/models/test_case_file_labels.py
- tests/unit/pipeline/stages/test_casefile.py
- tests/unit/pipeline/stages/test_linkage.py
- tests/unit/storage/test_casefile_io.py

### Change Log

- 2026-03-08: Implemented Story 8.2 code and tests for idempotent ServiceNow Problem/PIR upsert, denylist + MI-1 guardrails, and enriched linkage stage payload persistence. Story remains `in-progress` due unresolved local prerequisite failures causing skipped tests in full regression.
- 2026-03-08: Re-ran quality gates after environment recovery; full regression completed with zero skipped tests and story moved to `review`.
- 2026-03-08: Addressed code-review findings by wiring ServiceNow upsert -> linkage.json persistence orchestration, fixing PIR description identifier mapping, adding duplicate external_id detection, and rejecting empty PIR task sets; story moved to `done`.
