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
  - artifact/implementation-artifacts/3-2-reconstruct-case-context-and-build-deterministic-evidence-summary.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/contracts/triage_excerpt.py
  - src/aiops_triage_pipeline/contracts/enums.py
  - src/aiops_triage_pipeline/contracts/gate_input.py
  - src/aiops_triage_pipeline/contracts/action_decision.py
  - src/aiops_triage_pipeline/contracts/case_header_event.py
  - src/aiops_triage_pipeline/models/case_file.py
  - src/aiops_triage_pipeline/models/peak.py
  - src/aiops_triage_pipeline/storage/casefile_io.py
  - src/aiops_triage_pipeline/__main__.py
  - tests/unit/test_main.py
  - _bmad/tea/config.yaml
  - _bmad/tea/testarch/tea-index.csv
  - _bmad/tea/testarch/knowledge/data-factories.md
  - _bmad/tea/testarch/knowledge/component-tdd.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-healing-patterns.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-priorities-matrix.md
  - _bmad/tea/testarch/knowledge/ci-burn-in.md
  - _bmad/tea/testarch/knowledge/overview.md
---

# ATDD Checklist - Epic 3, Story 3.2: Reconstruct Case Context and Build Deterministic Evidence Summary

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Backend unit (pytest) + integration (MinIO testcontainer)
**TDD Phase:** RED

## Story Summary

Story 3.2 wires the cold-path event handler to read a triage casefile from S3/MinIO and produce
two outputs: a `TriageExcerptV1` (context reconstruction, FR37) and a deterministic UTF-8 plain
text evidence summary (FR38). Both are required before any LLM call in the cold-path diagnosis
pipeline.

**As an** SRE automation pipeline
**I want** to reconstruct triage context from persisted casefiles and produce a stable evidence summary
**So that** the LLM enrichment step receives a consistent, hash-verified snapshot of each alert case

## Acceptance Criteria

1. AC1 — Context retrieval: Given a CaseFileTriageV1 written to S3, when `retrieve_case_context()`
   is called with the case_id, then a TriageExcerptV1 is returned with all fields correctly mapped
   from the casefile. Missing casefile raises; hash mismatch raises. Never silently returns None.
2. AC2 — Evidence summary: Given a TriageExcerptV1, when `build_evidence_summary()` is called,
   then it returns a deterministic byte-stable UTF-8 string containing all required sections with
   correct content. Same input always produces identical bytes; order of dict keys does not affect
   output.

## Stack Detection / Mode

- `detected_stack`: backend (`pyproject.toml` + pytest tree, no frontend browser framework)
- `tea_execution_mode`: auto -> sequential (backend adaptation)
- Generation mode: AI generation only (no browser recording)

## Test Strategy

- Unit tests (P0) pin the `retrieve_case_context()` contract: correct field mapping from all
  casefile sub-models, hash integrity enforcement, and error propagation for missing/corrupted
  objects.
- Unit tests (P0) pin the `build_evidence_summary()` contract: byte-stability guarantee (D9
  architectural decision), all four EvidenceStatus labels in correct subsections, required section
  ordering, Finding field rendering, temporal context flags.
- Unit tests (P1) pin integration wiring in `__main__._cold_path_process_event()`: new
  `object_store_client` parameter, correct call sequence, warning log on retrieval failure.
- Integration tests (P0) use a real MinIO testcontainer for full round-trip: persist → retrieve →
  assert all TriageExcerptV1 fields, and verify missing object raises.
- No browser E2E tests for this backend-only story.

## Failing Tests Created (RED Phase)

### Unit Tests — Context Retrieval (21 tests)

**File:** `tests/unit/diagnosis/test_context_retrieval.py`

- `TestContextRetrievalReturnType::test_returns_triage_excerpt_v1` (3.2-UNIT-001) — RED
- `TestContextRetrievalFieldMapping::test_case_id_mapped_correctly` (3.2-UNIT-002) — RED
- `TestContextRetrievalFieldMapping::test_env_mapped_from_gate_input` (3.2-UNIT-003) — RED
- `TestContextRetrievalFieldMapping::test_cluster_id_mapped_from_gate_input` (3.2-UNIT-004) — RED
- `TestContextRetrievalFieldMapping::test_stream_id_mapped_from_gate_input` (3.2-UNIT-005) — RED
- `TestContextRetrievalFieldMapping::test_topic_mapped_from_gate_input` (3.2-UNIT-006) — RED
- `TestContextRetrievalFieldMapping::test_anomaly_family_mapped_from_gate_input` (3.2-UNIT-007) — RED
- `TestContextRetrievalFieldMapping::test_topic_role_mapped_from_gate_input` (3.2-UNIT-008) — RED
- `TestContextRetrievalFieldMapping::test_criticality_tier_mapped_from_gate_input` (3.2-UNIT-009) — RED
- `TestContextRetrievalFieldMapping::test_routing_key_mapped_from_topology_context` (3.2-UNIT-010) — RED
- `TestContextRetrievalFieldMapping::test_sustained_mapped_from_gate_input` (3.2-UNIT-011) — RED
- `TestContextRetrievalFieldMapping::test_evidence_status_map_mapped_from_snapshot` (3.2-UNIT-012) — RED
- `TestContextRetrievalFieldMapping::test_findings_mapped_from_gate_input` (3.2-UNIT-013) — RED
- `TestContextRetrievalFieldMapping::test_triage_timestamp_mapped_from_casefile` (3.2-UNIT-014) — RED
- `TestContextRetrievalFieldMapping::test_peak_true_when_peak_context_is_peak_window` (3.2-UNIT-015) — RED
- `TestContextRetrievalFieldMapping::test_peak_false_when_peak_context_not_peak_window` (3.2-UNIT-016) — RED
- `TestContextRetrievalHashIntegrity::test_raises_on_hash_mismatch` (3.2-UNIT-017) — RED
- `TestContextRetrievalHashIntegrity::test_raises_on_missing_triage_json` (3.2-UNIT-018) — RED
- `TestContextRetrievalHashIntegrity::test_does_not_return_none_on_missing` (3.2-UNIT-019) — RED
- `TestContextRetrievalPeakEdgeCases::test_peak_none_when_no_peak_context` (3.2-UNIT-020) — RED
- `TestContextRetrievalPeakEdgeCases::test_peak_false_when_near_peak_but_not_peak` (3.2-UNIT-021) — RED

**Root failure:** `ImportError: No module named 'aiops_triage_pipeline.diagnosis.context_retrieval'`

### Unit Tests — Evidence Summary (37 tests)

**File:** `tests/unit/diagnosis/test_evidence_summary.py`

- `TestEvidenceSummaryReturnType::test_returns_string` (3.2-UNIT-101) — RED
- `TestEvidenceSummaryReturnType::test_returns_non_empty_string` (3.2-UNIT-102) — RED
- `TestEvidenceSummaryReturnType::test_result_is_valid_utf8` (3.2-UNIT-103) — RED
- `TestEvidenceSummaryByteStability::test_identical_calls_produce_identical_output` (3.2-UNIT-104) — RED
- `TestEvidenceSummaryByteStability::test_dict_insertion_order_does_not_affect_output` (3.2-UNIT-105) — RED
- `TestEvidenceSummaryByteStability::test_no_timestamps_in_output` (3.2-UNIT-106) — RED
- `TestEvidenceSummaryByteStability::test_sorting_applied_to_evidence_status_keys` (3.2-UNIT-107) — RED
- `TestEvidenceSummaryByteStability::test_sorting_applied_to_findings` (3.2-UNIT-108) — RED
- `TestEvidenceSummarySections::test_all_four_sections_present` (3.2-UNIT-109) — RED
- `TestEvidenceSummarySections::test_case_context_section_present` (3.2-UNIT-110) — RED
- `TestEvidenceSummarySections::test_evidence_status_section_present` (3.2-UNIT-111) — RED
- `TestEvidenceSummarySections::test_anomaly_findings_section_present` (3.2-UNIT-112) — RED
- `TestEvidenceSummarySections::test_temporal_context_section_present` (3.2-UNIT-113) — RED
- `TestEvidenceSummarySections::test_section_order_fixed` (3.2-UNIT-114) — RED
- `TestEvidenceSummaryEvidenceStatus::test_present_label_appears_for_present_metric` (3.2-UNIT-115) — RED
- `TestEvidenceSummaryEvidenceStatus::test_absent_label_appears_for_absent_metric` (3.2-UNIT-116) — RED
- `TestEvidenceSummaryEvidenceStatus::test_stale_label_appears_for_stale_metric` (3.2-UNIT-117) — RED
- `TestEvidenceSummaryEvidenceStatus::test_unknown_label_appears_for_unknown_metric` (3.2-UNIT-118) — RED
- `TestEvidenceSummaryEvidenceStatus::test_unknown_explicitly_described_as_missing_or_unavailable` (3.2-UNIT-119) — RED
- `TestEvidenceSummaryEvidenceStatus::test_all_four_status_labels_in_summary` (3.2-UNIT-120) — RED
- `TestEvidenceSummaryFindings::test_finding_id_rendered` (3.2-UNIT-121) — RED
- `TestEvidenceSummaryFindings::test_finding_name_rendered` (3.2-UNIT-122) — RED
- `TestEvidenceSummaryFindings::test_finding_severity_rendered` (3.2-UNIT-123) — RED
- `TestEvidenceSummaryFindings::test_finding_is_anomalous_rendered` (3.2-UNIT-124) — RED
- `TestEvidenceSummaryFindings::test_finding_is_primary_rendered` (3.2-UNIT-125) — RED
- `TestEvidenceSummaryFindings::test_finding_evidence_required_rendered` (3.2-UNIT-126) — RED
- `TestEvidenceSummaryFindings::test_finding_reason_codes_rendered` (3.2-UNIT-127) — RED
- `TestEvidenceSummaryFindings::test_no_finding_when_findings_empty` (3.2-UNIT-128) — RED
- `TestEvidenceSummaryTemporalContext::test_sustained_true_rendered` (3.2-UNIT-129) — RED
- `TestEvidenceSummaryTemporalContext::test_sustained_false_rendered` (3.2-UNIT-130) — RED
- `TestEvidenceSummaryTemporalContext::test_peak_true_rendered` (3.2-UNIT-131) — RED
- `TestEvidenceSummaryTemporalContext::test_peak_false_rendered` (3.2-UNIT-132) — RED
- `TestEvidenceSummaryCaseContext::test_case_id_in_summary` (3.2-UNIT-133) — RED
- `TestEvidenceSummaryCaseContext::test_env_in_summary` (3.2-UNIT-134) — RED
- `TestEvidenceSummaryCaseContext::test_topic_in_summary` (3.2-UNIT-135) — RED
- `TestEvidenceSummaryCaseContext::test_anomaly_family_in_summary` (3.2-UNIT-136) — RED
- `TestEvidenceSummaryCaseContext::test_criticality_tier_in_summary` (3.2-UNIT-137) — RED

**Root failure:** `ImportError: No module named 'aiops_triage_pipeline.diagnosis.evidence_summary'`

### Unit Tests — Main Wiring (4 tests)

**File:** `tests/unit/test_main.py` (class `TestColdPathProcessEventWiring`)

- `test_cold_path_process_event_accepts_object_store_client_parameter` (3.2-UNIT-201) — RED
- `test_cold_path_process_event_calls_retrieve_case_context` (3.2-UNIT-202) — RED
- `test_cold_path_process_event_calls_build_evidence_summary` (3.2-UNIT-203) — RED
- `test_cold_path_process_event_logs_warning_on_retrieval_failure` (3.2-UNIT-204) — RED

**Root failure:** `_cold_path_process_event` has no `object_store_client` parameter; modules not yet imported in `__main__`.

### Integration Tests — Context Reconstruction (11 tests)

**File:** `tests/integration/cold_path/test_context_reconstruction.py`

- `TestContextReconstructionRoundTrip::test_retrieve_case_context_returns_triage_excerpt_v1` (3.2-INT-001) — RED
- `TestContextReconstructionRoundTrip::test_case_id_matches` (3.2-INT-002) — RED
- `TestContextReconstructionRoundTrip::test_env_matches_gate_input_env` (3.2-INT-003) — RED
- `TestContextReconstructionRoundTrip::test_topic_matches_gate_input_topic` (3.2-INT-004) — RED
- `TestContextReconstructionRoundTrip::test_routing_key_matches_topology_context` (3.2-INT-005) — RED
- `TestContextReconstructionRoundTrip::test_evidence_status_map_all_four_statuses` (3.2-INT-006) — RED
- `TestContextReconstructionRoundTrip::test_findings_reconstructed_with_correct_fields` (3.2-INT-007) — RED
- `TestContextReconstructionRoundTrip::test_triage_timestamp_matches` (3.2-INT-008) — RED
- `TestContextReconstructionRoundTrip::test_sustained_flag_matches` (3.2-INT-009) — RED
- `TestContextReconstructionRoundTrip::test_peak_flag_from_peak_context` (3.2-INT-010) — RED
- `TestContextReconstructionMissingObject::test_raises_on_nonexistent_case_id` (3.2-INT-011) — RED

**Root failure:** `ImportError: No module named 'aiops_triage_pipeline.diagnosis.context_retrieval'`

## Modules to Implement (GREEN Phase)

### `src/aiops_triage_pipeline/diagnosis/context_retrieval.py`

```
retrieve_case_context(case_id: str, object_store_client: S3ObjectStoreClient) -> TriageExcerptV1
```

- Read triage.json via `read_casefile_stage_json_or_none()`; raise if absent (Invariant A)
- Validate hash via `has_valid_casefile_triage_hash()`; raise if mismatch
- Map all TriageExcerptV1 fields from casefile sub-models per story field mapping table
- Derive `peak` from `evidence_snapshot.peak_context.is_peak_window` (None if no peak_context)

### `src/aiops_triage_pipeline/diagnosis/evidence_summary.py`

```
build_evidence_summary(excerpt: TriageExcerptV1) -> str
```

- Pure function (D9 architectural decision); no side effects; no timestamps; byte-stable
- Sorted evidence_status_map keys; sorted findings by finding_id
- Four required sections in fixed order: Case Context, Evidence Status, Anomaly Findings, Temporal Context
- All four EvidenceStatus variants labeled; UNKNOWN described as "missing or unavailable"
- All Finding fields rendered (id, name, severity, anomalous, primary, evidence_required, reason_codes)

### `src/aiops_triage_pipeline/__main__.py` (update)

- Add `object_store_client` parameter to `_cold_path_process_event()`
- Call `retrieve_case_context(case_id=event.case_id, object_store_client=object_store_client)`
- Call `build_evidence_summary(excerpt)` on the returned excerpt
- Log `cold_path_context_retrieval_failed` warning on exception; do not re-raise

## Implementation Checklist

### AC1 — Context Retrieval

- [ ] Create `src/aiops_triage_pipeline/diagnosis/__init__.py` (empty)
- [ ] Create `src/aiops_triage_pipeline/diagnosis/context_retrieval.py`
- [ ] Implement `retrieve_case_context()` with triage.json read and hash validation
- [ ] Map all 13 TriageExcerptV1 fields from the correct casefile sub-models
- [ ] Raise (not None) when triage.json is absent (Invariant A)
- [ ] Raise when hash verification fails
- [ ] Handle `peak_context is None` gracefully (peak=None)

### AC2 — Evidence Summary

- [ ] Create `src/aiops_triage_pipeline/diagnosis/evidence_summary.py`
- [ ] Implement `build_evidence_summary()` as pure function
- [ ] Sort evidence_status_map keys deterministically
- [ ] Sort findings by finding_id
- [ ] Render all four EvidenceStatus labels with correct descriptions
- [ ] Render all four required sections in fixed order
- [ ] Include all Finding fields in output
- [ ] Include temporal context (sustained, peak) flags
- [ ] No datetime calls or non-deterministic output

### Main Wiring

- [ ] Add `object_store_client` parameter to `_cold_path_process_event()`
- [ ] Import `retrieve_case_context` and `build_evidence_summary` in `__main__.py`
- [ ] Wire call sequence: retrieve → summarize → (pass to LLM stub)
- [ ] Add `cold_path_context_retrieval_failed` warning log on exception (fail-open)

## Running Tests

```bash
# Unit tests only (no Docker required)
uv run pytest -q tests/unit/diagnosis/ tests/unit/test_main.py::TestColdPathProcessEventWiring

# Integration tests (requires Docker)
uv run pytest -q -m integration tests/integration/cold_path/test_context_reconstruction.py

# All RED-phase tests for Story 3.2
uv run pytest -q \
  tests/unit/diagnosis/test_context_retrieval.py \
  tests/unit/diagnosis/test_evidence_summary.py \
  tests/unit/test_main.py::TestColdPathProcessEventWiring \
  tests/integration/cold_path/test_context_reconstruction.py
```

## Test Execution Evidence (RED Phase Confirmed)

**Command:** `uv run pytest -q tests/unit/diagnosis/ tests/unit/test_main.py::TestColdPathProcessEventWiring`

**Result:**

```text
FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
62 failed in Xs
```

**Failure summary:**

- All 21 `test_context_retrieval.py` tests: `ImportError: aiops_triage_pipeline.diagnosis.context_retrieval not implemented yet (Story 3.2 RED phase)`
- All 37 `test_evidence_summary.py` tests: `ImportError: aiops_triage_pipeline.diagnosis.evidence_summary not implemented yet (Story 3.2 RED phase)`
- All 4 `TestColdPathProcessEventWiring` tests: `object_store_client` not in signature / patches not called

**Zero regressions:** 908 pre-existing unit tests continue to PASS.

## Generated Artifacts

- `artifact/test-artifacts/atdd-checklist-3-2-reconstruct-case-context-and-build-deterministic-evidence-summary.md`
- `tests/unit/diagnosis/test_context_retrieval.py` (21 unit tests, RED)
- `tests/unit/diagnosis/test_evidence_summary.py` (37 unit tests, RED)
- `tests/integration/cold_path/test_context_reconstruction.py` (11 integration tests, RED)
- `tests/unit/test_main.py` (modified, +4 tests in `TestColdPathProcessEventWiring`, RED)

## Validation Notes

- Story ACs are explicit and testable; all ACs fully covered by failing tests.
- Backend pytest framework and test folder conventions are consistent with project standards.
- No browser CLI/MCP sessions were used; cleanup not required.
- RED phase stub pattern (try/except import + fallback function) allows test collection to succeed
  while deterministically failing at runtime.
- Python 3 except clause name deletion handled: error message captured to module-level
  `_IMPORT_ERROR_MSG` string before except block exits.
- Hash-correct `CaseFileTriageV1` fixtures built using `compute_casefile_triage_hash()` to
  support hash integrity tests.

## Completion Summary

ATDD RED phase is complete for Story 3.2 with 62 deterministic failing tests across four files:

- 21 unit tests pin `retrieve_case_context()` field mapping, hash integrity, and error propagation
- 37 unit tests pin `build_evidence_summary()` byte-stability guarantee, section structure,
  EvidenceStatus labeling, Finding rendering, and temporal context
- 4 unit tests pin `_cold_path_process_event()` wiring for the new object_store_client parameter
  and call sequence
- 11 integration tests validate full MinIO round-trip and error handling for missing objects

Sprint status updated: `3-2-reconstruct-case-context-and-build-deterministic-evidence-summary: in-progress`
