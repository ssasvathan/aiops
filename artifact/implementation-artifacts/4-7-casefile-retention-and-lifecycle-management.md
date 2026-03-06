# Story 4.7: CaseFile Retention & Lifecycle Management

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a compliance officer,
I want CaseFile retention enforced at 25 months in prod via automated lifecycle policies with auditable purge operations,
so that regulatory examination windows are satisfied and purges are traceable (FR21).

## Acceptance Criteria

1. **Given** CaseFiles exist in object storage with known creation timestamps
   **When** the retention lifecycle policy executes
   **Then** CaseFiles older than 25 months in prod are purged.
2. **And** purge operations are auditable: logged with timestamp, scope (`case_id`s affected), and policy reference.
3. **And** no manual ad-hoc deletion is permitted without governance approval.
4. **And** retention periods are configurable per environment.
5. **And** lifecycle policies can be run as a scheduled operation.
6. **And** unit tests verify: retention threshold calculation, purge logging, environment-specific retention configuration.

## Tasks / Subtasks

- [x] Task 1: Introduce CaseFile retention policy contract and policy artifact (AC: 4)
  - [x] Add `CasefileRetentionPolicyV1` contract with required env map (`local|dev|uat|prod`) and per-env retention values.
  - [x] Add `config/policies/casefile-retention-policy-v1.yaml` with prod set to 25 months and explicit non-prod values.
  - [x] Add contract fixtures/tests to `tests/unit/contracts/conftest.py` and `tests/unit/contracts/test_policy_models.py` (frozen model, round-trip, schema version, prod retention assertion).

- [x] Task 2: Add retention lifecycle execution module in storage boundary (AC: 1, 2, 5)
  - [x] Create `src/aiops_triage_pipeline/storage/lifecycle.py` with a policy-driven runner that:
    - resolves env-specific cutoff in UTC using aware datetimes,
    - discovers eligible CaseFile objects under `cases/` prefix,
    - maps object keys to `case_id` scope,
    - executes batched purge operations,
    - returns structured run results (scanned/eligible/purged/failed counts + case_ids).
  - [x] Keep lifecycle behavior deterministic and idempotent for repeated scheduled runs.

- [x] Task 3: Extend object-store abstraction for lifecycle operations (AC: 1, 2, 5)
  - [x] Extend `ObjectStoreClientProtocol` and `S3ObjectStoreClient` with listing and batch-delete operations needed by lifecycle runner.
  - [x] Use paginated listing for `cases/` objects and bounded delete batches.
  - [x] Preserve existing `put_if_absent`/`get_object_bytes` semantics and typed dependency errors.

- [x] Task 4: Add governance controls and audit-safe logging (AC: 2, 3)
  - [x] Enforce a governed execution mode for destructive purge (for example, explicit approval/change-ticket metadata required by config/env var).
  - [x] Emit structured lifecycle audit events with: `event_type`, `component`, `policy_ref`, `app_env`, `executed_at`, `case_ids`, `purged_count`, `failed_count`.
  - [x] Ensure logs never include sensitive payload values, only metadata and identifiers required for audit.

- [x] Task 5: Add scheduled operation entrypoint wiring (AC: 5)
  - [x] Extend `src/aiops_triage_pipeline/__main__.py` with a lifecycle mode (single-run and scheduler-friendly invocation).
  - [x] Load casefile retention policy via existing `load_policy_yaml(...)` pattern.
  - [x] Keep runtime configuration and startup logging aligned with existing settings patterns.

- [x] Task 6: Testing and regression coverage (AC: 6)
  - [x] Add unit tests for cutoff math, env-specific retention selection, governance gate behavior, and audit log payload structure.
  - [x] Add unit tests for paginator/list and batched delete behavior in lifecycle runner.
  - [x] Add integration coverage with object-store boundary to validate purge scope (`case_id`s), idempotent reruns, and failure handling.
  - [x] Confirm no regression to existing CaseFile write-once/hash integrity tests.

- [x] Task 7: Quality gates
  - [x] `uv run pytest -q tests/unit/contracts/test_policy_models.py tests/unit/storage/test_casefile_io.py tests/unit/storage/test_casefile_lifecycle.py`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs tests/integration/test_casefile_lifecycle.py -m integration`
  - [x] `uv run ruff check`

## Dev Notes

### Developer Context Section

- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
  - Story key: `4-7-casefile-retention-and-lifecycle-management`
  - Story ID: `4.7`
- Epic context: Epic 4 (`FR17`-`FR26`) focuses on durable CaseFile/outbox behavior.
- This story completes FR21 in the same durability/governance lane as Stories 4.2-4.6.
- Current repo state:
  - CaseFile stage writes and hash validation are implemented in `storage/casefile_io.py`.
  - Object store adapter currently supports write-once and read operations (`storage/client.py`).
  - Outbox already has retention-by-env policy modeling and cleanup selection patterns (`contracts/outbox_policy.py`, `outbox/state_machine.py`, `outbox/repository.py`).
  - No CaseFile retention lifecycle executor exists yet.

### Technical Requirements

- Enforce FR21 exactly:
  - prod retention window = 25 months,
  - automated lifecycle execution,
  - auditable purge operations including affected `case_id` scope.
- Retention must be environment-configurable and policy-driven (no hardcoded env branching).
- Purge logic must operate only on canonical CaseFile paths under `cases/{case_id}/{stage}.json`.
- Cutoff calculations must use timezone-aware UTC datetimes; reject naive timestamps.
- Purge execution must be idempotent and safe for scheduled reruns.
- Governance control is mandatory for deletion execution; ad-hoc/manual delete paths are not permitted.
- Maintain existing invariants and boundaries:
  - no mutation of existing stage files,
  - no changes to Invariant A/B2 behavior,
  - no weakening of hash-validation/write-once constraints.

### Architecture Compliance

- Align with architecture decisions and mappings:
  - Data architecture: object storage remains CaseFile system-of-record (`cases/{case_id}/{stage}.json`).
  - Serialization/integrity: keep Pydantic JSON + hash integrity chain untouched.
  - Security/governance: lifecycle/purge behavior must be policy-versioned and auditable.
  - Package boundaries: keep lifecycle logic in storage/config/contracts layers; avoid coupling to pipeline stage internals.
- Reuse established patterns from outbox lifecycle handling:
  - env-specific retention policy contract,
  - deterministic cutoff resolver,
  - typed error behavior for critical dependency failures.

### Library / Framework Requirements

- Required project baselines for this story path:
  - `boto3~=1.42`
  - `pydantic==2.12.5`
  - `pydantic-settings~=2.13.1`
  - `pytest==9.0.2`, `testcontainers==4.14.1`
- Use boto3 S3 client patterns already in repo; do not introduce a second object-store SDK.
- Keep Python datetime handling consistent with project rule: aware UTC timestamps only.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/contracts/casefile_retention_policy.py` (new)
  - `config/policies/casefile-retention-policy-v1.yaml` (new)
  - `src/aiops_triage_pipeline/storage/lifecycle.py` (new)
  - `src/aiops_triage_pipeline/storage/client.py` (extend protocol/adapter for list+delete)
  - `src/aiops_triage_pipeline/__main__.py` (add lifecycle mode wiring)
- Test targets:
  - `tests/unit/contracts/conftest.py` (fixture additions)
  - `tests/unit/contracts/test_policy_models.py` (contract coverage additions)
  - `tests/unit/storage/test_casefile_lifecycle.py` (new)
  - `tests/integration/test_casefile_lifecycle.py` (new)
- Keep existing file ownership intact:
  - Do not move or rewrite outbox modules for this story.

### Testing Requirements

- Unit tests must verify:
  - env-specific retention resolution (including prod=25 months),
  - cutoff derivation in UTC and naive-datetime rejection,
  - eligible object selection and `case_id` extraction from key layout,
  - batched delete behavior and partial failure handling,
  - governance-gated delete execution,
  - structured audit logging fields and policy reference inclusion.
- Integration tests must verify:
  - end-to-end lifecycle run against object-store boundary,
  - only expired objects are purged,
  - audit scope contains expected `case_id`s,
  - repeated scheduled runs are idempotent,
  - non-expired CaseFiles remain untouched.
- Regression expectations:
  - existing `tests/unit/storage/test_casefile_io.py` and `tests/integration/test_casefile_write.py` behavior remains unchanged.

### Previous Story Intelligence

From Story 4.6 (`4-6-triageexcerpt-exposure-denylist-enforcement.md`):
- Keep cross-cutting behavior centralized (single shared enforcement patterns, avoid boundary-specific forks).
- Preserve deterministic failure handling with typed exceptions; never fail silently.
- Keep structured logs audit-safe and metadata-only where sensitive content could leak.
- Maintain strict quality-gate discipline: targeted unit tests + integration path + lint.

Carry-forward to Story 4.7:
- Implement lifecycle behavior in one storage-focused path (no duplicate purge logic).
- Treat retention governance and audit trails as first-class acceptance criteria, not secondary logs.

### Git Intelligence Summary

Recent commits (latest first):
- `c6c0a0a` - fix(story-4.6): resolve code review findings and finalize status
- `24b46c2` - fix(outbox): harden publisher reliability and backlog health visibility
- `6212c93` - feat(story-4.5): implement durable outbox kafka publisher
- `752d72c` - Fix Story 4-4-postgres-durable-outbox-state-machine
- `a864bc5` - Fix Story 4.3 review findings and complete stage coverage

Actionable patterns:
- Add new behavior as focused modules with explicit tests instead of broad refactors.
- Keep durability-related logic strongly typed and transition-safe.
- Maintain sprint artifact hygiene (`story doc` + `sprint-status` transition).

### Latest Tech Information

Verification date: 2026-03-06.

- `boto3` latest listed release is in the `1.42.x` line (`1.42.58` as of 2026-02-26), which is compatible with project pin `boto3~=1.42`.
- `S3.Client.put_bucket_lifecycle_configuration` semantics: applying lifecycle config replaces prior config and supports up to 1,000 rules.
- S3 expiration behavior is asynchronous; there can be delay between eligibility and physical removal.
- For lifecycle verification/monitoring, AWS documents using `HeadObject`/`GetObject` expiry headers and list/inventory checks.
- For explicit cleanup jobs, boto3 guidance remains:
  - list objects with `list_objects_v2` + paginator,
  - batch purge via `delete_objects` (up to 1,000 keys/request).
- MinIO lifecycle behavior remains scanner-driven and S3-compatible, so expiration application may be delayed under load.
- Python datetime docs continue to recommend aware UTC timestamps for reliable time arithmetic.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- Never bypass durability controls or weaken invariant behaviors.
- Keep cross-cutting logic centralized; avoid parallel policy evaluators.
- Use structured logging and do not leak sensitive values.
- Validate at boundaries and preserve frozen contract-first implementation style.
- High-risk policy/governance changes require targeted regression tests.

### Project Structure Notes

- Existing structure strongly supports this story by extending:
  - `contracts/` for policy model,
  - `config/policies/` for versioned artifact,
  - `storage/` for lifecycle executor,
  - `__main__.py` for operational mode wiring,
  - `tests/unit` and `tests/integration` for guardrail coverage.
- No UX artifact dependency is required for this backend-only story.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 4.7: CaseFile Retention & Lifecycle Management`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 4: Durable Triage & Reliable Event Publishing`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR21)]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` (retention governance, auditable purge)]
- [Source: `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md` (object store retention + stage paths)]
- [Source: `artifact/planning-artifacts/architecture.md` (CaseFile management + storage architecture + policy constraints)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/4-6-triageexcerpt-exposure-denylist-enforcement.md`]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py`]
- [Source: `src/aiops_triage_pipeline/storage/client.py`]
- [Source: `src/aiops_triage_pipeline/contracts/outbox_policy.py`]
- [Source: `src/aiops_triage_pipeline/outbox/state_machine.py`]
- [Source: `src/aiops_triage_pipeline/outbox/repository.py`]
- [Source: https://pypi.org/pypi/boto3]
- [Source: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_bucket_lifecycle_configuration.html]
- [Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html]
- [Source: https://docs.aws.amazon.com/boto3/latest/guide/paginators.html]
- [Source: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/list_objects_v2.html]
- [Source: https://docs.aws.amazon.com/boto3/latest/reference/services/s3/bucket/delete_objects.html]
- [Source: https://docs.python.org/3/library/datetime.html]
- [Source: https://min.io/docs/minio/linux/administration/object-management/object-lifecycle-management.html]
- [Source: https://min.io/docs/minio/linux/reference/minio-mc/mc-ilm-rule-add.html]

### Story Completion Status

- Story context generated with implementation guardrails for FR21.
- Story file: `artifact/implementation-artifacts/4-7-casefile-retention-and-lifecycle-management.md`.
- Story status set to: `done`.
- Completion note: comprehensive retention/lifecycle implementation guide created for dev execution.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`
- Review workflow config: `_bmad/bmm/workflows/4-implementation/code-review/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml` (`review` story key at review start: `4-7-casefile-retention-and-lifecycle-management`)
- Core source artifacts:
  - `artifact/planning-artifacts/epics.md`
  - `artifact/planning-artifacts/architecture.md`
  - `artifact/planning-artifacts/prd/functional-requirements.md`
  - `artifact/planning-artifacts/prd/domain-specific-requirements.md`
  - `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md`
  - `artifact/project-context.md`
- Validation commands executed:
  - `uv run pytest -q tests/unit/contracts/test_policy_models.py tests/unit/storage/test_casefile_io.py tests/unit/storage/test_casefile_lifecycle.py`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs tests/integration/test_casefile_lifecycle.py -m integration`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs tests/integration/test_casefile_write.py -m integration`
  - `uv run ruff check`

### Completion Notes List

- Implemented `CasefileRetentionPolicyV1` contract and `config/policies/casefile-retention-policy-v1.yaml` with `prod=25` months and explicit non-prod values.
- Added lifecycle execution module `storage/lifecycle.py` with UTC-aware cutoff math, canonical `cases/{case_id}/{stage}.json` scope parsing, deterministic key ordering, bounded batch deletes, idempotent reruns, and structured run results.
- Extended `ObjectStoreClientProtocol`/`S3ObjectStoreClient` with paginated listing and batch-delete APIs while preserving typed dependency errors and existing write/read semantics.
- Added governance gate requiring approval metadata for destructive purges and structured lifecycle audit events containing required audit fields.
- Hardened delete boundary controls so `delete_objects_batch(...)` requires `governance_approval_ref` for any destructive delete request.
- Updated lifecycle purge semantics to evaluate retention at case scope (using canonical case creation timestamp preference from `triage.json`) and purge full eligible case scope deterministically.
- Added policy artifact validation test that loads `config/policies/casefile-retention-policy-v1.yaml` and asserts required env keys + `prod=25` months.
- Tightened lifecycle integration fixture skip behavior to Docker/environment failures only so setup regressions fail loudly.
- Added scheduled lifecycle mode wiring in `__main__.py` and lifecycle settings in `config/settings.py` for poll interval, pagination, delete batch size, and governance metadata.
- Added comprehensive unit and integration coverage for cutoff selection, governance enforcement, pagination/deletion behavior, audit logging shape, purge scope, idempotent reruns, and partial delete failures.
- Ran and passed all story quality gates and regression checks.

### File List

- `src/aiops_triage_pipeline/contracts/casefile_retention_policy.py`
- `src/aiops_triage_pipeline/contracts/__init__.py`
- `config/policies/casefile-retention-policy-v1.yaml`
- `src/aiops_triage_pipeline/storage/client.py`
- `src/aiops_triage_pipeline/storage/lifecycle.py`
- `src/aiops_triage_pipeline/storage/__init__.py`
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/__main__.py`
- `tests/unit/contracts/conftest.py`
- `tests/unit/contracts/test_policy_models.py`
- `tests/unit/storage/test_casefile_lifecycle.py`
- `tests/integration/test_casefile_lifecycle.py`
- `tests/unit/test_main.py`
- `artifact/implementation-artifacts/4-7-casefile-retention-and-lifecycle-management.md`

### Senior Developer Review (AI)

- Review date: 2026-03-06
- Outcome: Changes Requested (resolved in this pass)
- Findings fixed: 4 (2 High, 2 Medium)
- Fix summary:
  - Enforced governed deletion at object-store API boundary (`delete_objects_batch` now requires governance approval metadata).
  - Corrected retention purge behavior to evaluate at case scope and purge all stage files for an eligible case.
  - Added policy-artifact-backed test coverage for `config/policies/casefile-retention-policy-v1.yaml`.
  - Narrowed integration fixture skip handling to explicit Docker/environment failure classes.

### Change Log

- 2026-03-06: Implemented Story 4.7 CaseFile retention lifecycle (policy contract/artifact, storage lifecycle runner, governance/audit controls, CLI scheduling mode, and full unit/integration validation).
- 2026-03-06: Code review remediation pass completed (governed delete boundary, case-scope retention purge semantics, artifact-backed policy test coverage, and stricter integration fixture error handling).
