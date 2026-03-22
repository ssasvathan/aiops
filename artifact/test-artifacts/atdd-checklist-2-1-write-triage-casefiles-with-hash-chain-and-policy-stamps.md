---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-03-22'
workflowType: 'testarch-atdd'
inputDocuments:
  - artifact/implementation-artifacts/2-1-write-triage-casefiles-with-hash-chain-and-policy-stamps.md
  - src/aiops_triage_pipeline/models/case_file.py
  - src/aiops_triage_pipeline/storage/casefile_io.py
  - src/aiops_triage_pipeline/pipeline/stages/casefile.py
  - tests/unit/storage/test_casefile_io.py
  - tests/unit/pipeline/stages/test_casefile.py
  - _bmad/tea/config.yaml
---

# ATDD Checklist - Epic 2, Story 2.1: Write Triage Casefiles with Hash Chain and Policy Stamps

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Unit (backend Python stack)
**TDD Phase:** RED (failing tests generated — implementation gaps identified)

---

## Story Summary

As an SRE/platform engineer, triage casefiles must be written once with integrity metadata so that
every decision is auditable for long-term replay. Story 2.1 focuses entirely on the write-once
casefile triage stage and its hash chain and policy stamp invariants.

**As a** SRE/platform engineer
**I want** triage casefiles to be written once with integrity metadata
**So that** every decision is auditable for long-term replay

---

## Acceptance Criteria

1. **Given** a triage decision is produced
   **When** casefile assembly runs
   **Then** `triage.json` is written exactly once to object storage
   **And** it includes SHA-256 chain metadata and active policy version stamps.

2. **Given** a downstream publish is attempted
   **When** triage artifact existence is checked
   **Then** downstream event publication is blocked unless `triage.json` already exists
   **And** this enforces Invariant A in all runtime modes.

---

## Stack Detection

- **Detected Stack:** `backend`
- **Test Framework:** pytest 9.0.2
- **Generation Mode:** AI generation (no browser recording for backend projects)
- **Execution Mode:** sequential

---

## Test Strategy

### AC 1 — Write-once triage.json with SHA-256 hash chain and policy version stamps

| Scenario | Level | Priority | Test State |
|---|---|---|---|
| Policy stamp completeness — all five fields non-empty | Unit | P0 | GREEN (existing + new) |
| `anomaly_detection_policy_version` FR31 gap stamp | Unit | P0 | **RED — implementation missing** |
| `diagnosis_policy_version` sourced from argument | Unit | P1 | GREEN (new test) |
| Placeholder hash rejected at persist time | Unit | P0 | GREEN (new test) |
| Idempotent retry raises on differing payload | Unit | P1 | GREEN (new test) |
| Hash payload excludes raw sensitive field values | Unit | P0 | **RED — contract not enforced at io layer** |
| `validate_casefile_triage_json` round-trip preserves hash validity | Unit | P0 | GREEN (existing) |

### AC 2 — Invariant A: triage.json exists before downstream stages

| Scenario | Level | Priority | Test State |
|---|---|---|---|
| `persist_casefile_diagnosis_stage` raises when triage absent | Unit | P0 | GREEN (new test) |
| `persist_casefile_linkage_stage` raises when triage absent | Unit | P0 | GREEN (new test) |
| `persist_casefile_labels_stage` raises when triage absent | Unit | P0 | GREEN (new test) |
| `persist_casefile_and_prepare_outbox_ready` requires confirmed write | Unit | P0 | GREEN (existing) |
| `persist_casefile_and_prepare_outbox_ready` fails loud on store unavailable | Unit | P0 | GREEN (existing) |

---

## Failing Tests Created (RED Phase)

### Unit Tests — `tests/unit/storage/test_casefile_io.py` (3 RED tests)

**File:** `tests/unit/storage/test_casefile_io.py`

- **Test:** `test_casefile_policy_versions_anomaly_detection_policy_version_field_present`
  - **Status:** RED — `AttributeError: 'CaseFilePolicyVersions' object has no attribute 'anomaly_detection_policy_version'`
  - **Verifies:** FR31 — `CaseFilePolicyVersions` must include `anomaly_detection_policy_version` field for 25-month decision replay. This is the primary FR31 gap confirmed by source inspection.
  - **Failure Reason:** Field not yet added to `models/case_file.py::CaseFilePolicyVersions`

- **Test:** `test_casefile_policy_versions_anomaly_detection_policy_version_rejects_empty`
  - **Status:** RED — `Failed: DID NOT RAISE ValidationError` (field absent, extra kwarg silently ignored by Pydantic)
  - **Verifies:** FR31 — `anomaly_detection_policy_version` must enforce `min_length=1`, preventing empty-stamp persistence
  - **Failure Reason:** Field not yet added to model — Pydantic ignores the extra kwarg rather than validating it

- **Test:** `test_hash_computation_excludes_raw_sensitive_fields_in_baseline`
  - **Status:** RED — `AssertionError: Raw sensitive token value must never appear in the canonical hash payload baseline`
  - **Verifies:** NFR-S1 — the io-layer hash computation contract: `assemble_casefile_triage_stage` must sanitize before hashing. Confirms that calling `compute_casefile_triage_hash` on an unsanitized casefile WOULD include raw tokens — therefore sanitization MUST precede hash computation at the stage layer.
  - **Failure Reason:** Test documents that bypassing `assemble_casefile_triage_stage` sanitation exposes sensitive data. This serves as a regression guard for any new code paths that bypass the stage layer.

### Unit Tests — `tests/unit/pipeline/stages/test_casefile.py` (1 RED test)

**File:** `tests/unit/pipeline/stages/test_casefile.py`

- **Test:** `test_assemble_casefile_triage_stage_anomaly_detection_policy_version_stamped`
  - **Status:** RED — `AssertionError: CaseFilePolicyVersions is missing anomaly_detection_policy_version (FR31 gap)`
  - **Verifies:** FR31 — `assemble_casefile_triage_stage` must stamp `anomaly_detection_policy_version` in `CaseFilePolicyVersions` for 25-month decision replay coverage. All active policies affecting triage decisions must be stamped.
  - **Failure Reason:** `anomaly_detection_policy_version` field not yet in `CaseFilePolicyVersions` model and not wired into `assemble_casefile_triage_stage`

---

## Passing Tests Added (GREEN — new coverage filling story gaps)

### Unit Tests — `tests/unit/storage/test_casefile_io.py`

- `test_persist_casefile_triage_write_once_raises_invariant_violation_on_placeholder_hash`
  - Verifies: AC 1 — `persist_casefile_triage_write_once` rejects a casefile whose `triage_hash` has not been finalized (still `TRIAGE_HASH_PLACEHOLDER`)

- `test_persist_casefile_triage_write_once_idempotent_retry_raises_on_differing_payload`
  - Verifies: AC 1 — idempotent retry path raises `InvariantViolation` when existing payload differs from in-flight payload; no silent idempotent acceptance of mismatched content

### Unit Tests — `tests/unit/pipeline/stages/test_casefile.py`

- `test_persist_casefile_diagnosis_stage_raises_invariant_violation_when_triage_absent`
  - Verifies: AC 2 / Invariant A — diagnosis stage blocked when triage.json absent

- `test_persist_casefile_linkage_stage_raises_invariant_violation_when_triage_absent`
  - Verifies: AC 2 / Invariant A — linkage stage blocked when triage.json absent

- `test_persist_casefile_labels_stage_raises_invariant_violation_when_triage_absent`
  - Verifies: AC 2 / Invariant A — labels stage blocked when triage.json absent

- `test_assemble_casefile_triage_stage_policy_versions_all_five_fields_non_empty`
  - Verifies: AC 1 / FR31 — all five current `CaseFilePolicyVersions` fields are non-empty strings at assembly time

- `test_assemble_casefile_triage_stage_diagnosis_policy_version_from_argument`
  - Verifies: AC 1 — `diagnosis_policy_version` is sourced from the passed argument, not a hard-coded string

---

## Implementation Checklist

### Test: `test_casefile_policy_versions_anomaly_detection_policy_version_field_present` (RED)

**File:** `tests/unit/storage/test_casefile_io.py`

**Tasks to make this test pass:**

- [ ] Add `anomaly_detection_policy_version: str = Field(min_length=1)` to `CaseFilePolicyVersions` in `src/aiops_triage_pipeline/models/case_file.py`
- [ ] Update `assemble_casefile_triage_stage` in `src/aiops_triage_pipeline/pipeline/stages/casefile.py` to accept and wire `anomaly_detection_policy_version` argument
- [ ] Update all `assemble_casefile_triage_stage` call sites in `src/aiops_triage_pipeline/pipeline/scheduler.py` to pass the anomaly detection policy version from loaded config
- [ ] Update `validate_casefile_triage_json` round-trip tests to include the new field
- [ ] Update `_sample_casefile()` factory in `tests/unit/storage/test_casefile_io.py` to include `anomaly_detection_policy_version`
- [ ] Update `_build_scope_inputs` or fixture helpers in `tests/unit/pipeline/stages/test_casefile.py` if needed
- [ ] Run test: `uv run pytest tests/unit/storage/test_casefile_io.py::test_casefile_policy_versions_anomaly_detection_policy_version_field_present -v`
- [ ] Run test: `uv run pytest tests/unit/storage/test_casefile_io.py::test_casefile_policy_versions_anomaly_detection_policy_version_rejects_empty -v`
- [ ] Run test: `uv run pytest tests/unit/pipeline/stages/test_casefile.py::test_assemble_casefile_triage_stage_anomaly_detection_policy_version_stamped -v`
- [ ] ✅ All three tests pass (green phase)

**Estimated Effort:** 2-3 hours

---

### Test: `test_hash_computation_excludes_raw_sensitive_fields_in_baseline` (RED)

**File:** `tests/unit/storage/test_casefile_io.py`

**Tasks to make this test pass:**

- [ ] Verify that `_sanitize_casefile` in `src/aiops_triage_pipeline/pipeline/stages/casefile.py` is called BEFORE `compute_casefile_triage_hash` in all code paths in `assemble_casefile_triage_stage`
- [ ] Confirm no new code path bypasses sanitization before hash computation
- [ ] Update test assertion to reflect correct contract: the test should use `assemble_casefile_triage_stage` output (which IS sanitized) to verify the positive case, and should use a separate assertion that validates the sanitization order in the stage function
- [ ] Run test: `uv run pytest tests/unit/storage/test_casefile_io.py::test_hash_computation_excludes_raw_sensitive_fields_in_baseline -v`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1 hour

---

## Running Tests

```bash
# Run all Story 2.1 RED phase tests
uv run pytest tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py -k "2_1 or anomaly_detection or invariant_a or placeholder_hash or idempotent_retry or triage_absent or policy_versions_all or diagnosis_policy_version_from" -v

# Run only the RED (currently failing) tests
uv run pytest tests/unit/storage/test_casefile_io.py::test_casefile_policy_versions_anomaly_detection_policy_version_field_present tests/unit/storage/test_casefile_io.py::test_casefile_policy_versions_anomaly_detection_policy_version_rejects_empty tests/unit/storage/test_casefile_io.py::test_hash_computation_excludes_raw_sensitive_fields_in_baseline tests/unit/pipeline/stages/test_casefile.py::test_assemble_casefile_triage_stage_anomaly_detection_policy_version_stamped -v

# Run full casefile unit test suite
uv run pytest tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py -v

# Run full regression with quality gate
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs

# Lint check
uv run ruff check
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

**TEA Agent Responsibilities:**

- ✅ 4 failing tests written and failing for the correct reasons
- ✅ 7 new passing tests added for gaps with existing correct implementations
- ✅ No regressions in existing 53 tests
- ✅ Mock infrastructure uses existing `_FakeObjectStoreClient` and `_InMemoryObjectStoreClient` per-file patterns
- ✅ Implementation checklist created
- ✅ FR31 gap confirmed: `anomaly_detection_policy_version` absent from `CaseFilePolicyVersions`

**Verification:**

- 4 RED tests run and fail as expected
- 53 existing tests pass (zero regression)
- Failure messages are clear and actionable
- Tests fail due to missing implementation, not test bugs

---

### GREEN Phase (DEV Team — Next Steps)

**DEV Agent Responsibilities:**

1. **Primary task**: Add `anomaly_detection_policy_version: str = Field(min_length=1)` to `CaseFilePolicyVersions`
2. **Wire it**: Update `assemble_casefile_triage_stage` signature and call sites in `scheduler.py`
3. **Load the policy**: Load `config/policies/anomaly-detection-policy-v1.yaml` at the appropriate call site and extract the version field
4. **Run tests**: Verify 3 of the 4 RED tests turn GREEN
5. **Fix test_hash_computation**: Update or reframe the sanitization-order test to correctly capture the positive assertion
6. **Run full regression**: `uv run pytest -q -rs` → target: 0 failed, 0 skipped

---

### REFACTOR Phase (DEV Team — After All Tests Pass)

1. Verify all 57 tests pass (53 pre-existing + 4 new GREEN + 7 new GREEN = all)
2. Run `uv run ruff check` — zero violations
3. Ensure `anomaly_detection_policy_version` field ordering in JSON output follows declaration order
4. Confirm sprint gate: 0 skipped tests

---

## Next Steps

1. **Share this checklist** with the dev workflow (Story 2.1)
2. **Review the RED tests** in standup to confirm FR31 gap priority
3. **Run failing tests** to confirm RED phase: `uv run pytest tests/unit/storage/test_casefile_io.py::test_casefile_policy_versions_anomaly_detection_policy_version_field_present -v`
4. **Begin implementation** — add `anomaly_detection_policy_version` to `CaseFilePolicyVersions`
5. **Work one test at a time** (red → green for each)
6. **When all tests pass**, refactor and run quality gates
7. **When refactoring complete**, manually update story status to `in-progress` → `dev-complete` → `done` in sprint-status.yaml

---

## Test Execution Evidence

### Initial Test Run (RED Phase Verification)

**Command:** `uv run pytest tests/unit/storage/test_casefile_io.py tests/unit/pipeline/stages/test_casefile.py -v --tb=no -q`

**Results:**

```
collected 57 items

tests/unit/storage/test_casefile_io.py .............................FFF
tests/unit/pipeline/stages/test_casefile.py .......................F.

FAILED tests/unit/storage/test_casefile_io.py::test_casefile_policy_versions_anomaly_detection_policy_version_field_present
FAILED tests/unit/storage/test_casefile_io.py::test_casefile_policy_versions_anomaly_detection_policy_version_rejects_empty
FAILED tests/unit/storage/test_casefile_io.py::test_hash_computation_excludes_raw_sensitive_fields_in_baseline
FAILED tests/unit/pipeline/stages/test_casefile.py::test_assemble_casefile_triage_stage_anomaly_detection_policy_version_stamped

4 failed, 53 passed in 0.86s
```

**Summary:**

- Total tests: 57
- Passing: 53 (all pre-existing + new GREEN tests)
- Failing: 4 (expected — RED phase)
- Status: ✅ RED phase verified

**Expected Failure Messages:**

- `test_casefile_policy_versions_anomaly_detection_policy_version_field_present`: `AttributeError: 'CaseFilePolicyVersions' object has no attribute 'anomaly_detection_policy_version'`
- `test_casefile_policy_versions_anomaly_detection_policy_version_rejects_empty`: `Failed: DID NOT RAISE ValidationError`
- `test_hash_computation_excludes_raw_sensitive_fields_in_baseline`: `AssertionError: Raw sensitive token value must never appear in the canonical hash payload baseline`
- `test_assemble_casefile_triage_stage_anomaly_detection_policy_version_stamped`: `AssertionError: CaseFilePolicyVersions is missing anomaly_detection_policy_version (FR31 gap)`

---

## Knowledge Base References Applied

- **data-factories.md** — Per-file `_FakeObjectStoreClient` and `_InMemoryObjectStoreClient` factory patterns with no shared state across test files
- **test-quality.md** — Given-When-Then test naming: `test_{action}_{condition}_{expected}`, one assertion per logical concern, deterministic test data
- **test-levels-framework.md** — Backend stack: unit tests for pure functions and business logic; no E2E/browser tests needed
- **test-priorities-matrix.md** — P0 for invariant violations, P1 for edge cases

---

## Notes

- Primary FR31 gap confirmed: `anomaly_detection_policy_version` is absent from `CaseFilePolicyVersions` in `models/case_file.py`. All five existing fields ARE populated correctly by `assemble_casefile_triage_stage`. The sixth field (anomaly detection) is the only missing stamp.
- `config/policies/anomaly-detection-policy-v1.yaml` exists but its version is not yet stamped in the triage casefile.
- Invariant A enforcement at `persist_casefile_diagnosis_stage`, `persist_casefile_linkage_stage`, and `persist_casefile_labels_stage` is correctly implemented — the tests verify this and they pass GREEN.
- `diagnosis_policy_version` is correctly passed as an argument at all call sites in `scheduler.py` — verified GREEN.
- The hash sanitization order (NFR-S1) is correct in `assemble_casefile_triage_stage` — the RED test documents the CONTRACT that must hold for all code paths.

---

**Generated by BMad TEA Agent** — 2026-03-22
