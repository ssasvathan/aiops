# Story 3.2: Reconstruct Case Context and Build Deterministic Evidence Summary

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want cold-path processing to reconstruct full context from persisted artifacts,
So that diagnosis input reflects authoritative triage evidence.

**Implements:** FR37, FR38

## Acceptance Criteria

1. **Given** a `CaseHeaderEventV1` is consumed
   **When** cold-path retrieval executes
   **Then** triage artifact context is read from object storage and reconstructed into the diagnosis input model (`TriageExcerptV1`)
   **And** reconstruction fails loudly (raises, logs, skips case) on missing required artifact state.

2. **Given** triage excerpt data is available
   **When** evidence summary rendering runs
   **Then** output text is deterministic and byte-stable for identical inputs
   **And** evidence statuses (`PRESENT`, `UNKNOWN`, `ABSENT`, `STALE`) are explicitly represented in output sections.

## Tasks / Subtasks

- [x] Task 1: Implement case context reconstruction from S3 triage.json (AC: 1)
  - [x] Create `src/aiops_triage_pipeline/diagnosis/context_retrieval.py` with a `retrieve_case_context()` function that accepts `case_id` and `object_store_client`, reads `cases/{case_id}/triage.json` via `read_casefile_stage_json_or_none`, and reconstructs `TriageExcerptV1` from `CaseFileTriageV1`.
  - [x] Fail loudly: if `triage.json` is missing (returns `None`), raise a clearly typed exception (e.g., `CaseTriage NotFoundError` or use existing `ObjectNotFoundError`) — no silent skip, no default reconstruction.
  - [x] Reconstruct `TriageExcerptV1` from `CaseFileTriageV1` fields: map `gate_input.env`, `gate_input.cluster_id`, `gate_input.stream_id`, `gate_input.topic`, `gate_input.anomaly_family`, `topology_context.topic_role`, `topology_context.criticality_tier`, `topology_context.routing.routing_key`, `gate_input.sustained`, `evidence_snapshot.peak_context`, `evidence_snapshot.evidence_status_map`, `gate_input.findings`, and `triage_timestamp`.
  - [x] Validate hash integrity using `has_valid_casefile_triage_hash()` before using the reconstructed casefile; raise on hash mismatch.
  - [x] Log `case_context_retrieved` structured event with `case_id`, `triage_hash`, `object_path`.

- [x] Task 2: Implement deterministic evidence summary builder (AC: 2)
  - [x] Create `src/aiops_triage_pipeline/diagnosis/evidence_summary.py` implementing D9: pure function `build_evidence_summary(triage_excerpt: TriageExcerptV1) -> str`.
  - [x] Guarantee byte-identical output for identical inputs: sort all collections before rendering (evidence_status_map keys, findings by finding_id, reason_codes). No timestamps, no random UUIDs in output.
  - [x] Output sections (fixed order): (1) Case Context, (2) Evidence Status (PRESENT / UNKNOWN / ABSENT / STALE), (3) Anomaly Findings (all `Finding` fields: finding_id, name, severity, is_anomalous, is_primary, evidence_required, reason_codes), (4) Temporal Context (sustained flag, peak flag).
  - [x] PRESENT section: list evidence keys with status only. UNKNOWN section: list keys and their status (explicitly say "UNKNOWN — missing or unavailable metric"). ABSENT and STALE sections: list with explicit label.
  - [x] Add unit tests: `tests/unit/diagnosis/test_evidence_summary.py` covering byte-stability assertion (same input → same output across two calls), section presence, all four EvidenceStatus values in the correct sections.

- [x] Task 3: Wire reconstruction and summary into the cold-path processor boundary (AC: 1, 2)
  - [x] Update `_cold_path_process_event()` in `src/aiops_triage_pipeline/__main__.py` to: (a) call `retrieve_case_context()`, (b) call `build_evidence_summary()`, (c) pass both `triage_excerpt` and `evidence_summary` forward to the Story 3.3 processor boundary (stub log for now).
  - [x] Wire `object_store_client` dependency into `_cold_path_consumer_loop()` and `_build_cold_path_consumer_adapter()`/`_run_cold_path()` via `build_s3_object_store_client_from_settings(settings)`. Inject through function parameters, NOT module-level singletons.
  - [x] On reconstruction failure (triage.json missing or hash mismatch): log `cold_path_context_retrieval_failed` warning + `exc_info=True`, skip to next message (do not crash the consumer loop).
  - [x] On evidence summary failure: same structured-log + skip pattern.
  - [x] Commit offset only after processing attempt (success or logged failure), per existing loop design.

- [x] Task 4: Add unit and integration coverage (AC: 1, 2)
  - [x] `tests/unit/diagnosis/test_context_retrieval.py`: cover successful reconstruction from a fake `CaseFileTriageV1`, missing triage.json (None return), hash mismatch detection, and correct field mapping from casefile to `TriageExcerptV1`.
  - [x] Update `tests/unit/test_main.py` to assert `_cold_path_process_event()` now invokes context retrieval and summary steps (use fakes/mocks, no real S3).
  - [x] `tests/integration/cold_path/test_context_reconstruction.py`: write `CaseFileTriageV1` to MinIO testcontainer, consume via `retrieve_case_context()`, assert reconstructed `TriageExcerptV1` fields match. Mark with `pytestmark = pytest.mark.integration`.
  - [x] Keep sprint quality gate: zero skipped tests.

- [x] Task 5: Update documentation (AC: 1, 2)
  - [x] Update `docs/runtime-modes.md` cold-path section to describe context retrieval and evidence summary step.
  - [x] Update `docs/local-development.md` if S3 dependency guidance is needed for cold-path local run.

## Dev Notes

### Developer Context Section

- This story adds two new modules to the `diagnosis/` package and wires them into the processor boundary stub left by Story 3.1.
- **Strict scope boundary:** Do NOT implement LLM invocation (Story 3.3), fallback diagnosis logic (Story 3.4), or prompt building. The processor boundary should pass `triage_excerpt` + `evidence_summary` to a stub log call only.
- The processor boundary function `_cold_path_process_event()` in `__main__.py` already exists (Story 3.1 left it as a stub that logs `cold_path_event_received`). This story replaces that stub body with real retrieval + summary, but keeps the same function signature.
- `diagnosis/graph.py` (`run_cold_path_diagnosis()`) already exists and accepts `triage_excerpt: TriageExcerptV1` and `evidence_summary: str` — do NOT call it from this story. Story 3.3 wires that.
- `evidence_summary.py` is specified in D9 and referenced by `diagnosis/graph.py` already. The module does not yet exist — this story creates it.
- `context_retrieval.py` is a new module entirely; no existing code to reuse or collide with.
- Cold-path consumer loop is synchronous (sync `confluent-kafka` poll); `retrieve_case_context()` calls `object_store_client.get_object_bytes()` which is also synchronous — no asyncio needed for retrieval or summary.
- `_cold_path_consumer_loop()` is an `async` function (uses `await registry.update(...)`), so S3 calls inside sync helper functions called from it are fine.

### Technical Requirements

- Functional: FR37 (S3 context retrieval + TriageExcerptV1 reconstruction), FR38 (deterministic evidence summary).
- D9 specification (core-architectural-decisions.md): "Pure function: TriageExcerptV1 → str. Deterministic ordering (sorted keys, fixed section order). No timestamps in output. Conditionally includes sections based on evidence status."
- D6 (cold-path architecture): processing loop step 4 = reconstruct TriageExcerptV1, step 5 = build evidence summary (CR-06). This story implements both.
- Invariant A: `triage.json` is guaranteed to exist in S3 by the hot-path before any `CaseHeaderEventV1` is published. If it's missing, that is a system invariant violation — fail loudly (do not silently continue).
- Hash chain integrity: validate `triage_hash` on read using `has_valid_casefile_triage_hash()` from `storage/casefile_io.py` — do not skip this check.
- Object store access: use `read_casefile_stage_json_or_none()` from `storage/casefile_io.py`; the key pattern is `cases/{case_id}/triage.json` (computed by `build_casefile_triage_object_key()`).

### Architecture Compliance

- `diagnosis/` package boundary: `diagnosis/` imports from `contracts/`, `denylist/` only. The new modules must NOT import from `pipeline/`, `cache/`, `registry/`, or `coordination/`. For `context_retrieval.py`, it needs `storage/` — verify this is permitted: per `project-structure-boundaries.md`, the cold-path uses `diagnosis/` and `storage/`. **Direct import of `storage.casefile_io` from `diagnosis/` is consistent with D6 cold-path design** (the processing loop calls retrieval → summary → LLM → persist).
- `__main__.py` is the composition root: wire `object_store_client` there using `build_s3_object_store_client_from_settings(settings)` and pass it down to `_cold_path_consumer_loop()` → `_cold_path_process_event()`. Do not build it inside the loop.
- No cross-mode import drift: the cold-path must not import from `pipeline/`, `cache/dedupe`, `cache/evidence_window`, `rule_engine/`, `coordination/`, or `outbox/`.
- Package dependency rule from `project-structure-boundaries.md`: `diagnosis/ → contracts/, denylist/ only`. If `context_retrieval.py` needs `storage/casefile_io`, it may need to be placed at `__main__.py` level as a helper (not inside `diagnosis/`), OR the package rules allow storage import for the cold-path assembly path. **Recommended approach**: implement `retrieve_case_context()` as a standalone function in a new file `src/aiops_triage_pipeline/diagnosis/context_retrieval.py` and treat the import of `storage.casefile_io` as an intentional architectural boundary exception for the cold-path assembly. Alternatively, implement it directly in `__main__.py` as a private helper. **Choose the approach consistent with how `diagnosis/graph.py` imports `storage/casefile_io`** — it already does so (line 44-47 of graph.py). Therefore the `diagnosis/` package already imports from `storage/`, making `context_retrieval.py` inside `diagnosis/` fully consistent.
- Sync consumer loop: `retrieve_case_context()` must be synchronous (no `async def`). `build_evidence_summary()` must be a pure sync function.

### Library / Framework Requirements

- Repository-pinned versions (pyproject.toml):
  - `pydantic==2.12.5` — use `model_validate_json()` and `model_dump()` at I/O boundaries.
  - `boto3~=1.42` — used transitively via `storage.client.S3ObjectStoreClient`.
  - `structlog==25.5.0` — all log calls via `get_logger()`.
  - `pytest==9.0.2`, `testcontainers==4.14.1`, `pytest-asyncio==1.3.0`.
- Do NOT add new library dependencies for this story — everything needed is already in the stack.
- `read_casefile_stage_json_or_none` and `has_valid_casefile_triage_hash` are in `storage/casefile_io.py` — import and reuse them, do NOT reimplement deserialization or hashing.

### File Structure Requirements

Primary implementation files (new):
- `src/aiops_triage_pipeline/diagnosis/context_retrieval.py` (new) — `retrieve_case_context()`
- `src/aiops_triage_pipeline/diagnosis/evidence_summary.py` (new) — `build_evidence_summary()`

Modified files:
- `src/aiops_triage_pipeline/__main__.py` — wire `object_store_client` into `_run_cold_path()` / `_cold_path_consumer_loop()`, update `_cold_path_process_event()` to call retrieval + summary.

Primary tests (new):
- `tests/unit/diagnosis/test_context_retrieval.py` (new)
- `tests/unit/diagnosis/test_evidence_summary.py` (new — file referenced in architecture)
- `tests/integration/cold_path/test_context_reconstruction.py` (new)

Modified tests:
- `tests/unit/test_main.py` (modified — update cold-path event processing test)

Documentation:
- `docs/runtime-modes.md` (modified)
- `docs/local-development.md` (modified if needed)

### Testing Requirements

Unit tests must cover:
- `test_context_retrieval.py`:
  - Successful read and reconstruction: given a valid `CaseFileTriageV1` returned by fake object store, `retrieve_case_context()` returns a `TriageExcerptV1` with correct field mapping.
  - Missing triage.json: given `read_casefile_stage_json_or_none` returns `None`, function raises (do not swallow).
  - Hash mismatch: given a casefile whose `triage_hash` does not match computed hash, function raises.
  - Field mapping assertions: `topic_role` comes from `topology_context.topic_role`, `routing_key` from `topology_context.routing.routing_key`, `findings` from `gate_input.findings`, `sustained` from `gate_input.sustained`, `peak` from `evidence_snapshot.peak_context` (if present), `evidence_status_map` from `gate_input.evidence_status_map` or `evidence_snapshot.evidence_status_map`.
- `test_evidence_summary.py`:
  - Byte-stability: `build_evidence_summary(excerpt) == build_evidence_summary(excerpt)` for same input.
  - All four `EvidenceStatus` values appear in their correct labeled sections.
  - All `Finding` fields (finding_id, name, severity, is_anomalous, is_primary, evidence_required, reason_codes) appear in findings section.
  - No timestamps in output.
  - Sorted keys: given two inputs with same data in different dict insertion orders, output is identical.
  - Temporal context section: sustained=True and peak=True appear correctly.
- `test_main.py` update:
  - `_cold_path_process_event()` with injected fake object store returns without error on valid message.
  - On context retrieval failure (fake store returns None), function logs warning and does not raise.

Integration tests must cover:
- `test_context_reconstruction.py`:
  - Write a `CaseFileTriageV1` to MinIO testcontainer using `persist_casefile_triage_write_once()`.
  - Call `retrieve_case_context(case_id=..., object_store_client=...)`.
  - Assert reconstructed `TriageExcerptV1` has correct field values matching the written casefile.
  - Mark with `pytestmark = pytest.mark.integration`.

Regression gates:
- `uv run ruff check`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Zero skipped tests required.

### Previous Story Intelligence (Story 3.1)

Key patterns established in Story 3.1 that apply here:
- Consumer loop in `__main__.py` is the single composition root; new dependencies (object_store_client) must be constructed in `_run_cold_path()` and passed down, not built inside the loop or event handler.
- Processor boundary signature: `_cold_path_process_event(event: CaseHeaderEventV1, logger: structlog.BoundLogger) -> None` — extend this signature to accept `object_store_client` as a parameter.
- On per-message failures: log warning + `exc_info=True` + continue (do not re-raise from `_cold_path_process_event`). The consumer loop already handles this pattern via the outer try/except in `_process_cold_path_message()`.
- `KafkaConsumerAdapterProtocol`, `ConfluentKafkaCaseHeaderConsumer` are in `integrations/kafka_consumer.py` — not modified by this story.
- Health transitions for consumer lifecycle (`kafka_cold_path_connected`, `kafka_cold_path_poll`, `kafka_cold_path_commit`) were added in 3.1 — do NOT duplicate or reset them in this story.
- Code review finding from Story 3.1: integration tests must include `pytestmark = pytest.mark.integration` at module level.
- Code review finding from Story 3.1: avoid dead code / unused helpers — only implement what's needed for this story's scope.
- Post-3.1 test count baseline: 926 unit/ATDD tests passed, 0 skipped. This story adds new tests on top without breaking existing count.

### Latest Tech Information

External verification date: 2026-03-22.

- `boto3~=1.42` (S3 client): `get_object` raises `ClientError` with `NoSuchKey` code when object is not found. `storage/casefile_io.py` already handles this via `ObjectNotFoundError`. No new S3 API usage needed.
- `pydantic==2.12.5`: `model_validate_json()` for deserialization at I/O boundaries; `model_dump(mode="json")` for serialization. `frozen=True` models cannot be mutated — create new instances when transforming.
- `testcontainers==4.14.1`: MinIO testcontainer is already used in integration tests (storage lifecycle tests). Reuse existing `minio_client` fixture pattern from `tests/integration/conftest.py` rather than creating a new one.
- `structlog==25.5.0`: `get_logger("diagnosis.context_retrieval")` pattern consistent with `_logger = get_logger("diagnosis.graph")` in graph.py.

### Project Context Reference

Applied `archive/project-context.md` guidance:
- Contract-first: validate `CaseFileTriageV1` hash before consuming its data; reconstruct `TriageExcerptV1` from typed fields, not raw dicts.
- Hot/cold separation: no imports from hot-path packages (`pipeline/`, `cache/`, `rule_engine/`, `coordination/`).
- Shared logging/health/exception taxonomy: use `get_logger()`, `errors/exceptions.py` types, no parallel frameworks.
- No silent failures on critical paths: missing `triage.json` = loud failure + skip (not silent default). Hash mismatch = loud failure.
- Deterministic guardrails: evidence summary must be byte-stable; no timestamp or random element allowed in output.
- Never collapse UNKNOWN evidence status into anything else — the summary must explicitly represent UNKNOWN as UNKNOWN.
- Reuse `apply_denylist()` if any output crosses a boundary — but evidence summary stays internal (passed to LLM via Story 3.3), so denylist enforcement happens in `run_cold_path_diagnosis()` (already present in graph.py), not here.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 3, Story 3.2, FR37, FR38]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR37, FR38]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D6, D9]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md` — cold-path package boundary, CR-06 mapping]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md` — sync consumer, dependency injection, test patterns]
- [Source: `archive/project-context.md`]
- [Source: `src/aiops_triage_pipeline/__main__.py` — `_cold_path_process_event()` stub, `_run_cold_path()`, `_cold_path_consumer_loop()`]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py` — `run_cold_path_diagnosis()` signature, existing storage import pattern]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py` — `read_casefile_stage_json_or_none()`, `has_valid_casefile_triage_hash()`, `build_casefile_triage_object_key()`]
- [Source: `src/aiops_triage_pipeline/models/case_file.py` — `CaseFileTriageV1`, field layout]
- [Source: `src/aiops_triage_pipeline/contracts/triage_excerpt.py` — `TriageExcerptV1`, all fields]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py` — `Finding` all fields]
- [Source: `src/aiops_triage_pipeline/contracts/enums.py` — `EvidenceStatus` enum values]
- [Source: `artifact/implementation-artifacts/3-1-implement-cold-path-kafka-consumer-runtime-mode.md` — previous story patterns]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Fixed `PeakWindowContext` test data: RED phase tests used `scope=` (non-existent field) and omitted required `classification` field. Updated test fixtures in `test_context_retrieval.py` and `test_context_reconstruction.py` to use `classification="PEAK"`.
- Added `build_s3_object_store_client_from_settings` monkeypatch to existing cold-path unit tests and ATDD tests (`test_main.py`, `test_story_3_1_...py`) that used minimal SimpleNamespace settings without S3 attributes. These tests were previously passing because `_run_cold_path()` didn't build an S3 client before Story 3.2 wiring.
- Import sort: diagnosis imports must be placed after `denylist.loader` and before `health.alerts` alphabetically in `__main__.py`.

### Completion Notes List

- Implemented `retrieve_case_context()` in `diagnosis/context_retrieval.py`: reads `cases/{case_id}/triage.json` via `get_object_bytes`, validates triage_hash chain, maps all required fields to `TriageExcerptV1`. Raises `CaseTriageNotFoundError` (subclass of `InvariantViolation`) on missing triage.json. Raises `InvariantViolation` on hash mismatch.
- Implemented `build_evidence_summary()` in `diagnosis/evidence_summary.py`: pure function, D9-compliant, byte-stable output. Four fixed sections: Case Context, Evidence Status (PRESENT/UNKNOWN/ABSENT/STALE), Anomaly Findings, Temporal Context. All collections sorted before rendering.
- Wired `object_store_client` through `_run_cold_path()` → `_cold_path_consumer_loop()` → `_process_cold_path_message()` → `_cold_path_process_event()` via dependency injection (no singletons).
- `_cold_path_process_event()` updated: calls `retrieve_case_context()` then `build_evidence_summary()`. On failure: logs structured warning + `exc_info=True`, returns (does not raise). Story 3.3 stub log (`cold_path_context_ready`) emitted on success.
- All 1033 tests pass, 0 skipped, ruff clean.

### Senior Developer Review (AI)

**Reviewer:** claude-sonnet-4-6 on 2026-03-22

**Findings and Resolutions:**

| # | Severity | Description | Resolution |
|---|----------|-------------|------------|
| 1 | MEDIUM | Dead `KeyError` catch in `context_retrieval.py` line 61: `S3ObjectStoreClient.get_object_bytes()` raises `ObjectNotFoundError`, never `KeyError`. Catching `KeyError` was dead code copied from `read_casefile_stage_json_or_none()` pattern. | Removed `KeyError` from except clause; now `except ObjectNotFoundError as exc` only. |
| 2 | MEDIUM | Missing test: `cold_path_evidence_summary_failed` log event path untested. Story Task 4 requires both failure paths covered; only `cold_path_context_retrieval_failed` was tested. | Added `test_cold_path_process_event_logs_warning_on_evidence_summary_failure` (3.2-UNIT-205) to `tests/unit/test_main.py`. |
| 3 | LOW | `test_raises_when_object_not_found` used `pytest.raises(Exception)` without asserting specific type `CaseTriageNotFoundError`. | Added `CaseTriageNotFoundError` import to test and specific `isinstance` assertion in `test_context_retrieval.py`. |

**Outcome:** APPROVED — all findings resolved. 1034 tests pass, 0 skipped, ruff clean.

### File List

- `src/aiops_triage_pipeline/diagnosis/context_retrieval.py` (new)
- `src/aiops_triage_pipeline/diagnosis/evidence_summary.py` (new)
- `src/aiops_triage_pipeline/__main__.py` (modified)
- `tests/unit/diagnosis/test_context_retrieval.py` (modified — fixed PeakWindowContext fixture data; review: added CaseTriageNotFoundError type assertion)
- `tests/unit/test_main.py` (modified — added S3 mock + Story 3.2 wiring tests + review: added evidence_summary_failed test)
- `tests/integration/cold_path/test_context_reconstruction.py` (modified — fixed PeakWindowContext fixture data)
- `tests/atdd/test_story_3_1_implement_cold_path_kafka_consumer_runtime_mode_red_phase.py` (modified — added S3 mock)
- `docs/runtime-modes.md` (modified)
- `docs/local-development.md` (modified)

## Story Completion Status

- Story status: `done`
- Completion note: Story 3.2 fully implemented and reviewed. FR37 (S3 context retrieval → TriageExcerptV1 reconstruction) and FR38 (deterministic evidence summary builder per D9) complete. `object_store_client` wired through cold-path call chain via dependency injection. Code review resolved 3 findings (2 MEDIUM, 1 LOW). All 1034 tests pass (0 skipped). Ruff clean. Documentation updated.
