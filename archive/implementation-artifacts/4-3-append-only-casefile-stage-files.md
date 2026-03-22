# Story 4.3: Append-Only CaseFile Stage Files

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want additional CaseFile stage files (`diagnosis`, `linkage`, `labels`) written to the same case directory without mutating prior stage files,
so that each stage is independently immutable and the hash integrity chain is preserved across stages (FR19).

## Acceptance Criteria

1. **Given** a CaseFile `triage.json` exists for a case  
   **When** a cold-path stage completes (`diagnosis`, `linkage`, or `labels`)  
   **Then** the new stage file is written to `cases/{case_id}/{stage}.json` (for example, `diagnosis.json`, `linkage.json`, `labels.json`).
2. **And** prior stage files are never read-modify-written; each stage writes its own file independently.
3. **And** each new stage file includes SHA-256 hashes of prior stage files it depends on (hash chain).
4. **And** missing stage files indicate the stage did not complete (for example, no `diagnosis.json` if LLM timed out) and are treated as explicit absence, not runtime errors.
5. **And** unit tests verify independent stage writes, prior files unchanged after append, hash-chain integrity, and missing-stage-file handling.

## Tasks / Subtasks

- [x] Task 1: Define append-only stage contracts and dependency-hash metadata (AC: 1, 3)
  - [x] Extend `src/aiops_triage_pipeline/models/case_file.py` with explicit models for additional stage files:
    - `CaseFileDiagnosisV1`
    - `CaseFileLinkageV1`
    - `CaseFileLabelsV1`
  - [x] Add typed dependency hash metadata fields (for example: `triage_hash`, optional `diagnosis_hash`) so each stage records prior-stage dependencies.
  - [x] Keep models immutable (`frozen=True`) and schema-versioned.

- [x] Task 2: Implement canonical stage path + stage write helpers (AC: 1, 2)
  - [x] Add deterministic key/path helpers in `src/aiops_triage_pipeline/storage/casefile_io.py` for `cases/{case_id}/{stage}.json`.
  - [x] Restrict stage names to the canonical set (`triage`, `diagnosis`, `linkage`, `labels`) to prevent rogue file writes.
  - [x] Reuse Story 4.2 write-once behavior (or shared helper) so stage writes do not overwrite existing stage objects.

- [x] Task 3: Implement append-only stage persistence orchestration (AC: 1, 2, 3)
  - [x] Add stage-specific persistence entry points in `src/aiops_triage_pipeline/pipeline/stages/casefile.py` that:
    - serialize via Pydantic JSON boundary methods,
    - persist each stage independently,
    - include prior-stage hashes in payload before write.
  - [x] Enforce no read-modify-write behavior on prior files; only dependency-hash verification reads are allowed.
  - [x] Raise `InvariantViolation` for hash-chain conflicts/tamper mismatch and halt that case path.

- [x] Task 4: Make missing-stage semantics explicit and safe (AC: 4)
  - [x] Add read/list helpers that return explicit absence (for example `None`) for missing optional stage files.
  - [x] Ensure cold-path flows can proceed with expected absence semantics (for example, no `diagnosis.json` after timeout).
  - [x] Emit structured logs indicating stage absence as state, not error.

- [x] Task 5: Preserve Story 4.1/4.2 invariants and package boundaries (AC: 2, 3)
  - [x] Reuse existing triage hash helpers from `storage/casefile_io.py`; do not duplicate hashing logic.
  - [x] Keep object I/O in `storage/`; keep orchestration in `pipeline/stages/casefile.py`.
  - [x] Update exports (`models/__init__.py`, `storage/__init__.py`, optionally `pipeline/stages/__init__.py`) for new stage APIs.

- [x] Task 6: Add unit coverage for append-only behavior and hash chain (AC: 5)
  - [x] Extend `tests/unit/storage/test_casefile_io.py` for stage key generation, stage write idempotency, and overwrite rejection.
  - [x] Extend `tests/unit/pipeline/stages/test_casefile.py` for dependency-hash stamping, prior-file immutability, and missing-stage handling.
  - [x] Add negative tests for invalid stage names and dependency-hash mismatch.

- [x] Task 7: Quality gates
  - [x] `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py`
  - [x] `uv run pytest -q`
  - [x] `uv run ruff check`

## Dev Notes

### Developer Context Section

- Artifact discovery summary (`discover_inputs` protocol):
  - `epics_content`: `artifact/planning-artifacts/epics.md`
  - `architecture_content`: `artifact/planning-artifacts/architecture.md`
  - `prd_content` (selective):
    - `artifact/planning-artifacts/prd/functional-requirements.md`
    - `artifact/planning-artifacts/prd/non-functional-requirements.md`
    - `artifact/planning-artifacts/prd/domain-specific-requirements.md`
    - `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md`
  - `project_context`: `artifact/project-context.md`
  - `ux_content`: not found
- Story targeting:
  - Selected from first `backlog` item in `artifact/implementation-artifacts/sprint-status.yaml`.
  - Story key: `4-3-append-only-casefile-stage-files`
  - Story ID: `4.3`
- Epic sequencing context:
  - Story 4.1 is `done` and already delivered triage assembly + deterministic hash enforcement.
  - Story 4.2 is `ready-for-dev` and introduces write-once object persistence for `triage.json` (Invariant A).
  - Story 4.3 must build on 4.1 outputs and align with 4.2 write-path contracts without re-implementing them.
- Current repository baseline relevant to this story:
  - Implemented: `models/case_file.py` (triage model), `storage/casefile_io.py` (triage serialization/hash), `pipeline/stages/casefile.py` (triage assembly).
  - Placeholder/empty and still expected downstream:
    - `src/aiops_triage_pipeline/storage/client.py`
    - `src/aiops_triage_pipeline/pipeline/stages/outbox.py`
    - `src/aiops_triage_pipeline/outbox/schema.py`
    - `src/aiops_triage_pipeline/outbox/state_machine.py`
    - `src/aiops_triage_pipeline/outbox/publisher.py`
  - Existing integration test surface is minimal; no dedicated CaseFile append-only integration file exists yet.

### Technical Requirements

- Stage-file append-only rules:
  - Each stage writes only its own file (`diagnosis.json`, `linkage.json`, `labels.json`) under `cases/{case_id}/`.
  - Prior files are immutable after successful write; no in-place mutation.
- Hash-chain requirements:
  - Stage payload must carry hashes of prior stage files it depends on.
  - Hash verification mismatch is halt-class (`InvariantViolation`) because it indicates integrity conflict.
- Missing-stage semantics:
  - Missing optional stage files must be represented as explicit absence, not generic storage failure.
  - Absence is expected in some flows (for example diagnosis timeout) and must be observable.
- Serialization discipline:
  - Use canonical Pydantic JSON boundaries (`model_dump_json` / `model_validate_json`).
  - Keep deterministic SHA-256 hashing and lowercase hex digest format.
- Security/data minimization:
  - Do not introduce secrets/PII into CaseFile stage payloads.
  - Preserve denylist governance and exposure-safe payload shaping.

### Architecture Compliance

- Must align with architecture decisions and PRD invariants:
  - Decision 1C: `cases/{case_id}/{stage}.json` canonical storage path.
  - Decision 3D: Pydantic JSON serialization + SHA-256 tamper-evidence.
  - FR19: append-only stage file semantics.
  - NFR-T6: audit completeness via hash and traceable stage data.
- Required boundaries:
  - `storage/` owns object-storage read/write primitives.
  - `pipeline/stages/casefile.py` owns orchestration only.
  - `config/` remains a leaf module and must not import runtime stage logic.
- Regression guardrails:
  - Do not change Story 4.1 triage-hash computation semantics.
  - Do not bypass Story 4.2 write-once guardrails where shared helpers exist.

### Library / Framework Requirements

- Repo baseline versions (must stay consistent with `pyproject.toml` unless explicitly updated):
  - Python `>=3.13`
  - `pydantic==2.12.5`
  - `boto3~=1.42`
  - `pytest==9.0.2`
  - `pytest-asyncio==1.3.0`
  - `testcontainers==4.14.1`
- Stage write implementation guidance:
  - Keep S3/MinIO operations behind shared storage client helpers.
  - For write-once semantics, use conditional write behavior (shared from Story 4.2 path).
  - Keep hash/checksum handling explicit and deterministic.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/models/case_file.py`
  - `src/aiops_triage_pipeline/storage/casefile_io.py`
  - `src/aiops_triage_pipeline/storage/client.py`
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- Supporting updates likely needed:
  - `src/aiops_triage_pipeline/models/__init__.py`
  - `src/aiops_triage_pipeline/storage/__init__.py`
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- Test files to update/create:
  - `tests/unit/storage/test_casefile_io.py`
  - `tests/unit/pipeline/stages/test_casefile.py`
  - optional integration: `tests/integration/pipeline/test_casefile_append_only.py`

### Testing Requirements

- Unit tests required:
  - Stage path generation and stage-name validation.
  - Append-only write semantics per stage file (no overwrite).
  - Hash-chain stamping and dependency-hash mismatch behavior.
  - Explicit missing-stage-file handling behavior.
- Integration coverage target (recommended during implementation):
  - MinIO-backed append-only writes across triage -> diagnosis/linkage/labels flows.
  - Prior-stage immutability checks after later-stage writes.
- Regression checks:
  - Existing triage hash tests remain green.
  - Existing denylist and contract immutability tests remain green.

### Previous Story Intelligence

- From Story 4.1 (`done`):
  - Triage model and hash helpers are already implemented and tested.
  - Dedupe/denylist hardening was added in review follow-ups; do not regress list-value sanitization behavior.
- From Story 4.2 (`ready-for-dev`):
  - Planned object-store write-once logic and outbox-ready sequencing are specified but not yet implemented.
  - Baseline notes in 4.2 still mention some files as placeholders that are now partially implemented; use current repository state, not stale notes.
- Practical implication for 4.3:
  - Implement 4.3 against shared storage abstractions so 4.2 + 4.3 can compose without duplicated write paths.

### Git Intelligence Summary

- Recent commits show the current implementation pattern:
  - `d6f98d7`: hardened triage hash validation and denylist redaction.
  - `dcc91c8`, `bfcd6db`, `e8f368a`: iterative story-by-story delivery with targeted unit tests.
- Actionable repo conventions from recent history:
  - Favor deterministic behavior and strict validation over implicit fallbacks.
  - Keep tests close to domain code (`tests/unit/<domain>/...`) with focused negative-path coverage.
  - Update artifact story files and sprint-status tracking together when workflow milestones complete.

### Latest Tech Information

Verification date: **March 5, 2026**.

- AWS S3 conditional write guidance remains current in official docs:
  - `If-None-Match: *` supports create-if-absent semantics for write-once object creation.
  - Conflict/precondition outcomes (`409`/`412`) must be handled explicitly in idempotent write logic.
- Boto3 API docs (1.42.x line) continue to support the required `put_object` controls and checksum fields for integrity workflows.
- Pydantic current stable line remains 2.12.x; repository pin `2.12.5` is aligned.

Inference from sources:
- No dependency upgrade is required for Story 4.3. The priority is applying existing pinned toolchain correctly to append-only stage semantics and hash-chain integrity.

### Project Context Reference

Critical rules applied from `artifact/project-context.md`:

- Keep deterministic guardrails and never bypass invariant checks.
- Keep hot-path/cold-path boundaries explicit; this story affects staged persistence, not gate authority.
- Reuse shared cross-cutting utilities (hashing, denylist, structured logging) instead of parallel implementations.
- Fail loudly on critical dependency/invariant failures; avoid silent degradation for integrity risks.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 4.3: Append-Only CaseFile Stage Files`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 4: Durable Triage & Reliable Event Publishing`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR19, FR20, FR21)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-R2, NFR-T2, NFR-T6)]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` (write-once/append-only, hash integrity, data minimization)]
- [Source: `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md` (CaseFile lifecycle and stage flow)]
- [Source: `artifact/planning-artifacts/architecture.md` (Decisions 1C, 3D, package boundaries)]
- [Source: `docs/schema-evolution-strategy.md` (CaseFile stage immutability and hash-chain rules)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/4-1-casefile-triage-stage-assembly.md`]
- [Source: `artifact/implementation-artifacts/4-2-write-once-casefile-to-object-storage-invariant-a.md`]
- [Source: `src/aiops_triage_pipeline/models/case_file.py`]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/casefile.py`]
- [Source: `src/aiops_triage_pipeline/errors/exceptions.py`]
- [Source: `pyproject.toml`]
- [Source: `docker-compose.yml`]
- [Source: `https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html`]
- [Source: `https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html`]
- [Source: `https://docs.pydantic.dev/latest/changelog/`]
- [Source: `https://pypi.org/project/testcontainers/`]

### Story Completion Status

- Story context generation complete.
- Story file: `artifact/implementation-artifacts/4-3-append-only-casefile-stage-files.md`.
- Target status: `done`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created**.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml` first backlog story in order (`4-3-append-only-casefile-stage-files`)
- Validation fallback: manual checklist validation used because `_bmad/core/tasks/validate-workflow.xml` is missing in this repository
- Implementation:
  - Added immutable stage models and hash placeholders in `models/case_file.py`.
  - Added canonical stage path, stage hash helpers, write-once persistence helpers, and absent-stage readers in `storage/casefile_io.py`.
  - Added stage orchestration entry points with dependency-hash verification and absence-state logging in `pipeline/stages/casefile.py`.
- Verification:
  - `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Completion Notes List

- Built Story 4.3 context directly from Epic 4 requirements and current repository state.
- Added explicit guardrails to prevent duplicate persistence logic and hash-chain regressions.
- Included dependency/version guidance and official-doc recency checks for storage and serialization behavior.
- Implemented append-only stage models (`CaseFileDiagnosisV1`, `CaseFileLinkageV1`, `CaseFileLabelsV1`) with typed hash-chain fields and strict hash validators.
- Added canonical stage-key construction (`cases/{case_id}/{stage}.json`), canonical stage-name validation, and reusable write-once stage persistence checks.
- Added stage read/list helpers that return explicit absence (`None`) for missing stage files.
- Added stage orchestration functions for diagnosis/linkage/labels with `InvariantViolation` on dependency-hash mismatch or missing required dependencies.
- Added/extended unit tests for stage path generation, append-only/idempotent writes, overwrite rejection, dependency-hash mismatch, prior-file immutability, and stage absence logging.
- Fixed review follow-ups: added linkage/labels unit coverage, hardened typed not-found handling, and removed brittle string-based not-found detection.

### File List

- `artifact/implementation-artifacts/sprint-status.yaml`
- `artifact/implementation-artifacts/4-3-append-only-casefile-stage-files.md`
- `src/aiops_triage_pipeline/models/case_file.py`
- `src/aiops_triage_pipeline/models/__init__.py`
- `src/aiops_triage_pipeline/storage/casefile_io.py`
- `src/aiops_triage_pipeline/storage/client.py`
- `src/aiops_triage_pipeline/storage/__init__.py`
- `src/aiops_triage_pipeline/errors/exceptions.py`
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- `tests/unit/storage/test_casefile_io.py`
- `tests/unit/pipeline/stages/test_casefile.py`

### Change Log

- 2026-03-05: Implemented append-only CaseFile stage-file contracts, canonical stage write/read helpers, stage orchestration with dependency-hash verification, and full unit/regression quality gates.
- 2026-03-05: Senior code review fixes applied for Story 4.3 (linkage/labels coverage, typed not-found exception handling, KeyError narrowing, and story metadata alignment).

### Senior Developer Review (AI)

- Reviewer: Sas (AI)
- Date: 2026-03-05
- Outcome: Approved
- Findings fixed:
  - Added unit coverage for linkage/labels stage write paths and missing-stage semantics.
  - Replaced string-prefix not-found checks with typed `ObjectNotFoundError`.
  - Narrowed `KeyError` handling to only treat matching object-key misses as explicit absence.
  - Aligned story metadata/status fields to `done`.
- Verification rerun:
  - `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - `uv run ruff check`
