# Story 3.4: Persist Diagnosis Artifact with Fallback Guarantees

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/platform engineer,
I want diagnosis persistence to be resilient to model/provider failures,
so that every case produces an observable, auditable diagnosis outcome.

**Implements:** FR42, FR43

## Acceptance Criteria

1. **Given** LLM invocation succeeds
   **When** diagnosis write executes
   **Then** `diagnosis.json` is stored in object storage with hash-chain linkage to `triage.json`
   **And** success metrics/logs include case correlation context.

2. **Given** LLM invocation times out, fails, or returns invalid schema
   **When** cold-path fallback executes
   **Then** a deterministic fallback diagnosis report is generated and persisted
   **And** absence of primary diagnosis is explicit and observable.

## Tasks / Subtasks

- [x] Task 1: Guarantee hash-chain-safe diagnosis persistence on success path (AC: 1)
  - [x] Keep diagnosis persistence through `CaseFileDiagnosisV1` and write-once storage helpers (`compute_casefile_diagnosis_hash`, `persist_casefile_diagnosis_write_once`) instead of ad-hoc object writes.
  - [x] Ensure `triage_hash` used for diagnosis linkage is the validated persisted triage hash from context retrieval, not a derived surrogate.
  - [x] Validate success-path write behavior remains fail-loud for non-LLM persistence/invariant violations (do not remap storage invariant failures to LLM fallback reasons).

- [x] Task 2: Enforce deterministic fallback guarantees across all LLM failure classes (AC: 2)
  - [x] Ensure timeout, transport unavailability, schema-invalid output, and generic invocation exceptions all produce deterministic fallback reports via the fallback builder path.
  - [x] Ensure each fallback report persists to `diagnosis.json` with valid `triage_hash` and computed `diagnosis_hash` so audit chain remains complete.
  - [x] Keep fallback outputs schema-valid (`DiagnosisReportV1`) and explicit using stable reason codes (`LLM_TIMEOUT`, `LLM_UNAVAILABLE`, `LLM_SCHEMA_INVALID`, `LLM_ERROR`).

- [x] Task 3: Strengthen observability for success vs fallback outcomes (AC: 1, 2)
  - [x] Confirm cold-path logs include `case_id` and explicit event names for success persistence (`cold_path_diagnosis_json_written`) and fallback persistence (`cold_path_fallback_diagnosis_json_written`).
  - [x] Confirm metrics capture invocation result split (`success` vs `fallback`), fallback reason code counters, timeout counters, and latency with no double-recording per invocation.
  - [x] Verify HealthRegistry transitions for `llm` are explicit (`HEALTHY` on success; `DEGRADED` with reason on fallback paths).

- [x] Task 4: Preserve cold-path consumer resilience and sequencing contracts (AC: 1, 2)
  - [x] Keep sequential consume/process semantics in cold-path loop (D6) and avoid introducing background concurrency that could reorder diagnosis persistence.
  - [x] Preserve per-message error handling in `_cold_path_process_event_async()` so diagnosis invocation failures are logged and skipped without crashing the consumer loop.
  - [x] Keep sync wrapper constraints (`_cold_path_process_event`) intact: no `asyncio.run()` inside active event loop paths.

- [x] Task 5: Expand regression coverage for fallback-persistence guarantees (AC: 1, 2)
  - [x] Extend `tests/unit/diagnosis/test_graph.py` to assert each fallback class writes `diagnosis.json` with hash-chain integrity and stable reason code semantics.
  - [x] Add/adjust tests for success-path persistence failure behavior to ensure fail-loud invariant handling remains intact.
  - [x] Add/adjust integration coverage validating persisted diagnosis stage can be reloaded and hash-validated from object storage using stage helpers.

- [x] Task 6: Documentation and operator guidance updates
  - [x] Update runtime docs to explicitly state fallback persistence guarantee semantics and observability signals for diagnosis failures.
  - [x] Ensure local-development guidance remains accurate for LOG/MOCK/LIVE behavior while still guaranteeing persisted diagnosis stage outcomes.

## Dev Notes

### Developer Context Section

- Story 3.3 already wired all-case invocation and integrated diagnosis persistence/fallback paths in `diagnosis/graph.py`; Story 3.4 hardens and validates those guarantees against FR42/FR43 and NFR-R8.
- Existing architecture already provides write-once stage persistence and hash-chain helpers under `storage/casefile_io.py` and `pipeline/stages/casefile.py`; this story should reuse them rather than introducing alternate persistence paths.
- Keep cold-path contracts clear:
  - LLM/provider failures are degradable and produce deterministic fallback diagnosis output.
  - Storage/invariant failures after successful LLM output are not degradable; they must fail loud for operational visibility.
- Preserve advisory nature of cold-path diagnosis: this story does not alter deterministic gate authority in hot-path.

### Technical Requirements

- FR42: deterministic fallback diagnosis report on timeout/unavailability/schema-invalid invocation outcomes.
- FR43: diagnosis stage persisted as `diagnosis.json` with SHA-256 hash chain linkage to `triage.json`.
- NFR-R8: LLM failure must be explicit and observable, never silent.
- NFR-P4: 60-second timeout bound remains authoritative.
- NFR-S2/NFR-S1: denylist and secret-safe structured logging remain enforced on LLM input/output paths.

### Architecture Compliance

- D6 (Cold-path consumer architecture):
  - sequential processing, no eligibility gating,
  - commit-on-shutdown semantics,
  - per-message resilience.
- D9 (Evidence summary stability): story consumes deterministic summary and must not weaken byte-stability assumptions.
- Stage persistence and hash validation alignment:
  - `CaseFileDiagnosisV1` and `compute_casefile_diagnosis_hash(...)`
  - `persist_casefile_diagnosis_write_once(...)`
  - triage dependency validation from context retrieval and stage helpers.
- Composition root remains `__main__.py`; do not introduce module-level singleton orchestration for diagnosis runtime dependencies.

### Library / Framework Requirements

- Use repository-pinned stack and keep current architecture pins unless separately approved:
  - `langgraph==1.0.9` (project pin)
  - `pydantic==2.12.5`
  - `pydantic-settings~=2.13.1`
  - `confluent-kafka==2.13.0` (project pin)
  - `boto3~=1.42`
  - `structlog==25.5.0`
  - `pytest==9.0.2`
- Keep schema validation at boundaries with Pydantic v2 `model_validate(...)` / `model_validate_json(...)`.
- Do not introduce new diagnosis orchestration libraries or alternative storage abstractions.

### File Structure Requirements

Primary implementation focus:
- `src/aiops_triage_pipeline/diagnosis/graph.py`
- `src/aiops_triage_pipeline/diagnosis/fallback.py`
- `src/aiops_triage_pipeline/diagnosis/context_retrieval.py`
- `src/aiops_triage_pipeline/storage/casefile_io.py`
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- `src/aiops_triage_pipeline/__main__.py`

Primary test focus:
- `tests/unit/diagnosis/test_graph.py`
- `tests/unit/test_main.py`
- `tests/integration/cold_path/test_context_reconstruction.py`
- `tests/integration/test_casefile_write.py` and/or `tests/integration/test_casefile_lifecycle.py` for diagnosis stage behavior

Documentation:
- `docs/runtime-modes.md`
- `docs/local-development.md`

### Testing Requirements

Unit tests must cover:
- Each LLM failure class maps to deterministic fallback reason code and persists `diagnosis.json`.
- Fallback report retains validated `triage_hash` and remains `DiagnosisReportV1`-valid.
- Success path writes diagnosis stage with correct hash chain metadata.
- Success-path persistence failures raise (fail loud) and are not remapped as fallback.
- Health + metrics side effects occur once per invocation result class.

Integration/regression expectations:
- Cold-path diagnosis persistence remains compatible with object-store write-once semantics and revalidation.
- Casefile stage reading correctly reports explicit absence when diagnosis stage is not present.
- Full suite quality gate remains:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - zero skipped tests required.

### Previous Story Intelligence (Story 3.3)

- Story 3.3 established all-case diagnosis invocation and already repaired two critical correctness issues:
  - runtime async boundary: no nested `asyncio.run()` in active event loop path,
  - hash-chain input correctness: use persisted `triage_hash` from context retrieval, not synthetic hash.
- `run_cold_path_diagnosis(...)` already centralizes fallback mapping, persistence writes, and observability emission; Story 3.4 should extend and harden this path instead of duplicating logic elsewhere.
- Existing unit coverage in `tests/unit/diagnosis/test_graph.py` includes fallback branches and persistence checks; this story should close remaining edge cases and ensure contract-level guarantees are explicit.

### Git Intelligence Summary

Recent commit patterns show:
- cold-path work is localized to `__main__.py`, `diagnosis/*`, docs, and focused tests;
- story workflow updates include story artifact + sprint status in the same change;
- remediation-first commits corrected runtime safety and hash-chain linkage rather than broad refactors.

Actionable guidance:
- keep Story 3.4 implementation as incremental hardening in existing cold-path modules,
- avoid package churn or new architectural layers.

### Latest Tech Information

External verification date: 2026-03-23.

- `langgraph` latest PyPI release: `1.1.3` (2026-03-18); project pin remains `1.0.9`.
- `pydantic` latest PyPI release: `2.12.5` (2025-11-26), matching project pin.
- `httpx` latest stable: `0.28.1` (2024-12-06), compatible with current integration surface.
- `boto3` latest PyPI release: `1.42.73` (2026-03-20); project uses compatible `~1.42` range.
- `confluent-kafka` latest PyPI release: `2.13.2` (2026-03-02); project pin remains `2.13.0`.

Guidance for this story:
- focus on behavioral guarantees and invariants, not dependency upgrades.

### Project Context Reference

Applied `archive/project-context.md` rules:
- preserve hot/cold separation and deterministic guardrail authority;
- use shared denylist enforcement and structured logging primitives;
- keep contract-first validation and explicit failure taxonomy;
- never silence critical invariant failures;
- keep changes requirement-traceable and accompanied by targeted tests.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 3 / Story 3.4]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR42, FR43]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-P4, NFR-R8, NFR-S1, NFR-S2]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D6, D9]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/planning-artifacts/prd/event-driven-pipeline-specific-requirements.md`]
- [Source: `archive/project-context.md`]
- [Source: `artifact/implementation-artifacts/3-3-invoke-llm-for-all-cases-with-enriched-prompt-and-schema-validation.md`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py`]
- [Source: `src/aiops_triage_pipeline/diagnosis/fallback.py`]
- [Source: `src/aiops_triage_pipeline/diagnosis/context_retrieval.py`]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/casefile.py`]
- [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py`]
- [Source: `src/aiops_triage_pipeline/models/case_file.py`]
- [Source: `tests/unit/diagnosis/test_graph.py`]
- [Source: `https://pypi.org/project/langgraph/`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://pypi.org/project/httpx/`]
- [Source: `https://pypi.org/project/boto3/`]
- [Source: `https://pypi.org/project/confluent-kafka/`]

## Dev Agent Record

### Agent Model Used

gpt-5-codex

### Debug Log References

- create-story workflow execution for explicit story key `3-4-persist-diagnosis-artifact-with-fallback-guarantees`
- source analysis: sprint status, epics/PRD/architecture/project-context artifacts, previous story 3.3, current cold-path diagnosis/persistence modules, and recent git history
- latest-tech verification: PyPI project metadata for `langgraph`, `pydantic`, `httpx`, `boto3`, `confluent-kafka`
- dev-story implementation updates: `diagnosis/graph.py` fallback gap marker + persistence observability fields (`diagnosis_hash`, `primary_diagnosis_absent`)
- regression command evidence:
  - `uv run ruff check`
  - `uv run pytest -q tests/atdd/test_story_3_4_persist_diagnosis_artifact_with_fallback_guarantees_red_phase.py`
  - `uv run pytest -q tests/unit/diagnosis/test_graph.py`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q tests/integration/test_casefile_write.py -m integration -rs`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (1050 passed, 0 skipped)

### Completion Notes List

- Implemented explicit fallback absence semantics via stable `PRIMARY_DIAGNOSIS_ABSENT` gap marker while preserving deterministic reason-code mapping.
- Enriched success and fallback persistence observability with hash-chain correlation fields (`triage_hash`, `diagnosis_hash`) and fallback absence flag (`primary_diagnosis_absent=true`).
- Preserved fail-loud behavior for non-LLM persistence/invariant failures on success path and kept existing D6 cold-path sequencing/error-handling contracts.
- Added integration regression coverage to persist/load diagnosis stage through stage helpers and revalidate diagnosis hash.
- Updated runtime/local docs with fallback persistence guarantees and event-level observability guidance.

### File List

- `artifact/implementation-artifacts/3-4-persist-diagnosis-artifact-with-fallback-guarantees.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `src/aiops_triage_pipeline/diagnosis/graph.py`
- `tests/unit/diagnosis/test_graph.py`
- `tests/integration/test_casefile_write.py`
- `tests/atdd/test_story_3_4_persist_diagnosis_artifact_with_fallback_guarantees_red_phase.py`
- `tests/atdd/fixtures/story_3_4_test_data.py`
- `docs/runtime-modes.md`
- `docs/local-development.md`

### Change Log

- 2026-03-23: Completed Story 3.4 implementation and validations; hardened fallback persistence observability, expanded regression coverage, and documented fallback guarantees.
- 2026-03-23: Senior developer adversarial review completed; resolved all Critical/High/Medium/Low findings and revalidated targeted Story 3.4 tests.

## Senior Developer Review (AI)

- Reviewer: Sas (AI)
- Date: 2026-03-23
- Outcome: Approved

### Findings and Resolutions

1. `[MEDIUM]` Fallback metrics and result classification were emitted before fallback `diagnosis.json` persistence succeeded, which could misclassify hard persistence failures as successful fallback outcomes.
   Resolution: updated `run_cold_path_diagnosis(...)` to persist fallback first, then record fallback metrics/log result classification.
2. `[MEDIUM]` Story Dev Agent Record `File List` omitted `tests/atdd/fixtures/story_3_4_test_data.py` used by story ATDD coverage.
   Resolution: added the missing fixture path to `File List` for traceability.
3. `[LOW]` ATDD mocks that patched `asyncio.wait_for` raised directly without closing the passed awaitable, causing unawaited-coroutine warnings.
   Resolution: added awaitable-closing async side-effect helpers and updated ATDD patches to use them.
4. `[LOW]` Unit fallback tests did not consistently assert explicit `PRIMARY_DIAGNOSIS_ABSENT` semantics across all fallback classes.
   Resolution: expanded assertions in fallback unit tests (timeout, unavailable, generic error, schema validation round-trip).

## Story Completion Status

- Story status: `done`
- Completion note: All Story 3.4 tasks completed, acceptance criteria validated, and adversarial review findings resolved with targeted regression checks.
