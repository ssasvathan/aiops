---
title: 'Fix recurring hot_path.case_error for existing invalid triage artifacts'
slug: 'fix-hot-path-case-error-existing-invalid-triage'
created: '2026-03-31T00:45:00Z'
status: 'Completed'
stepsCompleted: [1, 2, 3, 4]
tech_stack:
  - 'Python 3.13'
  - 'structlog 25.5.0'
  - 'pydantic v2 models'
  - 'S3/MinIO via boto3 client abstraction'
  - 'pytest + pytest-asyncio'
files_to_modify:
  - 'src/aiops_triage_pipeline/__main__.py'
  - 'tests/unit/test_main.py'
code_patterns:
  - 'Thin hot-path orchestration in __main__.py with structured event_type logging'
  - 'Casefile existence probe via get_existing_casefile_triage(...)'
  - 'Hash-validation on read in read_casefile_stage_json_or_none(...)'
  - 'Per-decision fail-safe exception boundary in hot-path loop'
test_patterns:
  - 'Monkeypatch-driven scheduler loop unit tests in tests/unit/test_main.py'
  - 'MagicMock call inspection for event_type and structured log fields'
  - 'Casefile lookup behavior tests in tests/unit/pipeline/stages/test_casefile.py'
---

# Tech-Spec: Fix recurring hot_path.case_error for existing invalid triage artifacts

**Created:** 2026-03-31T00:45:00Z

## Overview

### Problem Statement

On the current branch/runtime, the hot-path loop emits `hot_path.case_error` every cycle for harness scopes. The reproduced root cause is a read-time `ValueError` (`triage_hash does not match canonical serialized payload bytes`) when `get_existing_casefile_triage(...)` attempts to load existing triage artifacts with invalid hash content.

### Solution

Make the hot-path existing-casefile pre-check resilient to invalid persisted triage payloads. Detect this specific invalid-artifact read failure path, emit an explicit structured event, and skip further processing for the affected decision (assembly/persist/outbox/dispatch) so the scheduler remains stable and stops repeated error spam for the same corrupted objects.

### Scope

**In Scope:**
- Fix `hot_path.case_error` root causes reproducible in the same hot-path decision loop in `__main__.py`.
- Address the currently observed invalid-existing-triage read path (`ValueError` on triage hash validation).
- Add targeted tests for the guarded behavior and logging outcome.

**Out of Scope:**
- Backfilling or rewriting existing corrupted triage objects in MinIO.
- Changing overall casefile hash model or write-once storage contract semantics.
- Unrelated pipeline-stage refactors outside this hot-path loop.

## Context for Development

### Codebase Patterns

- Hot-path orchestration in `src/aiops_triage_pipeline/__main__.py` uses a per-decision boundary (`try/except Exception`) that logs `hot_path_case_processing_failed` with `event_type="hot_path.case_error"`.
- Existing-casefile guard is executed before assembly/persist/dispatch using `get_existing_casefile_triage(...)`; when the lookup returns a casefile, the code logs `casefile.triage_already_exists` and continues.
- `read_casefile_stage_json_or_none(...)` in `storage/casefile_io.py` validates hash integrity at read boundaries and raises `ValueError` when triage hash does not match canonical payload bytes.
- `get_existing_casefile_triage(...)` intentionally propagates that `ValueError` (validated by unit tests), so caller-level handling is the correct containment point for this runtime path.
- Live runtime evidence confirms cycle-stable repeated failures every scheduler cycle for two fixed action fingerprints, indicating persistent invalid stored artifacts rather than transient lookup misses.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `src/aiops_triage_pipeline/__main__.py` | Primary fix location: handle lookup-time invalid-triage `ValueError` as a scoped skip path |
| `src/aiops_triage_pipeline/pipeline/stages/casefile.py` | Lookup helper contract (currently propagates `ValueError`; no behavior change expected) |
| `src/aiops_triage_pipeline/storage/casefile_io.py` | Source of hash-validation `ValueError` in triage reads |
| `tests/unit/test_main.py` | Add/adjust scheduler-loop tests for invalid-existing-triage handling and logging |
| `tests/unit/pipeline/stages/test_casefile.py` | Existing contract tests confirm helper propagates tamper-related `ValueError` |

### Technical Decisions

- Handle the observed `ValueError` at the hot-path caller boundary immediately around existing-casefile lookup, then `continue` decision processing for that scope.
- Preserve helper/storage contracts (`get_existing_casefile_triage` + `read_casefile_stage_json_or_none`) to avoid weakening data-integrity guarantees and to keep current unit-test intent valid.
- Emit a dedicated structured event for invalid existing triage artifacts (distinct from generic `hot_path.case_error`) with scope + action fingerprint fields for triage.
- Do not mutate/repair existing corrupted objects in this change; the behavior is runtime containment and noise reduction.
- Keep assembly/persist/outbox/dispatch short-circuited for invalid-existing-triage decisions to prevent repeated invariant/validation failure loops.

## Implementation Plan

### Tasks

- [x] Task 1: Add targeted invalid-existing-triage handling at lookup boundary in hot path
  - File: `src/aiops_triage_pipeline/__main__.py`
  - Action: Wrap `get_existing_casefile_triage(...)` in a narrow `except ValueError as exc` branch that checks for the known hash-validation message (`triage_hash does not match canonical serialized payload bytes`), logs a dedicated structured event, and `continue`s the decision loop.
  - Notes: Do not swallow unrelated `ValueError`s; re-raise non-matching values so they continue through the existing generic `hot_path.case_error` handler.

- [x] Task 2: Preserve current behavior for known-good and integration-failure paths
  - File: `src/aiops_triage_pipeline/__main__.py`
  - Action: Keep existing `existing_casefile is not None` skip behavior unchanged and keep generic `except Exception` logging path for non-targeted exceptions.
  - Notes: No changes to `get_existing_casefile_triage(...)` or `read_casefile_stage_json_or_none(...)` contracts.

- [x] Task 3: Add unit test for the newly handled invalid-existing-triage path
  - File: `tests/unit/test_main.py`
  - Action: Add a scheduler-loop test where `get_existing_casefile_triage` raises `ValueError("triage_hash does not match canonical serialized payload bytes")`.
  - Notes: Assert no assemble/persist/outbox/dispatch calls, assert dedicated invalid-existing-triage log is emitted, and assert `hot_path_case_processing_failed` is not emitted for this path.

- [x] Task 4: Add unit test ensuring non-targeted `ValueError` still follows generic error path
  - File: `tests/unit/test_main.py`
  - Action: Add a scheduler-loop test where lookup raises a different `ValueError` message.
  - Notes: Assert generic `hot_path_case_processing_failed` with `event_type="hot_path.case_error"` still occurs (no over-broad catch behavior).

- [x] Task 5: Re-run targeted regression and lint checks
  - File: `tests/unit/test_main.py`, `tests/unit/pipeline/stages/test_casefile.py`
  - Action: Execute targeted unit suites and Ruff lint after code changes.
  - Notes: Keep existing `test_get_existing_casefile_triage_propagates_value_error_for_tampered_payload` passing to preserve data-integrity contract behavior.

### Acceptance Criteria

- [x] AC 1: Given a hot-path decision where `get_existing_casefile_triage(...)` raises `ValueError("triage_hash does not match canonical serialized payload bytes")`, when the scheduler processes that decision, then it logs a dedicated invalid-existing-triage event and skips assembly, persistence, outbox insert, and dispatch for that decision.
- [x] AC 2: Given the same invalid-existing-triage condition, when the decision is processed, then `hot_path_case_processing_failed` with `event_type="hot_path.case_error"` is not emitted for that decision.
- [x] AC 3: Given `get_existing_casefile_triage(...)` raises `IntegrationError`, when the scheduler processes that decision, then the existing generic error behavior remains unchanged and `hot_path_case_processing_failed` with `event_type="hot_path.case_error"` is emitted.
- [x] AC 4: Given `get_existing_casefile_triage(...)` raises a non-targeted `ValueError`, when the scheduler processes that decision, then the exception is not treated as invalid-existing-triage and generic `hot_path.case_error` handling still applies.
- [x] AC 5: Given lookup returns a valid existing casefile, when the scheduler processes that decision, then `casefile.triage_already_exists` behavior remains unchanged (skip path still active).
- [x] AC 6: Given the implementation changes are complete, when running `uv run pytest -q tests/unit/test_main.py tests/unit/pipeline/stages/test_casefile.py` and `uv run ruff check`, then all checks pass.

## Additional Context

### Dependencies

- Existing scheduler-loop test harness utilities in `tests/unit/test_main.py`:
- `_hot_path_settings_for_coordination_tests(...)`
- `_patch_hot_path_case_processing_dependencies(...)`
- Existing casefile lookup contract tests in `tests/unit/pipeline/stages/test_casefile.py` (especially tampered payload propagation).
- Structured logging conventions (`event`, `event_type`, key-value fields) in hot-path orchestration.
- No new third-party dependencies or infrastructure changes required.

### Testing Strategy

- Unit tests:
- Add new scheduler-loop test for targeted hash-mismatch `ValueError` handling in `tests/unit/test_main.py`.
- Add scheduler-loop test for non-targeted `ValueError` to ensure generic `hot_path.case_error` path remains intact.
- Preserve and run existing lookup-contract tests in `tests/unit/pipeline/stages/test_casefile.py`.
- Manual verification (runtime):
- Rebuild/restart app container, confirm repeated `hot_path.case_error` entries for the two known fingerprints no longer appear.
- Confirm replacement dedicated invalid-existing-triage event appears once per affected decision cycle.
- Commands:
- `uv run pytest -q tests/unit/test_main.py tests/unit/pipeline/stages/test_casefile.py`
- `uv run ruff check`

### Notes

- Reproduced in live container (`aiops-app-1`) for:
- `case-harness-harness-cluster-harness-lag-topic-3961489c3af3`
- `case-harness-harness-cluster-harness-proxy-topic-d12ef3b3956b`
- In-container probe confirms exception class/message:
- `ValueError: triage_hash does not match canonical serialized payload bytes`
- Risk note: message-matching a `ValueError` string is intentionally narrow to avoid masking unrelated logic errors; a future hardening improvement is to introduce a typed exception for invalid stored casefile payloads.
- Limitation: this change contains runtime error noise; it does not repair existing corrupted triage objects.

## Review Notes

- Adversarial review completed
- Findings: 10 total, 1 fixed, 9 skipped
- Resolution approach: auto-fix
