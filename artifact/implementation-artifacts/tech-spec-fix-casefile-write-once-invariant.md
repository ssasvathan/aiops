---
title: 'Fix casefile write-once invariant violation in hot-path cycle'
slug: 'fix-casefile-write-once-invariant'
created: '2026-03-30'
status: 'Completed'
stepsCompleted: [1, 2, 3, 4]
tech_stack: ['Python 3.13', 'pydantic v2', 'MinIO (S3 via boto3)', 'Redis', 'structlog']
files_to_modify:
  - 'src/aiops_triage_pipeline/pipeline/stages/casefile.py'
  - 'src/aiops_triage_pipeline/pipeline/stages/__init__.py'
  - 'src/aiops_triage_pipeline/__main__.py'
  - 'tests/unit/pipeline/stages/test_casefile.py'
  - 'tests/integration/test_casefile_write.py'
code_patterns:
  - 'read_casefile_stage_json_or_none existence-check pattern (used in cold-path dependency validation)'
  - 'write-once persistence via put_if_absent + idempotency check'
  - 'ObjectStoreClientProtocol for MinIO access'
  - 'structlog structured logging with event_type fields'
  - 'thin __main__.py wiring — logic extracted to casefile.py helpers'
test_patterns:
  - '_FakeObjectStoreClient in-memory dict-backed mock for unit tests'
  - 'pytest-asyncio asyncio_mode=auto'
  - 'tests/unit/pipeline/stages/ for pipeline stage unit tests'
  - 'tests/unit/storage/ for storage/io unit tests'
  - 'tests/integration/test_casefile_write.py for MinIO-backed integration tests'
---

# Tech-Spec: Fix casefile write-once invariant violation in hot-path cycle

**Created:** 2026-03-30

## Overview

### Problem Statement

Every 30-second hot-path cycle fails with `InvariantViolation: write-once invariant violation: existing object payload differs from retry payload` for two persistent anomaly cases. The root cause: `_derive_case_id()` produces a stable `case_id` from `action_fingerprint` (pure structural identity — env/cluster/topic/anomaly_family/tier), but `assemble_casefile_triage_stage()` sets `triage_timestamp = datetime.now(UTC)` when no `triage_timestamp` is passed. Each cycle produces the same `case_id` but a different `triage_timestamp` → different payload → write-once check raises on every cycle after the first.

### Solution

Extract a new helper `get_existing_casefile_triage(*, gate_input, object_store_client) -> CaseFileTriageV1 | None` into `casefile.py`. This helper derives the `case_id` and checks MinIO for an existing triage artifact. In the hot-path loop, call this helper before `assemble_casefile_triage_stage`; if a casefile already exists, log and `continue` — skipping assembly, persistence, outbox insert, and dispatch entirely. The first recorded triage is authoritative. `_derive_case_id` is also made public (`derive_case_id`) to serve as the single source of truth for case ID derivation.

### Scope

**In Scope:**
- Expose `_derive_case_id` as `derive_case_id` in `casefile.py` (rename only, no logic change)
- Add `get_existing_casefile_triage(*, gate_input, object_store_client) -> CaseFileTriageV1 | None` to `casefile.py`
- Update `pipeline/stages/__init__.py` to export both new public names
- Add existence-check guard in `__main__.py` hot-path loop before `assemble_casefile_triage_stage`
- Unit tests: `derive_case_id` determinism; `get_existing_casefile_triage` skip/pass/error-propagation behaviour
- Integration test: existing triage artifact → hot-path skips re-assembly (positive assertions)

**Out of Scope:**
- Changing `case_id` derivation logic or `action_fingerprint` construction
- Modifying write-once semantics or `_persist_casefile_payload_write_once`
- Re-triage logic (updating existing casefiles)
- Changing `triage_timestamp` default behaviour
- Adding a `head_object` / `exists` primitive to `ObjectStoreClientProtocol`

---

## Context for Development

### Codebase Patterns

- **Existence-check pattern already established**: `read_casefile_stage_json_or_none` is used in cold-path stage dependency validation (`_validate_diagnosis_stage_hashes`, `_validate_linkage_stage_hashes`, etc.) before every write. The same function is the canonical tool for the hot-path guard — no new protocol surface needed. It is already imported at the top of `casefile.py`.
- **`__main__.py` must stay thin**: Logic belongs in `casefile.py` helpers, not in the main wiring file. The existence-check logic is extracted into `get_existing_casefile_triage` so it is independently testable and `__main__.py` only calls + branches.
- **`_derive_case_id` is currently private**: Defined at `casefile.py:233`. Called internally at `casefile.py:123` as `_derive_case_id(gate_input=gate_input)`. No callers outside the module. Safe to rename public; update the internal call site too.
- **`read_casefile_stage_json_or_none` already imported in `casefile.py`**: No new imports needed in `casefile.py` — it is already in the import block at lines 40–54.
- **`__main__.py` imports directly from `pipeline.stages.casefile`**: The existing import block is `from aiops_triage_pipeline.pipeline.stages.casefile import (assemble_casefile_triage_stage, persist_casefile_and_prepare_outbox_ready)`. Add `get_existing_casefile_triage` to this block.
- **`__init__.py` exports casefile public API**: Only `get_existing_casefile_triage` is added to `pipeline/stages/__init__.py` import + `__all__`. `derive_case_id` is NOT added to `__init__.py` — `__main__.py` imports directly from `pipeline.stages.casefile`, making an `__init__` export of `derive_case_id` dead code that would create a misleading half-public API.
- **Outbox is safe to skip**: `insert_pending_object` is idempotent for same case_id+payload, but skipping the block entirely is cleaner — first cycle already wrote the outbox entry.
- **Structured logging**: All log events use `event_type` field + key-value pairs via `structlog`. Log the skip with `event_type="casefile.triage_already_exists"`, including `case_id` and `scope`.
- **IntegrationError propagates — not treated as "not found"**: `read_casefile_stage_json_or_none` returns `None` only for `KeyError` with matching key or `ObjectNotFoundError`. `IntegrationError` propagates and is caught by the existing `except Exception` at `__main__.py:~843` — no extra handling needed in the guard.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `src/aiops_triage_pipeline/pipeline/stages/casefile.py` | Add `derive_case_id` (renamed from `_derive_case_id`) and new `get_existing_casefile_triage` helper |
| `src/aiops_triage_pipeline/pipeline/stages/__init__.py` | Add `get_existing_casefile_triage` to imports and `__all__` only |
| `src/aiops_triage_pipeline/__main__.py` | Hot-path loop at lines ~814-850; add `get_existing_casefile_triage` to import block; add guard before assembly |
| `src/aiops_triage_pipeline/storage/casefile_io.py` | `read_casefile_stage_json_or_none` used internally by new helper — **no changes to this file** |
| `tests/unit/pipeline/stages/test_casefile.py` | Add unit tests: `derive_case_id` determinism; `get_existing_casefile_triage` returns None / returns existing / propagates error |
| `tests/integration/test_casefile_write.py` | Add integration test: write triage → re-run hot-path block → assert no InvariantViolation, payload unchanged, log emitted |

### Technical Decisions

- **Extract to named helper, not inline in `__main__.py`**: `get_existing_casefile_triage` in `casefile.py` keeps `__main__.py` thin, enables clean unit testing, and follows the project's "reuse existing helper functions" rule.
- **Use `read_casefile_stage_json_or_none` not a HEAD/exists check**: Consistent with existing codebase pattern; validates hash integrity on read as a bonus. Adding a new `object_exists` primitive to `ObjectStoreClientProtocol` is unnecessary new surface area.
- **Make `_derive_case_id` public, not duplicated**: The derivation logic must not be duplicated. Making it public preserves single source of truth. `get_existing_casefile_triage` calls `derive_case_id` internally.
- **Skip entire block on existing case**: `dispatch_action` for OBSERVE does nothing meaningful; AG5 deduplication handles non-OBSERVE re-dispatch. Skipping all of assembly + persist + outbox + dispatch is correct.
- **IntegrationError propagates**: MinIO connectivity failure on the existence check is not treated as "not found". It propagates to the `except Exception` handler at `__main__.py:~843`, consistent with all other MinIO failure paths.

---

## Implementation Plan

### Tasks

- [x] Task 1: Rename `_derive_case_id` → `derive_case_id` in `casefile.py`
  - File: `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
  - Action: Rename the function definition at line 233 from `_derive_case_id` to `derive_case_id`. Update the internal call site at line 123 from `_derive_case_id(gate_input=gate_input)` to `derive_case_id(gate_input=gate_input)`. No logic changes.

- [x] Task 2: Add `get_existing_casefile_triage` helper to `casefile.py`
  - File: `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
  - Action: Add a new public function after `persist_casefile_and_prepare_outbox_ready`. It must: (1) resolve `case_id` using the **same precedence chain as `assemble_casefile_triage_stage`**: `gate_input.case_id or derive_case_id(gate_input=gate_input)` — this ensures the guard checks the same key that assembly would write; (2) call `read_casefile_stage_json_or_none(object_store_client=object_store_client, case_id=case_id, stage="triage")`; (3) if the result is non-None, return it narrowed to `CaseFileTriageV1` using `cast(CaseFileTriageV1, result)` — `cast` is a type-checker annotation only (runtime no-op), but is required here because `read_casefile_stage_json_or_none` returns the union type `CaseFileAnyPayload | None`; no additional runtime validation is needed since `read_casefile_stage_json_or_none` already validates the hash on read. Add `cast` to the `from typing import ...` block.
  - Notes: Function signature: `def get_existing_casefile_triage(*, gate_input: GateInputV1, object_store_client: ObjectStoreClientProtocol) -> CaseFileTriageV1 | None`. Let `IntegrationError` and `CriticalDependencyError` propagate unhandled — both are caught by the `except Exception` handler at `__main__.py:~843`.

- [x] Task 3: Update `pipeline/stages/__init__.py` exports
  - File: `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
  - Action: Add **only `get_existing_casefile_triage`** to the `from aiops_triage_pipeline.pipeline.stages.casefile import (...)` block and to `__all__`. Do NOT add `derive_case_id` to `__init__.py` at all — `__main__.py` imports directly from `pipeline.stages.casefile` (not via `__init__`), so exporting `derive_case_id` from `__init__` would be dead code that creates a misleading half-public API surface.

- [x] Task 4: Add existence-check guard in `__main__.py` hot-path loop
  - File: `src/aiops_triage_pipeline/__main__.py`
  - Action: (1) Add `get_existing_casefile_triage` to the **existing direct import** `from aiops_triage_pipeline.pipeline.stages.casefile import (...)` — do NOT change the import source to `pipeline.stages`; keep importing directly from `pipeline.stages.casefile` to match the existing style in `__main__.py`. (2) Inside the hot-path `try:` block at line ~814, before the call to `assemble_casefile_triage_stage`, add the guard:
    ```python
    existing_casefile = get_existing_casefile_triage(
        gate_input=gate_input,
        object_store_client=object_store_client,
    )
    if existing_casefile is not None:
        logger.info(
            "casefile_triage_already_exists",
            event_type="casefile.triage_already_exists",
            case_id=existing_casefile.case_id,
            scope=scope,
        )
        continue
    ```
  - Notes: The `continue` skips the remainder of the inner `for decision in decisions:` loop body (assembly + persist + outbox + dispatch). The existing `except Exception` at line ~843 already handles any `IntegrationError` or `CriticalDependencyError` raised by the existence check — no additional error handling needed.

- [x] Task 5: Unit tests — `derive_case_id` determinism
  - File: `tests/unit/pipeline/stages/test_casefile.py`
  - Action: Add a test that constructs a `GateInputV1` with a known `action_fingerprint` (e.g. `"harness/harness-cluster/harness_validation/SOURCE_TOPIC/harness-lag-topic/CONSUMER_LAG/TIER_1/group:harness-consumer"`) and asserts `derive_case_id(gate_input=gi)` returns `"case-harness-harness-cluster-harness-lag-topic-3961489c3af3"`. Assert the same input always produces the same output (call twice).

- [x] Task 6: Unit tests — `get_existing_casefile_triage` behaviour
  - File: `tests/unit/pipeline/stages/test_casefile.py`
  - Action: Using a `_FakeObjectStoreClient` (existing in-memory mock pattern), add five tests:
    1. **Returns None** when fake client has no stored object for the derived `case_id`.
    2. **Returns CaseFileTriageV1** when fake client has a valid serialized triage object at the expected path. The stored payload must be a properly finalized `CaseFileTriageV1` — use `serialize_casefile_triage(finalized_casefile)` to produce the bytes (where `finalized_casefile` has a valid `triage_hash` computed via `compute_casefile_triage_hash`). Do NOT store raw/arbitrary bytes — `read_casefile_stage_json_or_none` validates the hash on read and will raise if the payload is invalid.
    3. **Propagates IntegrationError** when fake client raises `IntegrationError` on `get_object_bytes`.
    4. **Propagates CriticalDependencyError** when fake client raises `CriticalDependencyError` on `get_object_bytes` — distinct from `IntegrationError`; must not be swallowed or converted to `None`.
    5. **Propagates ValueError** when fake client returns bytes that fail hash verification (corrupted payload) — store bytes that deserialize as valid JSON but with a tampered `triage_hash` field; assert `ValueError` propagates from `validate_casefile_triage_json`.

- [x] Task 7: Integration test — existing triage skips re-assembly + happy path regression
  - File: `tests/integration/test_casefile_write.py`
  - Action: Add two test scenarios:
    **Scenario A — skip path**: (1) Persist a valid `CaseFileTriageV1` to real MinIO via `persist_casefile_triage_write_once`; (2) call `get_existing_casefile_triage` with the same `gate_input` and assert it returns a non-None `CaseFileTriageV1`; (3) read the object from MinIO and assert payload bytes are bit-identical to the original write; (4) validate `casefile.triage_already_exists` logging in a hot-path scheduler loop unit test that executes the real branch in `__main__.py`.
    **Scenario B — happy path regression**: Before writing this scenario, check whether `tests/integration/test_casefile_write.py` already covers: (a) no pre-existing casefile, (b) assembly + persist returns a valid `OutboxReadyCasefileV1`, (c) object exists in MinIO after write. If existing tests already cover this flow, augment the most relevant existing test to also assert `get_existing_casefile_triage` returns `None` before assembly (i.e. the guard does not false-positive) rather than writing a duplicate test. Only write a new test if no existing coverage exists for the full flow.

### Acceptance Criteria

- [x] AC 1: Given a `GateInputV1` with `action_fingerprint = "harness/harness-cluster/harness_validation/SOURCE_TOPIC/harness-lag-topic/CONSUMER_LAG/TIER_1/group:harness-consumer"`, when `derive_case_id(gate_input=gate_input)` is called, then it returns `"case-harness-harness-cluster-harness-lag-topic-3961489c3af3"` deterministically on every invocation.

- [x] AC 2: Given no triage object exists in MinIO for the derived `case_id`, when `get_existing_casefile_triage(gate_input=gate_input, object_store_client=client)` is called, then it returns `None`.

- [x] AC 3: Given a valid, hash-verified triage object exists in MinIO at `cases/{case_id}/triage.json`, when `get_existing_casefile_triage(gate_input=gate_input, object_store_client=client)` is called, then it returns the stored `CaseFileTriageV1` with `triage_hash` intact.

- [x] AC 4: Given the MinIO client raises `IntegrationError` on `get_object_bytes`, when `get_existing_casefile_triage` is called from within the hot-path loop, then the `IntegrationError` propagates to the `except Exception` handler at `__main__.py:~843`, which logs `event_type="hot_path.case_error"` with `exc_info=True` and continues to the next scope — the error is not swallowed or silently converted to `None`.

- [x] AC 5: Given a triage casefile already exists in MinIO for a `case_id`, when the hot-path loop processes a `gate_input` that produces that same `case_id`, then: the loop body skips assembly + persist + outbox insert + dispatch (`continue` is executed), no `InvariantViolation` is raised, and a structured log event with `event_type="casefile.triage_already_exists"` containing the correct `case_id` and `scope` is emitted.

- [x] AC 6: Given a triage casefile already exists in MinIO, when the hot-path block executes the guard and skips, then the object bytes at `cases/{case_id}/triage.json` in MinIO are bit-identical to the original write (not overwritten or mutated).

- [x] AC 7: Given a `gate_input` for which no triage casefile exists yet, when the hot-path loop processes it, then `assemble_casefile_triage_stage` is called, the casefile is persisted, the outbox entry is created, and dispatch is triggered — no regression in the happy path.

---

## Additional Context

### Dependencies

- `read_casefile_stage_json_or_none` is already imported in `casefile.py` — no import additions needed in that file.
- `CaseFileTriageV1` is already imported in `casefile.py`.
- `ObjectStoreClientProtocol` is already imported in `casefile.py`.
- `GateInputV1` is already imported in `casefile.py`.
- Tasks 1 and 2 must be completed before Tasks 3 and 4 (exports and wiring depend on the renamed/new functions existing).
- Task 5 and 6 (unit tests) can be written against the Task 1/2 implementation.
- Task 7 (integration test) depends on Tasks 1 and 2 being implemented.

### Testing Strategy

**Unit tests (`tests/unit/pipeline/stages/test_casefile.py`):**
- Use `_FakeObjectStoreClient` (in-memory dict-backed mock, existing pattern in the test suite)
- Test `derive_case_id` with two known `action_fingerprint` values (one with `consumer_group`, one without) and assert exact string outputs
- Test `get_existing_casefile_triage` for all five paths: None (missing), found (valid hash-verified payload), propagated `IntegrationError`, propagated `CriticalDependencyError`, propagated `ValueError` (corrupted payload)
- Run with: `uv run pytest -q tests/unit/pipeline/stages/test_casefile.py`

**Integration tests (`tests/integration/test_casefile_write.py`):**
- Requires Docker/testcontainers MinIO instance (existing fixture pattern)
- Write a valid triage artifact first, then verify existence check and guard behaviour
- Assert bit-identical payload (no overwrite) and no exception on re-run
- Run with: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q tests/integration/test_casefile_write.py`

**Full regression after implementation:**
```
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
uv run ruff check
```

### Notes

- The two failing case IDs confirmed from live logs: `case-harness-harness-cluster-harness-lag-topic-3961489c3af3` and `case-harness-harness-cluster-harness-proxy-topic-d12ef3b3956b` — use these as expected values in AC 1 / Task 5 unit tests. The exact `action_fingerprint` inputs that produce these IDs are: `"harness/harness-cluster/harness_validation/SOURCE_TOPIC/harness-lag-topic/CONSUMER_LAG/TIER_1/group:harness-consumer"` and `"harness/harness-cluster/harness_validation/SOURCE_TOPIC/harness-proxy-topic/THROUGHPUT_CONSTRAINED_PROXY/TIER_1"` respectively. Both verified via SHA-256 computation against the derivation formula in `casefile.py:233`.
- Both produce `final_action: OBSERVE` — AG5 dedupe never fires for OBSERVE, confirming `dedupe_store` is not the right lever.
- **`triage_timestamp` frozen-on-first-write (accepted semantic change):** After this fix, the `triage_timestamp` in a persisted casefile represents the time of first encounter, not the current cycle time. Downstream consumers (audit trail, SLA calculations, retention policy) will see a frozen first-encounter timestamp for persistent anomalies. This is the correct and intended behaviour — the first recorded triage is authoritative. No downstream changes are required; the `casefile_retention_policy` contract uses `triage_timestamp` for TTL but this does not affect correctness since TTL is measured from first write.
- **`produced_cases` counter inflated on skip path (accepted):** `__main__.py:867` computes `produced_cases = sum(len(d) for d in decisions_by_scope.values())` at the outer scope, counting every decision regardless of whether the guard fired. After this fix, cycles with pre-existing casefiles will report the same `produced_cases` as if they had assembled — the count reflects decisions evaluated, not casefiles written. This is acceptable; a future improvement could add a `skipped_cases` counter to distinguish, but that is out of scope here.
- **Observability gap (acknowledged):** When `IntegrationError` or `CriticalDependencyError` propagates from the guard call to the `except Exception` handler at `__main__.py:~843`, the existing handler logs `hot_path.case_error` with `action_fingerprint` and `scope` but no `case_id` field — because `case_id` is resolved inside `get_existing_casefile_triage` and not available in the outer scope. This is a minor observability regression. Mitigation: the `casefile.triage_already_exists` log event (emitted on the success path) does carry `case_id`, so MinIO errors are distinguishable from normal skip events by the absence of that prior log entry.
- Party Mode insights incorporated: Winston (extract helper, thin main), Amelia (function signature, single import), Murat (strong positive assertions, error propagation test cases).

## Review Notes

- Adversarial review completed
- Findings: 10 total, 6 fixed, 4 skipped (noise/undecided)
- Resolution approach: auto-fix real findings
