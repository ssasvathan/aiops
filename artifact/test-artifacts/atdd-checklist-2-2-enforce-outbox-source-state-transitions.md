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
  - artifact/implementation-artifacts/2-2-enforce-outbox-source-state-transitions.md
  - src/aiops_triage_pipeline/outbox/state_machine.py
  - src/aiops_triage_pipeline/outbox/repository.py
  - src/aiops_triage_pipeline/outbox/schema.py
  - src/aiops_triage_pipeline/pipeline/stages/outbox.py
  - tests/unit/outbox/test_state_machine.py
  - tests/unit/outbox/test_repository.py
  - _bmad/tea/config.yaml
---

# ATDD Checklist - Epic 2, Story 2.2: Enforce Outbox Source-State Transitions

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Unit (backend Python stack)
**TDD Phase:** GREEN (tests written, implementation verified, all passing)

---

## Story Summary

As a platform operator, I want outbox rows to move through guarded state transitions so that the
publish lifecycle is durable and recovery-safe. The outbox enforces a strict `PENDING_OBJECT →
READY` transition via both in-memory guards (`state_machine.py`) and SQL-level conditional UPDATE
guards (`repository.py::_write_transition`). Invalid transitions, mismatched payloads, and
concurrent races are all rejected by `InvariantViolation`.

**As a** platform operator
**I want** outbox rows to move through guarded state transitions
**So that** publish lifecycle is durable and recovery-safe

---

## Acceptance Criteria

1. Given a casefile triage artifact is persisted, when outbox insertion occurs, then rows are
   created in `PENDING_OBJECT` and transition to `READY` only through source-state-guarded
   operations, and invalid transitions are rejected.

2. Given policy/audit fields are required for replay, when outbox metadata is stored, then required
   identifiers and version references are persisted for downstream consumers, and transition history
   remains queryable for diagnostics.

---

## Stack Detection

- `detected_stack`: **backend** (`pyproject.toml` present, no `package.json`/`playwright.config.*`)
- `tea_execution_mode`: auto → resolved to **sequential**
- No E2E or API (HTTP) tests generated — pure Python unit tests

---

## Test Strategy

| Acceptance Criterion | Test Level | Priority | Scenario                                             |
|----------------------|-----------|---------|------------------------------------------------------|
| AC1                  | Unit       | P0      | `mark_outbox_record_ready` raises for non-PENDING_OBJECT source states (READY, SENT, RETRY, DEAD) |
| AC1                  | Unit       | P0      | `mark_outbox_record_ready` produces correct fields from PENDING_OBJECT |
| AC1                  | Unit       | P1      | `_resolve_transition_now` clamps backward timestamps |
| AC1                  | Unit       | P0      | `insert_pending_object` creates row in PENDING_OBJECT |
| AC1                  | Unit       | P1      | `insert_pending_object` is idempotent on matching payload |
| AC1                  | Unit       | P0      | `insert_pending_object` raises on mismatched object_path |
| AC1, AC2             | Unit       | P0      | `insert_pending_object` raises on mismatched triage_hash |
| AC1                  | Unit       | P0      | `transition_to_ready` succeeds from PENDING_OBJECT |
| AC1                  | Unit       | P1      | `transition_to_ready` is idempotent when already READY |
| AC1                  | Unit       | P0      | `transition_to_ready` raises when source is not PENDING_OBJECT |

---

## Failing Tests Created (RED Phase → GREEN after verification)

### Unit Tests: State Machine Guards (6 tests)

**File:** `tests/unit/outbox/test_state_machine.py`

- **Test:** `test_mark_outbox_record_ready_raises_when_source_status_is_ready`
  - **Status:** GREEN - Passes (implementation guard verified)
  - **Verifies:** `mark_outbox_record_ready` raises `InvariantViolation` when source=READY (cannot double-advance)

- **Test:** `test_mark_outbox_record_ready_raises_when_source_status_is_sent`
  - **Status:** GREEN - Passes (implementation guard verified)
  - **Verifies:** `mark_outbox_record_ready` raises `InvariantViolation` when source=SENT (terminal-state protection)

- **Test:** `test_mark_outbox_record_ready_raises_when_source_status_is_retry`
  - **Status:** GREEN - Passes (implementation guard verified)
  - **Verifies:** `mark_outbox_record_ready` raises `InvariantViolation` when source=RETRY (skip-state protection)

- **Test:** `test_mark_outbox_record_ready_raises_when_source_status_is_dead`
  - **Status:** GREEN - Passes (implementation guard verified)
  - **Verifies:** `mark_outbox_record_ready` raises `InvariantViolation` when source=DEAD (terminal-state protection)

- **Test:** `test_mark_outbox_record_ready_produces_correct_fields_from_pending_object`
  - **Status:** GREEN - Passes
  - **Verifies:** PENDING_OBJECT → READY transition preserves `case_id`, `casefile_object_path`, `triage_hash`, `created_at`, sets `status=READY`, `updated_at=ready_at`, clears `next_attempt_at`/errors

- **Test:** `test_resolve_transition_now_clamps_when_now_is_earlier_than_record_updated_at`
  - **Status:** GREEN - Passes
  - **Verifies:** `_resolve_transition_now` clamps `now` to `record.updated_at` when clock is behind (clock-skew safety)

### Unit Tests: Repository Guards (7 tests)

**File:** `tests/unit/outbox/test_repository.py`

- **Test:** `test_insert_pending_object_creates_row_in_pending_object_status`
  - **Status:** GREEN - Passes
  - **Verifies:** `insert_pending_object` always creates rows in `PENDING_OBJECT` — never `READY` or any other status

- **Test:** `test_insert_pending_object_returns_existing_row_when_payload_matches`
  - **Status:** GREEN - Passes
  - **Verifies:** Idempotent re-insert returns existing row when `casefile_object_path` and `triage_hash` match

- **Test:** `test_insert_pending_object_raises_when_existing_row_has_mismatched_object_path`
  - **Status:** GREEN - Passes
  - **Verifies:** `insert_pending_object` raises `InvariantViolation("existing outbox case_id has different casefile_object_path")` on path mismatch

- **Test:** `test_insert_pending_object_raises_when_existing_row_has_mismatched_triage_hash`
  - **Status:** GREEN - Passes
  - **Verifies:** `insert_pending_object` raises `InvariantViolation("existing outbox case_id has different triage_hash")` on hash mismatch

- **Test:** `test_transition_to_ready_succeeds_from_pending_object`
  - **Status:** GREEN - Passes
  - **Verifies:** `transition_to_ready` produces `status=READY` with correct `updated_at` from `PENDING_OBJECT` source

- **Test:** `test_transition_to_ready_is_idempotent_when_already_ready`
  - **Status:** GREEN - Passes
  - **Verifies:** Calling `transition_to_ready` on an already-READY row returns the current row without error

- **Test:** `test_transition_to_ready_raises_when_source_status_is_not_pending_object`
  - **Status:** GREEN - Passes
  - **Verifies:** In-memory guard (`mark_outbox_record_ready`) raises `InvariantViolation` when source is `SENT`; SQL-level guard is the backstop for concurrent races

---

## Test Execution Evidence

### Full Regression Run

**Command:** `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

**Results:**
```
903 passed in 72.90s (0:01:12)
```

**Summary:**
- Total tests: 903
- Passing: 903
- Failing: 0
- Skipped: 0
- Baseline (Story 2.1): 890
- New tests added: 13
- Status: GREEN phase — all source-state guards verified

---

## Data Factories

No new data factories required. Tests use the per-file `_ready_casefile(case_id)` helper
(established pattern from Story 2.1) returning `OutboxReadyCasefileV1` with `triage_hash="a" * 64`
and `object_path=f"cases/{case_id}/triage.json"`. SQLite in-memory engine (`create_engine
("sqlite+pysqlite:///:memory:")`) is the per-test database fixture.

---

## Mock Requirements

No external service mocking required. Unit tests use SQLite in-memory database — no Postgres,
no Docker, no network calls.

---

## Required `data-testid` Attributes

N/A — backend-only pipeline, no UI components.

---

## Implementation Checklist

### Test: `test_mark_outbox_record_ready_raises_when_source_status_is_ready`

**File:** `tests/unit/outbox/test_state_machine.py`

- [x] Verify `mark_outbox_record_ready` raises `InvariantViolation` with message matching `cannot mark record READY from status=READY`
- [x] Run test: `uv run pytest tests/unit/outbox/test_state_machine.py::test_mark_outbox_record_ready_raises_when_source_status_is_ready`
- [x] Test passes (green phase)

---

### Test: `test_mark_outbox_record_ready_raises_when_source_status_is_sent`

**File:** `tests/unit/outbox/test_state_machine.py`

- [x] Verify `mark_outbox_record_ready` raises for `status=SENT`
- [x] Test passes (green phase)

---

### Test: `test_mark_outbox_record_ready_raises_when_source_status_is_retry`

**File:** `tests/unit/outbox/test_state_machine.py`

- [x] Verify `mark_outbox_record_ready` raises for `status=RETRY`
- [x] Test passes (green phase)

---

### Test: `test_mark_outbox_record_ready_raises_when_source_status_is_dead`

**File:** `tests/unit/outbox/test_state_machine.py`

- [x] Verify `mark_outbox_record_ready` raises for `status=DEAD`
- [x] Test passes (green phase)

---

### Test: `test_mark_outbox_record_ready_produces_correct_fields_from_pending_object`

**File:** `tests/unit/outbox/test_state_machine.py`

- [x] Verify all fields of produced READY record: `status`, `case_id`, `casefile_object_path`, `triage_hash`, `updated_at`, `created_at`, `delivery_attempts`, `next_attempt_at`, `last_error_code`, `last_error_message`
- [x] Test passes (green phase)

---

### Test: `test_resolve_transition_now_clamps_when_now_is_earlier_than_record_updated_at`

**File:** `tests/unit/outbox/test_state_machine.py`

- [x] Create `PENDING_OBJECT` record with `updated_at=12:02`, call `mark_outbox_record_ready(now=12:00)`, verify `ready.updated_at == 12:02` (clamped)
- [x] Test passes (green phase)

---

### Test: `test_insert_pending_object_creates_row_in_pending_object_status`

**File:** `tests/unit/outbox/test_repository.py`

- [x] Verify `status == "PENDING_OBJECT"`, `case_id`, `casefile_object_path`, `triage_hash`, `created_at`, `updated_at`, `delivery_attempts == 0`
- [x] Test passes (green phase)

---

### Test: `test_insert_pending_object_returns_existing_row_when_payload_matches`

**File:** `tests/unit/outbox/test_repository.py`

- [x] Verify idempotent re-insert returns same `case_id`, `triage_hash`, `casefile_object_path` and `status == "PENDING_OBJECT"`
- [x] Test passes (green phase)

---

### Test: `test_insert_pending_object_raises_when_existing_row_has_mismatched_object_path`

**File:** `tests/unit/outbox/test_repository.py`

- [x] Insert with `object_path="cases/case-mismatch-path/triage.json"`, re-insert with `object_path="cases/case-mismatch-path-alt/triage.json"` (same hash), verify `InvariantViolation("different casefile_object_path")`
- [x] Test passes (green phase)

---

### Test: `test_insert_pending_object_raises_when_existing_row_has_mismatched_triage_hash`

**File:** `tests/unit/outbox/test_repository.py`

- [x] Insert with `triage_hash="a"*64`, re-insert with `triage_hash="c"*64` (same path), verify `InvariantViolation("different triage_hash")`
- [x] Test passes (green phase)

---

### Test: `test_transition_to_ready_succeeds_from_pending_object`

**File:** `tests/unit/outbox/test_repository.py`

- [x] Insert PENDING_OBJECT row, call `transition_to_ready`, verify `status == "READY"` and `updated_at == ready_at`
- [x] Test passes (green phase)

---

### Test: `test_transition_to_ready_is_idempotent_when_already_ready`

**File:** `tests/unit/outbox/test_repository.py`

- [x] Insert, transition to READY, call `transition_to_ready` again, verify `status == "READY"` without error
- [x] Test passes (green phase)

---

### Test: `test_transition_to_ready_raises_when_source_status_is_not_pending_object`

**File:** `tests/unit/outbox/test_repository.py`

- [x] Advance row to SENT, call `transition_to_ready`, verify `InvariantViolation("cannot mark record READY from status=SENT")` raised by in-memory guard
- [x] Test passes (green phase)

---

## Running Tests

```bash
# Run all new tests for this story
uv run pytest tests/unit/outbox/test_state_machine.py tests/unit/outbox/test_repository.py -v

# Run state machine guard tests only
uv run pytest tests/unit/outbox/test_state_machine.py -v

# Run repository guard tests only
uv run pytest tests/unit/outbox/test_repository.py -v

# Run full regression
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs

# Run with coverage
uv run pytest --cov=aiops_triage_pipeline.outbox tests/unit/outbox/
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) — N/A for Verification Story

This is a **verification and hardening** story. The implementation (`outbox/repository.py`,
`outbox/state_machine.py`, `outbox/schema.py`) already exists. The ATDD RED phase here means
"tests not yet written" — the tests were written and immediately verified GREEN because the
implementation was pre-existing and correct.

**TEA Agent Responsibilities:**
- Tests written with exact names from story specification
- All 13 tests pass against existing implementation
- No implementation changes required (correct by construction)
- Ruff linting: 0 errors

### GREEN Phase (Complete)

All 13 new tests pass. Full suite: 903 passed, 0 skipped.

### REFACTOR Phase

No refactoring required. Test code follows established patterns:
- `test_{action}_{condition}_{expected}` naming
- Per-test SQLite in-memory engine (no shared state)
- `create_outbox_table(engine)` per-test schema setup
- `_ready_casefile(case_id)` helper for test data

---

## Next Steps

1. **Handoff to dev workflow**: All acceptance criteria verified with explicit test coverage
2. **Run quality gates** before marking story done:
   - `uv run ruff check` — confirmed passing
   - Full pytest: 903 passed, 0 skipped — confirmed passing
3. **Update story status**: Set to `dev-complete` in sprint-status.yaml
4. **Stories 2.3 and 2.4** build on the READY rows that this story's insertion pipeline produces

---

## Knowledge Base References Applied

- **test-quality.md** — `test_{action}_{condition}_{expected}` naming, one assertion focus per test
- **test-levels-framework.md** — Backend stack: unit tests only, no E2E/browser tests
- **data-factories.md** — Per-file `_ready_casefile()` helper pattern, SQLite in-memory per test
- **ci-burn-in.md** — Zero-skip discipline enforced; 0 skipped tests at sprint gate

---

## Notes

- Story 2.2 is a **verification story** — implementation was pre-existing and correct. The ATDD
  artifact adds explicit observability of the source-state invariants.
- The SQL-level source-state guard in `_write_transition` (`UPDATE ... WHERE status IN (...)`) is
  the authoritative enforcement mechanism. The in-memory guards in `state_machine.py` are
  defence-in-depth and fire first in the call chain.
- `test_transition_to_ready_raises_when_source_status_is_not_pending_object` tests the in-memory
  guard path (the most common code path). A concurrent-race test to cover the SQL-level guard
  directly would require two concurrent connections and is out of scope for this unit test suite.

---

**Generated by BMad TEA Agent** - 2026-03-22
