# Story 3.2: Deterministic Fallback Diagnosis

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want a deterministic fallback diagnosis when LLM is unavailable,
so that case file completeness and hash-chain integrity are preserved regardless of LLM availability.

## Acceptance Criteria

1. **Given** an LLM invocation fails (timeout, error, service unavailable)
   **When** the cold-path processes a BASELINE_DEVIATION case
   **Then** `run_cold_path_diagnosis()` in `diagnosis/graph.py` falls back to deterministic diagnosis (FR28)
   **And** the fallback produces a valid `DiagnosisReportV1` persisted via `persist_casefile_diagnosis_write_once()` — preserving SHA-256 hash-chain integrity (NFR-A1)
   **And** the fallback path is already fully wired in `graph.py` via `_persist_fallback_and_record()` — no changes to graph.py are expected
   **And** `build_fallback_report()` in `diagnosis/fallback.py` already handles all anomaly families by accepting generic `reason_codes` — confirm it produces a correct report for BASELINE_DEVIATION cases

2. **Given** the fallback diagnosis path for BASELINE_DEVIATION
   **When** `build_fallback_report()` is called with BASELINE_DEVIATION-specific reason codes
   **Then** it follows the identical fallback pattern used for existing anomaly families (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY)
   **And** returns `DiagnosisReportV1` with `verdict="UNKNOWN"`, `confidence=DiagnosisConfidence.LOW`, `fault_domain=None`, and the provided `reason_codes`
   **And** `triage_hash=None` is intentional — hash chain is injected by `_make_and_persist_fallback()` in `graph.py` (not by `build_fallback_report()`)
   **And** the case file remains complete and structurally valid after hash injection and persistence

3. **Given** LLM failure occurs during BASELINE_DEVIATION case processing
   **When** the fallback is triggered
   **Then** no import path to the hot path exists (D6 invariant — `diagnosis/` is a cold-path leaf; nothing in hot-path imports from `diagnosis/`)
   **And** no shared state is accessed by `build_fallback_report()`
   **And** no conditional wait occurs — `build_fallback_report()` is a synchronous pure function called from within the existing async fallback handlers in `graph.py`

4. **Given** unit tests in `tests/unit/diagnosis/test_fallback.py`
   **When** tests are executed
   **Then** `test_build_fallback_report_baseline_deviation_timeout()` verifies BASELINE_DEVIATION case with `reason_codes=("LLM_TIMEOUT",)` returns `verdict="UNKNOWN"`, `confidence=LOW`
   **And** `test_build_fallback_report_baseline_deviation_unavailable()` verifies `reason_codes=("LLM_UNAVAILABLE",)` returns correct schema
   **And** `test_build_fallback_report_baseline_deviation_error()` verifies `reason_codes=("LLM_ERROR",)` returns correct schema
   **And** all 3 tests verify `triage_hash is None` (hash injected by graph.py, not fallback.py)
   **And** all 3 tests verify the returned `DiagnosisReportV1` passes `model_validate()` round-trip (schema validity)
   **And** all existing 7 tests in `test_fallback.py` continue to pass without modification

5. **Given** unit tests in `tests/unit/diagnosis/test_graph.py`
   **When** tests are executed
   **Then** `test_run_cold_path_diagnosis_baseline_deviation_timeout_produces_fallback()` verifies that with a BASELINE_DEVIATION excerpt and a `asyncio.TimeoutError`-raising LLM client, `run_cold_path_diagnosis()` returns a `DiagnosisReportV1` with `reason_codes=("LLM_TIMEOUT",)` and `triage_hash == _FAKE_TRIAGE_HASH` (hash injected)
   **And** `test_run_cold_path_diagnosis_baseline_deviation_unavailable_produces_fallback()` verifies with `httpx.TransportError` that fallback is triggered with `reason_codes=("LLM_UNAVAILABLE",)` and `triage_hash` populated
   **And** both tests verify `diagnosis.json` is persisted via `object_store_client.put_if_absent` being called once
   **And** all existing graph tests (see current count: 1314 total unit tests) continue to pass without modification

## Tasks / Subtasks

- [x] Task 1: Verify `diagnosis/fallback.py` handles BASELINE_DEVIATION without code changes (AC: 1, 2, 3)
  - [x] 1.1 Open `src/aiops_triage_pipeline/diagnosis/fallback.py` — confirm `build_fallback_report(reason_codes, case_id)` is anomaly-family-agnostic (no family-specific branching)
  - [x] 1.2 Call `build_fallback_report(("LLM_TIMEOUT",), case_id="bd-test-001")` mentally and trace the return — confirm `verdict="UNKNOWN"`, `confidence=LOW`, `triage_hash=None`, `fault_domain=None`
  - [x] 1.3 Confirm `diagnosis/graph.py` `_make_and_persist_fallback()` already injects `triage_hash` into the fallback report (line ~130 in graph.py: `DiagnosisReportV1.model_validate({**raw.model_dump(), "triage_hash": triage_hash, ...})`)
  - [x] 1.4 Confirm that `run_cold_path_diagnosis()` in `graph.py` already handles `asyncio.TimeoutError`, `pydantic.ValidationError`, `httpx.TransportError`, and generic `Exception` via `_persist_fallback_and_record()` — ALL anomaly families handled identically (no BASELINE_DEVIATION-specific branching needed)
  - [x] 1.5 Run `uv run ruff check src/aiops_triage_pipeline/diagnosis/` — confirm 0 violations (no code changes expected)
  - [x] 1.6 Run `uv run pytest tests/unit/diagnosis/test_fallback.py tests/unit/diagnosis/test_graph.py -v` — confirm all existing tests pass before adding new ones

- [x] Task 2: Add BASELINE_DEVIATION-specific unit tests to `tests/unit/diagnosis/test_fallback.py` (AC: 4)
  - [x] 2.1 Open `tests/unit/diagnosis/test_fallback.py`
  - [x] 2.2 Add `test_build_fallback_report_baseline_deviation_timeout()` — constructs report with `("LLM_TIMEOUT",)`, asserts `verdict == "UNKNOWN"`, `confidence == DiagnosisConfidence.LOW`, `reason_codes == ("LLM_TIMEOUT",)`, `triage_hash is None`, `case_id == "bd-case-001"` (provide case_id)
  - [x] 2.3 Add `test_build_fallback_report_baseline_deviation_unavailable()` — constructs report with `("LLM_UNAVAILABLE",)`, asserts same schema invariants, `case_id is None` (no case_id provided — test default path)
  - [x] 2.4 Add `test_build_fallback_report_baseline_deviation_error()` — constructs report with `("LLM_ERROR",)`, asserts same schema invariants
  - [x] 2.5 For all 3 new tests: call `DiagnosisReportV1.model_validate(report.model_dump(mode="json"))` to verify round-trip schema validity
  - [x] 2.6 All imports at module level (retro L4/lesson from Epic 2 — confirmed pattern in test_fallback.py)
  - [x] 2.7 Run `uv run pytest tests/unit/diagnosis/test_fallback.py -v` — confirm all 10 tests pass (7 existing + 3 new)
  - [x] 2.8 Run `uv run ruff check tests/unit/diagnosis/test_fallback.py` — confirm 0 lint violations

- [x] Task 3: Add BASELINE_DEVIATION fallback tests to `tests/unit/diagnosis/test_graph.py` (AC: 5)
  - [x] 3.1 Open `tests/unit/diagnosis/test_graph.py` — locate existing fallback test patterns (e.g., `test_run_cold_path_diagnosis_timeout_returns_fallback`)
  - [x] 3.2 Add helper `_make_baseline_deviation_excerpt(case_id: str = "bd-001") -> TriageExcerptV1` — mirrors `_make_eligible_excerpt()` but with `anomaly_family="BASELINE_DEVIATION"` and at least one `Finding` with `reason_codes=("BASELINE_DEV:consumer_lag.offset:HIGH",)` (from `contracts.gate_input.Finding`)
  - [x] 3.3 Add `test_run_cold_path_diagnosis_baseline_deviation_timeout_produces_fallback()`:
    - Create `mock_client` where `invoke` raises `asyncio.TimeoutError` (use `AsyncMock(side_effect=asyncio.TimeoutError())`)
    - Call `run_cold_path_diagnosis(case_id="bd-001", triage_excerpt=_make_baseline_deviation_excerpt(), ..., triage_hash=_FAKE_TRIAGE_HASH)`
    - Assert `report.reason_codes == ("LLM_TIMEOUT",)` and `report.triage_hash == _FAKE_TRIAGE_HASH`
    - Assert `mock_store.put_if_absent` called once (diagnosis.json persisted)
  - [x] 3.4 Add `test_run_cold_path_diagnosis_baseline_deviation_unavailable_produces_fallback()`:
    - Create `mock_client` where `invoke` raises `httpx.ConnectError("simulated")` (subclass of `httpx.TransportError`)
    - Call `run_cold_path_diagnosis(...)` with BASELINE_DEVIATION excerpt
    - Assert `report.reason_codes == ("LLM_UNAVAILABLE",)` and `report.triage_hash == _FAKE_TRIAGE_HASH`
    - Assert `mock_store.put_if_absent` called once
  - [x] 3.5 All imports at module level — `httpx.ConnectError` already importable via existing `import httpx`; `asyncio.TimeoutError` already in stdlib
  - [x] 3.6 Run `uv run pytest tests/unit/diagnosis/test_graph.py -v` — all existing tests + 2 new pass
  - [x] 3.7 Run `uv run ruff check tests/unit/diagnosis/test_graph.py` — 0 violations

- [x] Task 4: Full regression run (AC: inline)
  - [x] 4.1 Run `uv run pytest tests/unit/ -q` — confirm 1319 passed (1314 existing + 5 new), 0 failures, 0 skipped
  - [x] 4.2 Run `uv run ruff check src/ tests/` — 0 lint violations across entire source tree and test suite

## Dev Notes

### Critical Finding: `build_fallback_report()` Is Already Fully Family-Agnostic

**The most important architectural constraint for this story is that NO production code changes are required.**

`diagnosis/fallback.py::build_fallback_report()` accepts only `reason_codes: tuple[str, ...]` and `case_id: str | None`. It has no anomaly family parameter, no conditional branching on family, and no reference to `BASELINE_DEVIATION` anywhere. The function is completely family-agnostic by design.

The full cold-path fallback pipeline for BASELINE_DEVIATION is already wired in `graph.py`:

1. `run_cold_path_diagnosis()` receives the BASELINE_DEVIATION `TriageExcerptV1`
2. On failure (timeout/error/unavailable), calls `_persist_fallback_and_record(reason_codes=("LLM_TIMEOUT",), ...)`
3. `_persist_fallback_and_record()` calls `_make_and_persist_fallback()`
4. `_make_and_persist_fallback()` calls `build_fallback_report(reason_codes, case_id)` → returns raw `DiagnosisReportV1` with `triage_hash=None`
5. Injects `triage_hash` via `DiagnosisReportV1.model_validate({**raw.model_dump(), "triage_hash": triage_hash, "case_id": case_id, "gaps": fallback_gaps})`
6. Computes `diagnosis_hash` via `compute_casefile_diagnosis_hash(casefile_placeholder)`
7. Persists `CaseFileDiagnosisV1` via `persist_casefile_diagnosis_write_once()`
8. Logs `cold_path_fallback_diagnosis_json_written` with `case_id`, `reason_codes`, `triage_hash`, `diagnosis_hash`

**This story is verification + test coverage only.** The fallback already works for BASELINE_DEVIATION; the story adds explicit test evidence to prove it.

### The `build_fallback_report()` Return Shape

```python
# diagnosis/fallback.py
def build_fallback_report(
    reason_codes: tuple[str, ...],
    case_id: str | None = None,
) -> DiagnosisReportV1:
    return DiagnosisReportV1(
        case_id=case_id,
        verdict="UNKNOWN",
        fault_domain=None,
        confidence=DiagnosisConfidence.LOW,
        evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
        next_checks=(),
        gaps=(),
        reason_codes=reason_codes,
        triage_hash=None,  # Injected by graph.py, not here
    )
```

For BASELINE_DEVIATION tests: pass `reason_codes=("LLM_TIMEOUT",)` or `("LLM_UNAVAILABLE",)` or `("LLM_ERROR",)` — the exact same codes used for other families. The function does not need or accept an `anomaly_family` parameter.

### `_make_baseline_deviation_excerpt()` Helper Pattern

Use `contracts.gate_input.Finding` (NOT `models.anomaly.AnomalyFinding`) to construct `TriageExcerptV1.findings` — this is the established pattern from `test_graph.py` and `test_prompt.py`:

```python
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.contracts.enums import CriticalityTier, Environment

def _make_baseline_deviation_excerpt(case_id: str = "bd-001") -> TriageExcerptV1:
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-x",
        topic="payments.events",
        anomaly_family="BASELINE_DEVIATION",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="OWN::Streaming::Payments",
        sustained=True,
        evidence_status_map={},
        findings=(
            Finding(
                finding_id="BD-001",
                name="baseline_deviation_correlated",
                is_anomalous=True,
                severity="LOW",
                is_primary=False,
                evidence_required=(),
                reason_codes=("BASELINE_DEV:consumer_lag.offset:HIGH",),
            ),
        ),
        triage_timestamp=datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc),
    )
```

`TriageExcerptV1.anomaly_family` was extended to include `"BASELINE_DEVIATION"` in Story 3-1. This Literal is already live.

### Mock LLM Client for Failure Injection in `test_graph.py`

The existing test pattern uses `AsyncMock` to simulate LLM failures:

```python
# Timeout simulation
mock_client = MagicMock(spec=LLMClient)
mock_client.invoke = AsyncMock(side_effect=asyncio.TimeoutError())

# Transport error (LLM_UNAVAILABLE)
mock_client.invoke = AsyncMock(side_effect=httpx.ConnectError("simulated unavailability"))
```

These map to the existing exception handlers in `run_cold_path_diagnosis()`:
- `asyncio.TimeoutError` → `reason_codes=("LLM_TIMEOUT",)`, `fallback_reason="LLM_TIMEOUT"`
- `httpx.TransportError` (and subclasses including `ConnectError`) → `reason_codes=("LLM_UNAVAILABLE",)`, `fallback_reason="LLM_UNAVAILABLE"`

Note: the `asyncio.wait_for()` in `run_cold_path_diagnosis()` catches `asyncio.TimeoutError` directly — but `mock_client.invoke` raising `asyncio.TimeoutError` will propagate through `graph.ainvoke()` and be caught by the outer `except asyncio.TimeoutError`. This is consistent with how `_make_read_timeout_error()` is used in existing tests.

### `object_store_client.put_if_absent` Call Count

In fallback scenarios, `persist_casefile_diagnosis_write_once()` calls `object_store_client.put_if_absent` once for the diagnosis.json. The mock store `_make_mock_store()` returns `PutIfAbsentResult.CREATED`. Assert `mock_store.put_if_absent.call_count == 1` to confirm persistence happened exactly once.

Note: the `write-once` invariant in `persist_casefile_diagnosis_write_once()` means duplicate calls return `ALREADY_EXISTS` without overwriting — this is already tested in the existing cold-path tests. The fallback path follows the same write-once semantics.

### D6 Invariant Verification (No Hot-Path Coupling)

The D6 architectural invariant ("no import path to hot path, no shared state, no conditional wait") is satisfied for the fallback path:

1. `diagnosis/fallback.py` imports only from `contracts/diagnosis_report.py` and `contracts/enums.py` — both pure data contracts with no hot-path logic
2. `build_fallback_report()` is a synchronous pure function with no async operations, no global state reads, no external I/O
3. The function is called from within `_make_and_persist_fallback()` in `graph.py` which is already async cold-path — the call is non-blocking from the caller's perspective
4. No `asyncio.wait()`, no `asyncio.gather()`, no blocking I/O — pure in-memory construction

### Hash-Chain Integrity Flow (NFR-A1)

The full hash-chain for a BASELINE_DEVIATION fallback case:

```
triage.json                     triage_hash (SHA-256 of triage.json)
     ↓                                ↓
ColdPathDiagnosisState      ──→  _make_and_persist_fallback(triage_hash=triage_hash)
                                        ↓
                             DiagnosisReportV1(triage_hash=triage_hash, ...)  ← hash injected
                                        ↓
                             CaseFileDiagnosisV1(
                               triage_hash=triage_hash,
                               diagnosis_hash=PLACEHOLDER,     ← placeholder for hash computation
                             )
                                        ↓
                             compute_casefile_diagnosis_hash(casefile_placeholder)
                                        ↓
                             CaseFileDiagnosisV1(
                               triage_hash=triage_hash,
                               diagnosis_hash=computed_hash,   ← final hash
                             )
                                        ↓
                             persist_casefile_diagnosis_write_once() → diagnosis.json
```

For tests: verify `report.triage_hash == _FAKE_TRIAGE_HASH` after `run_cold_path_diagnosis()` returns. This confirms the hash-chain injection happened correctly through the fallback path.

### What NOT to Implement (Scope Boundaries)

This story does NOT require:
- Any modifications to `diagnosis/fallback.py` — it is already correct
- Any modifications to `diagnosis/graph.py` — fallback wiring is already correct for all families
- Any new modules or files in `diagnosis/`
- Any modifications to `contracts/triage_excerpt.py` — BASELINE_DEVIATION Literal already added in Story 3-1
- Any modifications to `__main__.py` — cold-path handler already processes all families
- Any documentation updates beyond what's already done in Story 3-1

**Production code changes: ZERO. Test additions: 5 new tests (3 in test_fallback.py + 2 in test_graph.py).**

### structlog Logger Instantiation (Epic 2 Retro TD-3 / L3)

`build_fallback_report()` is a pure function — no logging, no structlog. No risk of the module-level logger instantiation issue from Epic 2.

If any new logging is added during implementation (none expected), instantiate structlog loggers **inside the function body** to support test fixture log reconfiguration.

### Exception Re-Raise Pattern (Epic 2 Retro TD-4 / L4)

If implementing any except blocks in new test code: use bare `raise` (not `raise exc`) to preserve traceback chain. No new `except` blocks expected in this story.

### Current Test Count

1,314 unit tests collected. This story targets +5 new tests:
- `test_fallback.py`: +3 new tests (Tasks 2.2, 2.3, 2.4)
- `test_graph.py`: +2 new tests (Tasks 3.3, 3.4)
- **Target total: 1,319 tests passing. Zero regressions required.**

### Project Structure Notes

All changes are additive to existing test files — no new files created:

**Files to modify:**
- `tests/unit/diagnosis/test_fallback.py` — add 3 new BASELINE_DEVIATION fallback tests
- `tests/unit/diagnosis/test_graph.py` — add 2 new BASELINE_DEVIATION graph fallback integration tests

**Files to verify (no changes expected):**
- `src/aiops_triage_pipeline/diagnosis/fallback.py` — verify already handles BASELINE_DEVIATION
- `src/aiops_triage_pipeline/diagnosis/graph.py` — verify fallback wiring works for all families

**Alignment with project structure boundaries:**
- `artifact/planning-artifacts/architecture/project-structure-boundaries.md`: FR25-FR28 are explicitly mapped to "No new files — existing cold-path handles new anomaly_family"
- This story is pure test-coverage delivery confirming that boundary constraint was correctly implemented in Story 3-1

### References

- Epic 3 Story 3.2 requirements: `artifact/planning-artifacts/epics.md` §Epic 3, Story 3.2
- FR28: Deterministic fallback diagnosis on LLM failure
- NFR-A1: SHA-256 hash-chain integrity for BASELINE_DEVIATION case files
- `diagnosis/fallback.py`: `src/aiops_triage_pipeline/diagnosis/fallback.py`
- `diagnosis/graph.py` — `_make_and_persist_fallback()`, `_persist_fallback_and_record()`, `run_cold_path_diagnosis()`: `src/aiops_triage_pipeline/diagnosis/graph.py`
- `contracts/diagnosis_report.py`: `src/aiops_triage_pipeline/contracts/diagnosis_report.py`
- `contracts/triage_excerpt.py`: `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
- Existing fallback tests: `tests/unit/diagnosis/test_fallback.py`
- Existing graph tests: `tests/unit/diagnosis/test_graph.py`
- Story 3-1 Dev Notes (completed): `artifact/implementation-artifacts/3-1-baseline-deviation-llm-diagnosis-prompt-and-processing.md`
- Architecture project structure boundaries: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`
- Architecture core decisions D6: `artifact/planning-artifacts/architecture/core-architectural-decisions.md`
- Epic 2 Retrospective (L3, L4, L7 lessons): `artifact/implementation-artifacts/epic-2-retro-2026-04-05.md`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- VERIFICATION ONLY: Zero production code changes required or made.
- Task 1: Confirmed `build_fallback_report()` in `diagnosis/fallback.py` is fully anomaly-family-agnostic — accepts only `reason_codes` and `case_id`, no branching on anomaly family. `ruff check` passed with 0 violations.
- Task 1: Confirmed `run_cold_path_diagnosis()` in `graph.py` handles `asyncio.TimeoutError`, `pydantic.ValidationError`, `httpx.TransportError`, and generic `Exception` identically for all anomaly families via `_persist_fallback_and_record()`. `triage_hash` injected at `_make_and_persist_fallback()` line ~133.
- Task 2: 3 BASELINE_DEVIATION tests already present in `tests/unit/diagnosis/test_fallback.py` (added in ATDD step): `test_build_fallback_report_baseline_deviation_timeout`, `test_build_fallback_report_baseline_deviation_unavailable`, `test_build_fallback_report_baseline_deviation_error`. All 10 tests pass. Imports at module level. Round-trip `model_validate` verified.
- Task 3: 2 BASELINE_DEVIATION graph tests already present in `tests/unit/diagnosis/test_graph.py` (added in ATDD step): `test_run_cold_path_diagnosis_baseline_deviation_timeout_produces_fallback`, `test_run_cold_path_diagnosis_baseline_deviation_unavailable_produces_fallback`. Both use `_make_baseline_deviation_excerpt()` helper. `asyncio.TimeoutError` → `LLM_TIMEOUT`, `httpx.ConnectError` → `LLM_UNAVAILABLE`. Both assert `triage_hash == _FAKE_TRIAGE_HASH` and `put_if_absent.assert_called_once()`.
- Task 4: Full regression run confirmed 1319 passed, 0 failures, 0 skipped. `uv run ruff check src/ tests/` — 0 violations.
- All 5 ACs satisfied. D6 invariant (no hot-path coupling) confirmed. NFR-A1 hash-chain integrity confirmed via `triage_hash` injection in `_make_and_persist_fallback()`.

### Code Review Notes (2026-04-05)

Adversarial code review performed by claude-sonnet-4-6. All findings fixed:

- **M-1 [FIXED]**: Removed duplicate `assert clean_fact in report.evidence_pack.facts` assertion (copy-paste artifact) in `test_llm_narrative_sanitization_uses_active_denylist` — `test_graph.py` line 1097.
- **M-2 [FIXED]**: Added `assert "PRIMARY_DIAGNOSIS_ABSENT" in report.gaps` to both new BASELINE_DEVIATION graph tests. Every other fallback test (8 total) asserts this gap; `_make_and_persist_fallback()` always injects it. Omission was an inconsistency with the established pattern, confirmed empirically.
- **L-1 [FIXED]**: Added `assert registry.get("llm") == HealthStatus.DEGRADED` to both new BD graph tests, consistent with `test_timeout_raises_asyncio_timeout_error` and `test_health_registry_degraded_on_generic_exception`.
- **L-2 [FIXED]**: Added `artifact/implementation-artifacts/sprint-status.yaml` to story File List (was modified in git but missing from list).
- **L-3 [FIXED]**: Added `assert report.case_id is None` to `test_build_fallback_report_baseline_deviation_error`, consistent with `test_build_fallback_report_baseline_deviation_unavailable` (same call signature, same expected behavior).

Post-fix: 1319 unit tests pass, 0 failures, 0 skipped. `ruff check src/ tests/` — 0 violations.

### File List

tests/unit/diagnosis/test_fallback.py
tests/unit/diagnosis/test_graph.py
artifact/implementation-artifacts/sprint-status.yaml
