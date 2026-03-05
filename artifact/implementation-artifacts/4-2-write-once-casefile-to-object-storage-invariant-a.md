# Story 4.2: Write-Once CaseFile to Object Storage (Invariant A)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want CaseFile `triage.json` written to object storage as a write-once artifact before any Kafka header is published,
so that the durability guarantee (Invariant A) ensures no event reaches consumers without its backing evidence existing in storage (FR18).

## Acceptance Criteria

1. **Given** a CaseFile triage stage has been assembled  
   **When** the triage stage is persisted  
   **Then** `triage.json` is written to object storage at `cases/{case_id}/triage.json`.
2. **And** the write completes successfully before any outbox record transitions to `READY`.
3. **And** if object storage is unavailable, the pipeline halts for this case with explicit alerting (NFR-R2) with no silent degradation.
4. **And** the write is idempotent; retrying the same `case_id` produces the same result.
5. **And** the SHA-256 hash is stored in the outbox record for tamper-evidence verification.
6. **And** integration tests verify Invariant A: CaseFile exists in object storage before Kafka header appears (NFR-T2).
7. **And** integration tests use MinIO via testcontainers.

## Tasks / Subtasks

- [ ] Task 1: Implement object storage write-once persistence for triage artifacts (AC: 1, 4)
  - [ ] Add object-store client and persistence helpers in `src/aiops_triage_pipeline/storage/client.py` and `src/aiops_triage_pipeline/storage/casefile_io.py` for `cases/{case_id}/triage.json` writes.
  - [ ] Use a conditional create/write-once path (S3 conditional request) to prevent overwrite of existing objects.
  - [ ] On duplicate writes, verify idempotency by comparing stored content hash/object bytes with the triage artifact being retried.

- [ ] Task 2: Enforce Invariant A sequencing in stage orchestration (AC: 2, 3)
  - [ ] Implement Stage 4 persistence orchestration in `src/aiops_triage_pipeline/pipeline/stages/casefile.py` so object write confirmation happens before any READY transition path is possible.
  - [ ] Fail fast with `CriticalDependencyError`/`InvariantViolation` on object-store unavailability or write-once violations.
  - [ ] Emit structured logs with `case_id`, object path, and outcome for auditability.

- [ ] Task 3: Thread triage hash and object reference into outbox-ready inputs (AC: 2, 5)
  - [ ] Define a typed handoff payload (stage output/model) that includes `case_id`, object path, and `triage_hash` required for outbox persistence.
  - [ ] Ensure READY transition logic can only consume this confirmed-write payload.
  - [ ] Keep full outbox DB state-machine implementation scope aligned with Story 4.4, but provide the guardrail contract now.

- [ ] Task 4: Preserve security and minimization boundaries from Story 4.1 (AC: 1, 4)
  - [ ] Persist only validated serialized triage payload output from Story 4.1.
  - [ ] Do not bypass denylist/minimization paths; never write secrets/credentials/PII into object payload.

- [ ] Task 5: Add unit tests for write-once + idempotency semantics (AC: 3, 4, 5)
  - [ ] Add/extend `tests/unit/storage/test_casefile_io.py` for conditional write behavior, duplicate-write idempotent success, and mismatch failure.
  - [ ] Add/extend stage tests in `tests/unit/pipeline/stages/test_casefile.py` for sequencing guardrail (no READY path without confirmed write).
  - [ ] Add failure-path tests for object-store unavailability and invariant-breaking scenarios.

- [ ] Task 6: Add integration coverage for Invariant A using MinIO + outbox path (AC: 6, 7)
  - [ ] Add `tests/integration/test_casefile_write.py` to verify object existence at `cases/{case_id}/triage.json` before any Kafka publish evidence.
  - [ ] Use testcontainers-backed MinIO for isolated integration runs and assert persisted content hash integrity.
  - [ ] Validate retry behavior remains idempotent under transient failures.

- [ ] Task 7: Quality gates
  - [ ] `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py`
  - [ ] `uv run pytest -q tests/integration/test_casefile_write.py -m integration`
  - [ ] `uv run pytest -q`
  - [ ] `uv run ruff check`

## Dev Notes

### Developer Context Section

- Artifact discovery summary (`discover_inputs` protocol):
  - `epics_content`: loaded from 1 file: `artifact/planning-artifacts/epics.md`
  - `architecture_content`: loaded from 1 file: `artifact/planning-artifacts/architecture.md`
  - `prd_content`: selectively loaded from 5 files:
    - `artifact/planning-artifacts/prd/functional-requirements.md`
    - `artifact/planning-artifacts/prd/non-functional-requirements.md`
    - `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md`
    - `artifact/planning-artifacts/prd/domain-specific-requirements.md`
    - `artifact/planning-artifacts/prd/success-criteria.md`
  - `ux_content`: none found
  - `project_context`: loaded from `artifact/project-context.md`
- Story targeting:
  - Selected from sprint status first backlog item: `4-2-write-once-casefile-to-object-storage-invariant-a`
  - Story ID: `4.2` (Epic 4, Story 2)
- Epic 4 context relevant to this story:
  - Story 4.1 assembles/validates/hash-stamps `triage.json` payload
  - Story 4.2 persists that payload as write-once artifact (Invariant A)
  - Story 4.4/4.5 later build full outbox state-machine and publisher flows
- Current repository baseline:
  - `src/aiops_triage_pipeline/storage/client.py` is placeholder (empty)
  - `src/aiops_triage_pipeline/storage/casefile_io.py` is placeholder (empty)
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py` is placeholder (empty)
  - `src/aiops_triage_pipeline/outbox/{schema.py,state_machine.py,publisher.py}` are placeholders
  - Existing stage outputs/contracts already available and should be reused (`EvidenceStageOutput`, `PeakStageOutput`, `TopologyStageOutput`, `GateInputV1`, `ActionDecisionV1`, `CaseHeaderEventV1`, `TriageExcerptV1`)
- Sequencing note:
  - Story 4.1 is currently `ready-for-dev` (not yet `done`), so 4.2 implementation must either:
    - build directly on completed 4.1 outputs once merged, or
    - include minimal interim adapters with clear TODO boundaries to avoid duplicating 4.1 logic.

### Technical Requirements

- Persistence target and pathing:
  - Persist triage stage bytes to `cases/{case_id}/triage.json` exactly (no env prefix, no alternate naming).
  - Ensure object key derivation is deterministic from `case_id`.
- Write-once and idempotency semantics:
  - First successful write creates the object.
  - Retries for the same `case_id` must be idempotent:
    - if existing content matches expected hash/bytes, treat as success (no mutation),
    - if existing content differs, raise invariant violation (tamper/conflict signal).
  - Never perform blind overwrite for `triage.json`.
- Invariant A sequencing:
  - Object-store write confirmation is a hard precondition for any outbox READY transition.
  - READY transition path must consume only a confirmed-write payload.
- Failure handling:
  - Object-store unavailability is critical-path failure (NFR-R2): fail loudly and halt this case path.
  - Map transient object-store errors into explicit exceptions/log events; do not silently degrade.
- Hash integrity:
  - Use Story 4.1 triage hash as source-of-truth for persisted object identity.
  - Thread `triage_hash` into outbox-ready data for downstream tamper-evidence checks.
- Serialization boundary discipline:
  - Persist canonical serialized bytes (`model_dump_json()` output path from Story 4.1).
  - Re-validation/readback helpers should use `model_validate_json()` on external I/O boundaries.

### Architecture Compliance

- Align with architecture decisions:
  - **1C Object storage layout:** `cases/{case_id}/{stage}.json` (this story: `triage.json`).
  - **3D CaseFile serialization + SHA-256:** hash computed over serialized JSON bytes; hash carried with outbox metadata.
  - **4C critical dependency behavior:** object-store failures are halt-class, not degradable.
  - **5B local topology:** MinIO-backed local object storage parity for invariant testing.
- Enforce FR/NFR guardrails:
  - FR18 Invariant A (write-before-publish) is non-negotiable.
  - NFR-R2 critical dependency stop-on-failure for object storage.
  - NFR-T2 requires explicit automated verification of Invariant A.
- Package/boundary constraints:
  - `storage/` owns object I/O and persistence primitives.
  - `pipeline/stages/casefile.py` owns orchestration and sequencing.
  - `outbox/` consumes confirmed-write metadata; no bypass path from stage logic directly to publish readiness.
  - Keep `config/` leaf package rule intact (no imports from runtime pipeline modules into config).
- Do not regress completed story behavior:
  - Preserve Stage 1 UNKNOWN semantics and Stage 3 routing outputs.
  - Preserve frozen contract usage and structured logging/event field conventions.

### Library / Framework Requirements

- Runtime/tooling baseline (from `pyproject.toml`):
  - Python `>=3.13`
  - `boto3~=1.42` for S3/MinIO object operations
  - `pydantic==2.12.5` for model serialization/validation boundaries
  - `pytest==9.0.2`, `pytest-asyncio==1.3.0`, `testcontainers==4.14.1`
- S3 write-once implementation expectations:
  - Use boto3 S3 `put_object` with conditional request semantics for create-only writes.
  - Handle conditional failure responses explicitly (idempotent duplicate vs conflict/mismatch).
  - Set explicit content type (`application/json`) and include checksum metadata where practical.
- Error mapping:
  - Map boto3/botocore client errors into project exception taxonomy (`CriticalDependencyError`, `InvariantViolation`, `IntegrationError` as appropriate by failure class).
- Linting/style:
  - Keep Ruff-compliant style (`E,F,I,N,W`), Python 3.13 typing conventions, immutable model patterns.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/storage/client.py`
  - `src/aiops_triage_pipeline/storage/casefile_io.py`
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- Likely supporting updates:
  - `src/aiops_triage_pipeline/storage/__init__.py` (export persistence helpers)
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py` (export stage APIs if needed)
  - `src/aiops_triage_pipeline/outbox/schema.py` and/or stage handoff models for `triage_hash` + object path contracts (without overreaching Story 4.4 scope)
- Test files to add/update:
  - `tests/unit/storage/test_casefile_io.py`
  - `tests/unit/pipeline/stages/test_casefile.py`
  - `tests/integration/test_casefile_write.py`
- Structure guardrails:
  - Keep object-store details inside `storage/`; do not duplicate S3 calls in pipeline stage modules.
  - Keep stage orchestration in `pipeline/stages/casefile.py`; do not entangle with `outbox/publisher.py`.
  - Preserve naming conventions: snake_case modules/functions, explicit typed models.

### Testing Requirements

- Unit tests (required):
  - Write-once success path: first put writes `cases/{case_id}/triage.json`.
  - Idempotent retry path: duplicate write for same `case_id` and same hash returns success without mutation.
  - Conflict path: duplicate key with mismatched bytes/hash raises invariant violation.
  - Unavailability path: storage outage raises critical dependency error and blocks READY progression.
  - Sequencing path: outbox READY handoff cannot be created if object write confirmation is absent.
- Integration tests (required):
  - MinIO + pipeline integration verifies object exists before any header publish evidence (Invariant A).
  - Retry scenario under transient errors remains idempotent and does not create multiple divergent artifacts.
  - Persisted object content hash matches expected triage hash.
- Regression checks:
  - Existing stage tests (`test_evidence.py`, `test_peak.py`, `test_topology.py`, `test_gating.py`) remain green.
  - Contract round-trip and immutability tests remain green.
- Recommended commands:
  - `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py`
  - `uv run pytest -q tests/integration/test_casefile_write.py -m integration`
  - `uv run pytest -q`
  - `uv run ruff check`

### Previous Story Intelligence

- Story 4.1 output establishes the immediate contract this story should consume:
  - Triage-stage model assembly and deterministic serialization/hash responsibilities are defined in Story 4.1 guidance.
  - Story 4.2 should persist that artifact, not redesign data shape or hashing semantics.
- Key carry-over constraints from Story 4.1:
  - Reuse shared `apply_denylist(...)`; no boundary-specific denylist logic.
  - Use Pydantic JSON boundary methods (`model_dump_json` / `model_validate_json`).
  - Preserve policy version stamps + `triage_hash` as audit-critical metadata.
- Practical sequencing insight:
  - Story 4.1 and 4.2 are tightly coupled: if 4.1 code is not merged yet, implement minimal adapter seams instead of duplicating its logic.
  - Keep hard boundary: Story 4.2 handles persistence + ordering; Story 4.4 handles full durable-outbox state machine.
- Known current baseline risk from prior story notes:
  - Core files for casefile/storage/outbox paths are still placeholders, so this story must establish first concrete write-path patterns and tests.

### Git Intelligence Summary

- Recent commit titles (latest 5):
  - `dcc91c8` feat(story-3.5): add v0 compat views and resolve review findings
  - `bfcd6db` feat(story-3.4): implement multi-level ownership routing
  - `e8f368a` fix(story-3.3): dedupe downstream impacts and finalize review sync
  - `24d6c01` feat: finalize story 3.2 review fixes and validation hardening
  - `47ce6ae` feat(registry): implement topology loader v0/v1 with validations and reload
- Observed implementation patterns from recent commits:
  - Use immutable Pydantic models with explicit freeze of nested mappings (`MappingProxyType`) where needed.
  - Deterministic ordering in stage assembly paths (`sorted(...)` iteration for repeatable outputs).
  - Structured logging with stable `event_type` fields and explicit diagnostics payloads.
  - Strong unit-test mirroring of source structure (`tests/unit/<domain>/...`).
  - Stage API exports are curated through `pipeline/stages/__init__.py`.
- Actionable implications for Story 4.2:
  - Keep write-path outputs deterministic and immutable to match established stage style.
  - Add storage/casefile tests with the same strictness as topology/gating test suites.
  - Preserve clean package boundaries and explicit exports for newly introduced helpers.

### Latest Tech Information

Verification date: **March 4, 2026**.

- AWS S3 conditional-write behavior (official):
  - Use `If-None-Match: *` for create-only semantics; S3 only writes if object key does not already exist.
  - On concurrent writers, first finisher succeeds; later conflicting writes return `412 Precondition Failed`.
  - `409 Conflict` can occur in race conditions and is explicitly retriable.
- AWS S3 durability semantics relevant to write-once:
  - `PutObject` is all-or-nothing (no partial-object writes on success/failure boundary).
- boto3 status:
  - Boto3 documentation currently shows `1.42.60`; project pin `boto3~=1.42` remains aligned with this minor line.
  - `put_object` supports conditional semantics and checksum fields (`ChecksumSHA256`) useful for integrity checks.
- MinIO object immutability notes (official MinIO docs):
  - MinIO supports object lock/immutability with S3-compatible behavior.
  - MinIO docs note enabling object lock on **existing** buckets starts from `RELEASE.2025-05-20T20-30-00Z`.
  - **Inference:** this repo’s local MinIO image is `RELEASE.2025-01-20T14-49-07Z`, so existing-bucket object-lock enablement is not available in local baseline; Story 4.2 should rely on application-level conditional write-once enforcement and idempotency checks.
- Pydantic JSON boundary APIs:
  - Current docs continue to use `model_dump_json()` / `model_validate_json()` as canonical JSON serialize/validate boundary methods, consistent with Story 4.1/4.2 design.

### Project Context Reference

Critical rules applied from `artifact/project-context.md`:

- Preserve deterministic guardrails:
  - Hot path remains deterministic and independent from LLM/cold-path behavior.
  - Do not introduce alternate decision paths that bypass policy authority.
- Use shared cross-cutting primitives only:
  - Shared denylist enforcement (`apply_denylist(...)`)
  - Shared exception taxonomy (`errors/exceptions.py`)
  - Shared structured logging conventions and correlation context
- Maintain safety and security posture:
  - No secrets in logs/artifacts.
  - Fail loudly on critical dependency failures; never silent degradation for object storage outages.
- Respect framework and config boundaries:
  - Keep `config` package leaf behavior.
  - Keep integration mode semantics and environment caps centralized.
- Testing discipline:
  - Add targeted unit/integration tests for changed behaviors in storage/casefile boundaries.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 4.2: Write-Once CaseFile to Object Storage (Invariant A)`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 4: Durable Triage & Reliable Event Publishing`]
- [Source: `artifact/planning-artifacts/architecture.md` (Decisions 1C, 3D, 4C, 5B; package boundaries and invariants)]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR18, FR22-FR23, FR59)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-R2, NFR-T2)]
- [Source: `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md` (hot-path stage ordering, CaseFile lifecycle)]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` (write-once/append-only, hash integrity)]
- [Source: `artifact/planning-artifacts/prd/success-criteria.md` (Invariant A outcome metrics)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/4-1-casefile-triage-stage-assembly.md`]
- [Source: `pyproject.toml`]
- [Source: `docker-compose.yml`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `src/aiops_triage_pipeline/contracts/{gate_input.py,action_decision.py,case_header_event.py,triage_excerpt.py,diagnosis_report.py}`]
- [Source: `src/aiops_triage_pipeline/models/{evidence.py,peak.py}`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/{gating.py,topology.py}`]
- [Source: `src/aiops_triage_pipeline/errors/exceptions.py`]
- [Source: `https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html`]
- [Source: `https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html`]
- [Source: `https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html`]
- [Source: `https://docs.min.io/community/minio-object-store/administration/object-management/object-locking.html`]
- [Source: `https://docs.pydantic.dev/changelog/`]
- [Source: `https://docs.pydantic.dev/latest/concepts/serialization/`]

### Story Completion Status

- Story context generation complete.
- Story file: `artifact/implementation-artifacts/4-2-write-once-casefile-to-object-storage-invariant-a.md`.
- Target status: `ready-for-dev`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created**.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`.
- Story selected from `artifact/implementation-artifacts/sprint-status.yaml` as first backlog item in order: `4-2-write-once-casefile-to-object-storage-invariant-a`.
- Epic/story context loaded from planning artifacts, project context, prior story file, and repository source tree.
- Latest-technology verification performed on March 4, 2026 using official documentation.

### Completion Notes List

- Story context generated with implementation guardrails focused on Invariant A and idempotent write-once behavior.
- Includes explicit sequencing requirements so no outbox record can transition to READY before object-store write confirmation.
- Includes latest S3 conditional-write semantics and MinIO object-lock constraints relevant to local environment.

### File List

- `artifact/implementation-artifacts/4-2-write-once-casefile-to-object-storage-invariant-a.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
