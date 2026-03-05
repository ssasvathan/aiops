# Story 4.1: CaseFile Triage Stage Assembly

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the system to assemble a complete CaseFile triage stage containing evidence, gating inputs, action decisions, and policy version stamps,
so that every triage decision is captured as a self-contained, auditable artifact with tamper-evident hashing (FR17, FR20).

## Acceptance Criteria

1. **Given** evidence, topology, and gating results are available for a case  
   **When** the CaseFile triage stage is assembled  
   **Then** `triage.json` contains: evidence snapshot, gating inputs (GateInput.v1 fields), ActionDecision.v1, and policy version stamps (`rulebook_version`, `peak_policy_version`, `prometheus_metrics_contract_version`, `exposure_denylist_version`, `diagnosis_policy_version`).
2. **And** a SHA-256 content hash is computed over the serialized JSON bytes and included in the artifact.
3. **And** data minimization is enforced: no PII, credentials, or secrets in the CaseFile.
4. **And** sensitive fields are redacted per the exposure denylist before inclusion.
5. **And** the triage stage is serialized via Pydantic `.model_dump_json()` and validates via `model_validate_json()` round-trip.
6. **And** unit tests verify: all required fields present, SHA-256 hash correctness, data minimization (no denied fields), and round-trip serialization.

## Tasks / Subtasks

- [x] Task 1: Define CaseFile triage domain model and policy-stamp envelope (AC: 1, 2, 5)
  - [x] Implement `CaseFileTriageV1` model(s) in `src/aiops_triage_pipeline/models/case_file.py` with immutable Pydantic models (`frozen=True`).
  - [x] Include fields for evidence snapshot, topology context, gate inputs, action decisions, policy versions, and `triage_hash`.
  - [x] Encode `policy_versions` explicitly: `rulebook_version`, `peak_policy_version`, `prometheus_metrics_contract_version`, `exposure_denylist_version`, `diagnosis_policy_version`.
  - [x] Ensure schema version field and UTC-aware triage timestamp are present for audit replay.

- [x] Task 2: Build deterministic serialization + hashing helpers (AC: 2, 5)
  - [x] Implement `serialize_casefile_triage(...)` and `compute_sha256_hex(...)` in `src/aiops_triage_pipeline/storage/casefile_io.py`.
  - [x] Serialize using Pydantic `.model_dump_json()` and hash the exact serialized JSON bytes.
  - [x] Implement `model_validate_json()` round-trip helper to guarantee re-validation on read/deserialize.
  - [x] Keep helpers pure and side-effect free (no object storage writes in Story 4.1).

- [x] Task 3: Enforce data minimization + denylist before final artifact assembly (AC: 3, 4)
  - [x] Reuse shared `apply_denylist(...)` from `src/aiops_triage_pipeline/denylist/enforcement.py`; do not implement any local denylist logic.
  - [x] Apply denylist to human-visible/sensitive fields entering triage artifact payload.
  - [x] Guarantee no credentials/secrets/PII fields are carried into final CaseFile triage model.

- [x] Task 4: Implement stage assembly orchestration for triage artifact creation (AC: 1, 2, 5)
  - [x] Implement `assemble_casefile_triage_stage(...)` in `src/aiops_triage_pipeline/pipeline/stages/casefile.py`.
  - [x] Inputs should include Stage 1/2/3 outputs plus GateInput/ActionDecision results and loaded policy models.
  - [x] Derive stable `case_id`/scope linkage and include routing/topology context required for audit traceability.
  - [x] Produce immutable `CaseFileTriageV1` payload ready for Story 4.2 persistence.

- [x] Task 5: Export new models/helpers through package boundaries (AC: 1, 5)
  - [x] Update `src/aiops_triage_pipeline/models/__init__.py` exports for new CaseFile model types.
  - [x] Update `src/aiops_triage_pipeline/storage/__init__.py` exports for serialization/hash helpers.
  - [x] Keep import boundaries aligned with architecture: `pipeline/stages` may consume `models`, `contracts`, `storage`, `denylist`, not vice versa.

- [x] Task 6: Add focused unit tests for Story 4.1 invariants (AC: 6)
  - [x] Add `tests/unit/storage/test_casefile_io.py`: deterministic JSON bytes and SHA-256 correctness for stable fixtures.
  - [x] Add `tests/unit/pipeline/stages/test_casefile.py`: assembled payload field completeness and denylist enforcement.
  - [x] Add regression test(s) that `model_validate_json(model_dump_json())` round-trip returns equivalent model data.
  - [x] Add negative tests: denied-field removal, malformed JSON deserialization failure path, and missing policy version fields.

- [x] Task 7: Quality gates
  - [x] `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py`
  - [x] `uv run pytest -q tests/unit/contracts/test_frozen_models.py`
  - [x] `uv run pytest -q`
  - [x] `uv run ruff check`

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Hashing updated to use a canonical triage payload basis plus strict `validate_casefile_triage_json()` hash verification; stored `triage_hash` is now checked against deterministic canonical bytes. [src/aiops_triage_pipeline/storage/casefile_io.py]
- [x] [AI-Review][HIGH] Denylist enforcement now removes denied string values found inside lists during recursive sanitization. [src/aiops_triage_pipeline/pipeline/stages/casefile.py]
- [x] [AI-Review][MEDIUM] `CaseFileTriageV1` now requires `triage_hash` to be a non-empty 64-char lowercase SHA-256 hex string. [src/aiops_triage_pipeline/models/case_file.py]
- [x] [AI-Review][MEDIUM] Unit tests now assert assembled hash correctness via `compute_casefile_triage_hash(...)` and `has_valid_casefile_triage_hash(...)`. [tests/unit/pipeline/stages/test_casefile.py]
- [x] [AI-Review][MEDIUM] Unit tests now cover denylist redaction for sensitive values inside list elements. [tests/unit/pipeline/stages/test_casefile.py]
- [x] [AI-Review][MEDIUM] Dev Agent Record File List updated to include all currently changed files relevant to this review pass.

## Dev Notes

### Developer Context Section

- Artifact discovery context used:
  - `epics_content`: `artifact/planning-artifacts/epics.md` (Epic 4 + Story 4.1 through 4.7)
  - `architecture_content`: `artifact/planning-artifacts/architecture.md`
  - `prd_content` (selective): `functional-requirements.md`, `non-functional-requirements.md`, `event-driven-aiops-platform-specific-requirements.md`, `domain-specific-requirements.md`, `success-criteria.md`
  - `project_context`: `artifact/project-context.md`
  - `ux_content`: not found
- Story sequencing context:
  - This is the first story in Epic 4; there is no previous Epic 4 story file for prior-story intelligence.
  - Downstream Epic 4 stories (4.2-4.7) depend on Story 4.1 outputs, especially the triage payload shape and `triage_hash`.
- Current implementation baseline in repository:
  - `src/aiops_triage_pipeline/models/case_file.py` is currently empty.
  - `src/aiops_triage_pipeline/storage/casefile_io.py` is currently empty.
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py` is currently empty.
  - Existing contracts and upstream stage outputs already exist and should be reused (`GateInputV1`, `ActionDecisionV1`, `EvidenceStageOutput`, `PeakStageOutput`, `TopologyStageOutput`).

### Technical Requirements

- Implement a typed, immutable triage-stage model that contains:
  - Evidence snapshot data needed for replay/audit.
  - Gating inputs (`GateInputV1`) and resulting action decision(s) (`ActionDecisionV1`).
  - Topology/routing context needed for traceability.
  - Explicit policy version stamp object with required 5 version fields.
  - SHA-256 hash field derived from serialized JSON bytes.
- Serialization and validation rules:
  - Serialize using Pydantic `.model_dump_json()` only (no custom ad-hoc JSON serialization path).
  - Re-validate using `model_validate_json()` from serialized content before returning/persisting payload.
  - Hash must be computed from the exact serialized bytes that are later written to storage.
- Data minimization and exposure control:
  - Strip/redact denied fields using shared `apply_denylist(...)`.
  - Never include credentials, tokens, connection strings, keytab paths, or equivalent secret-bearing fields in `triage.json`.
  - Preserve functional fields required by contracts and audits after denylist application.
- Determinism and audit-readiness:
  - Hash calculation and serialized output must be deterministic for identical logical input.
  - Include UTC-aware timestamp fields and stable identifiers (`case_id`, scope identity) to support NFR-T1 replay and NFR-T6 audits.
- Story boundary:
  - Story 4.1 produces assembled+validated triage artifact and hash; storage write ordering/invariant enforcement with object storage is Story 4.2.

### Architecture Compliance

- Preserve core architecture decisions relevant to FR17/FR20:
  - CaseFile stage files follow `cases/{case_id}/{stage}.json` naming convention (Story 4.1 focuses `triage.json` model/bytes).
  - CaseFile JSON is produced through Pydantic model serialization and validated on deserialize boundary.
  - SHA-256 is mandatory tamper-evidence metadata.
- Respect package boundaries:
  - `models/` defines domain models only.
  - `storage/` holds serialization/hash I/O helpers.
  - `pipeline/stages/casefile.py` orchestrates stage assembly from prior stage outputs.
  - `denylist/` remains single-source of enforcement logic.
- Do not alter behavior in completed earlier stories (regression-sensitive surfaces):
  - Stage 1 evidence UNKNOWN propagation semantics.
  - Stage 2 peak/sustained outputs.
  - Stage 3 topology/routing resolution behavior.
  - Stage 6 gate-input assembly behavior in current implementation.
- Align to architecture NFRs carried into this story:
  - NFR-S5 denylist coverage.
  - NFR-T6 audit-trail completeness fields in CaseFile.
  - NFR-T1 replayability through policy version stamping.

### Library / Framework Requirements

- Python runtime: `>=3.13` (repo baseline from `pyproject.toml`).
- Pydantic:
  - Use existing pinned `pydantic==2.12.5`.
  - Use `BaseModel(..., frozen=True)` for contract-like casefile models where applicable.
  - Use `.model_dump_json()` for serialization and `.model_validate_json()` for round-trip validation.
- Hashing:
  - Use stdlib `hashlib.sha256` on encoded JSON bytes.
  - Store digest as lowercase hex string for consistency across tests/logging.
- Denylist:
  - Use existing `DenylistV1` loader + `apply_denylist(...)` only.
  - No alternate regex engines or secondary denylist functions.
- Storage client note:
  - `boto3~=1.42` is already pinned for S3/MinIO client usage; Story 4.1 does not yet perform object PUT calls (implemented in Story 4.2).

### Project Structure Notes

- Primary implementation files:
  - `src/aiops_triage_pipeline/models/case_file.py` (new model definitions; currently empty)
  - `src/aiops_triage_pipeline/storage/casefile_io.py` (serialization/hash helpers; currently empty)
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py` (assembly orchestration; currently empty)
- Likely supporting updates:
  - `src/aiops_triage_pipeline/models/__init__.py` (export new casefile model symbols)
  - `src/aiops_triage_pipeline/storage/__init__.py` (export helper functions/types)
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py` (export casefile stage assembler if stage API is exposed)
- Primary tests to add:
  - `tests/unit/storage/test_casefile_io.py`
  - `tests/unit/pipeline/stages/test_casefile.py`
- Keep cross-package boundaries strict:
  - No direct imports from `pipeline/` into `config/` or `contracts/`.
  - No duplicate data model definitions in stage modules.
  - No Story 4.2 object-storage write logic in Story 4.1 files.

### Testing Requirements

- Unit coverage required for AC closure:
  - Triage model contains all required top-level and nested fields (FR17).
  - Policy version stamps are present and correctly mapped.
  - SHA-256 output is deterministic and matches expected bytes for fixed fixture payload.
  - Denylist removes denied field names and denied-value patterns.
  - Pydantic round-trip with `model_dump_json()` / `model_validate_json()` preserves semantics.
- Negative-path coverage:
  - Invalid/missing policy stamp fields fail validation.
  - Invalid JSON payload fails `model_validate_json`.
  - Attempted injection of denied fields does not survive final assembled payload.
- Regression coverage:
  - No mutation of existing `GateInputV1`, `ActionDecisionV1`, `EvidenceStageOutput`, `TopologyStageOutput` behavior due to casefile additions.
  - Existing contract immutability tests remain green.
- Suggested command sequence:
  - `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py`
  - `uv run pytest -q tests/unit/contracts/test_frozen_models.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Latest Tech Information

Verification date: **March 4, 2026**.

- Pydantic:
  - PyPI shows latest stable `pydantic` as `2.12.5`; repository pin already matches.
  - Current docs continue to recommend `.model_dump_json()` / `.model_validate_json()` for JSON boundary workflows; this aligns directly with Story 4.1 AC.
- boto3 / S3:
  - PyPI shows latest stable `boto3` in `1.42.x`; repository range `boto3~=1.42` is current and compatible.
  - AWS `put_object` docs document `IfNoneMatch="*"` write-if-absent semantics and conflict behavior (`412`/`409`) relevant to Story 4.2 write-once enforcement.
  - AWS docs expose checksum headers/options (`ChecksumSHA256`, etc.), which can be leveraged in Story 4.2+ to cross-check stored object integrity with local `triage_hash`.
- Python hashing:
  - Python stdlib docs for `hashlib.sha256()` confirm stable digest APIs (`digest`, `hexdigest`) suitable for deterministic triage tamper-evidence hashing.

Inference from sources:
- No upgrade/migration work is required in Story 4.1 for these libraries; focus remains on correct model assembly, serialization boundary validation, and deterministic hashing.

### Project Context Reference

Critical rules applied from `artifact/project-context.md`:

- Keep models immutable and boundary-validated (Pydantic frozen models + JSON re-validation).
- Do not fork cross-cutting implementations:
  - reuse `apply_denylist(...)`
  - reuse shared logging/health/event primitives when needed
- Preserve UNKNOWN semantics and deterministic policy behavior (no implicit defaults that inflate confidence/actions).
- Maintain safe integration posture:
  - no unintended outbound LIVE behavior in development paths
  - avoid secret leakage in logs/artifacts
- Follow repo quality gates for risk-sensitive changes (contracts/gating/denylist/degraded-mode adjacent code requires targeted tests).

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 4.1: CaseFile Triage Stage Assembly`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 4: Durable Triage & Reliable Event Publishing`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR17-FR21, FR60-FR61)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-S5, NFR-T1, NFR-T6)]
- [Source: `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md` (CaseFile lifecycle, stage flow)]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` (data minimization, hash integrity, policy governance)]
- [Source: `artifact/planning-artifacts/prd/success-criteria.md` (Invariant A/B2 and audit readiness outcomes)]
- [Source: `artifact/planning-artifacts/architecture.md` (data architecture 1C/3D, denylist 2B, package mapping)]
- [Source: `artifact/project-context.md`]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py`]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py`]
- [Source: `src/aiops_triage_pipeline/contracts/triage_excerpt.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py`]
- [Source: `src/aiops_triage_pipeline/denylist/enforcement.py`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `config/policies/peak-policy-v1.yaml`]
- [Source: `config/policies/prometheus-metrics-contract-v1.yaml`]
- [Source: `config/denylist.yaml`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://docs.pydantic.dev/latest/concepts/models/`]
- [Source: `https://pypi.org/project/boto3/`]
- [Source: `https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html`]
- [Source: `https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-configure.html`]
- [Source: `https://docs.python.org/3/library/hashlib.html`]

### Story Completion Status

- Story context generation complete.
- Story file: `artifact/implementation-artifacts/4-1-casefile-triage-stage-assembly.md`.
- Target status: `ready-for-dev`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created**.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`.
- Story selected from `artifact/implementation-artifacts/sprint-status.yaml` as first backlog item in order: `4-1-casefile-triage-stage-assembly`.
- Epic/story context loaded from planning artifacts and architecture; repository codebase scanned for current implementation baseline and affected files.
- Latest-technology verification completed on March 4, 2026 using official docs (Pydantic, boto3/AWS S3, Python stdlib).
- Implemented casefile domain models in `src/aiops_triage_pipeline/models/case_file.py` with frozen Pydantic models, explicit policy version envelope, topology/evidence snapshots, and hash validation.
- Implemented pure helpers in `src/aiops_triage_pipeline/storage/casefile_io.py`: `serialize_casefile_triage`, `compute_sha256_hex`, `validate_casefile_triage_json`.
- Implemented casefile stage assembly in `src/aiops_triage_pipeline/pipeline/stages/casefile.py`, including stable case ID derivation, scope-aware topology/evidence stitching, recursive denylist sanitization using shared `apply_denylist`, and model round-trip validation.
- Added exports in `src/aiops_triage_pipeline/models/__init__.py`, `src/aiops_triage_pipeline/storage/__init__.py`, and `src/aiops_triage_pipeline/pipeline/stages/__init__.py`.
- Added tests:
  - `tests/unit/storage/test_casefile_io.py`
  - `tests/unit/pipeline/stages/test_casefile.py`
- Code review remediation pass applied (March 5, 2026):
  - canonical triage hash computation helper + strict hash verification at JSON validation boundary
  - non-empty `triage_hash` model enforcement
  - denylist recursion hardened for sensitive list-element values
  - stronger unit assertions for hash correctness and list redaction coverage
- Quality gates executed successfully:
  - `uv run pytest -q tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py` (11 passed)
  - `uv run pytest -q tests/unit/contracts/test_frozen_models.py` (48 passed)
  - `uv run pytest -q` (317 passed)
  - `uv run ruff check` (all checks passed)

### Completion Notes List

- Created comprehensive Story 4.1 implementation guide with concrete tasks, file targets, and acceptance-criteria traceability.
- Added guardrails preventing common implementation failures:
  - ad-hoc serialization/hashing
  - denylist bypasses
  - missing policy stamp fields
  - weak audit/replay coverage
- Documented explicit boundaries between Story 4.1 (assemble/validate/hash) and Story 4.2 (write-once object storage persistence).
- Implemented and validated CaseFile triage assembly end-to-end against all acceptance criteria:
  - AC1: triage payload now includes evidence snapshot, topology/routing context, GateInput.v1, ActionDecision.v1, and explicit policy versions.
  - AC2: SHA-256 digest generated from serialized bytes and stamped into payload.
  - AC3/AC4: denylist sanitization removes denied names/pattern-matched sensitive values before final model validation.
  - AC5: serialization uses `.model_dump_json()` and deserialize boundary enforces `.model_validate_json()`.
  - AC6: focused unit tests cover deterministic bytes/hash, round-trip, denied field stripping, malformed JSON, and required policy stamp validation.

### File List

- `src/aiops_triage_pipeline/models/case_file.py`
- `src/aiops_triage_pipeline/storage/casefile_io.py`
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- `src/aiops_triage_pipeline/models/__init__.py`
- `src/aiops_triage_pipeline/storage/__init__.py`
- `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- `tests/unit/storage/test_casefile_io.py`
- `tests/unit/pipeline/stages/test_casefile.py`
- `artifact/implementation-artifacts/4-1-casefile-triage-stage-assembly.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `README.md`
- `docs/architecture.md`
- `docs/contracts.md`
- `docs/local-development.md`
- `artifact/implementation-artifacts/4-2-write-once-casefile-to-object-storage-invariant-a.md`
- `artifact/implementation-artifacts/epic-3-retro-2026-03-04.md`

### Change Log

- 2026-03-05: Implemented Story 4.1 CaseFile triage-stage models, assembly, serialization/hash helpers, exports, and focused unit coverage; all quality gates passing; status moved to `review`.
- 2026-03-05: Addressed AI code-review findings by hardening canonical hash validation, enforcing non-empty `triage_hash`, extending denylist sanitization to list values, and strengthening unit tests.
