# Story 6.4: LLM Output Schema Validation & Deterministic Fallback

Status: done

## Story

As a platform operator,
I want invalid or unavailable LLM output to produce a deterministic schema-valid fallback DiagnosisReport,
so that the system is resilient to LLM failures and every case has a valid diagnosis stage regardless of LLM
behavior (FR39, FR40).

## Acceptance Criteria

1. **Given** the LLM invocation is fired
   **When** the LLM is unavailable (network/connection failure)
   **Then** a fallback DiagnosisReport is emitted with: `verdict=UNKNOWN`, `confidence=LOW`,
   `reason_codes=("LLM_UNAVAILABLE",)` (FR39)
2. **When** the LLM times out (> 60 seconds, i.e., `asyncio.TimeoutError` from `asyncio.wait_for`)
   **Then** a fallback DiagnosisReport is emitted with: `verdict=UNKNOWN`, `confidence=LOW`,
   `reason_codes=("LLM_TIMEOUT",)` (FR39)
   **And** no retry occurs within the same evaluation cycle (NFR-P4)
3. **When** the LLM returns an HTTP error (non-2xx response)
   **Then** a fallback DiagnosisReport is emitted with: `verdict=UNKNOWN`, `confidence=LOW`,
   `reason_codes=("LLM_ERROR",)` (FR39)
4. **When** the LLM returns malformed or schema-invalid output (`pydantic.ValidationError`)
   **Then** the output was attempted to be validated against `DiagnosisReportV1` schema via
   `model_validate()` (FR40)
   **And** invalid output triggers deterministic fallback with `reason_codes=("LLM_SCHEMA_INVALID",)`
   **And** a gap is recorded: `gaps=("LLM output failed schema validation",)` (FR40)
5. **And** all fallback DiagnosisReports have `triage_hash` populated (same as success path)
6. **And** all fallback DiagnosisReports are schema-valid and written to `diagnosis.json` via
   `persist_casefile_diagnosis_write_once()` with computed hash chain
7. **And** the HealthRegistry `"llm"` component is updated to `DEGRADED` on any failure
8. **And** unit tests verify: each failure scenario (unavailable, timeout, error, malformed), fallback
   `triage_hash` population, `diagnosis.json` write for each scenario, no retry within cycle, gauge
   still balanced in fallback path

## Tasks / Subtasks

- [x] Task 1: Add `_make_and_persist_fallback()` module-level helper to `diagnosis/graph.py` (AC: 5, 6)
  - [x] New sync function `_make_and_persist_fallback(*, reason_codes, case_id, triage_hash, object_store_client, gaps=())` that:
    - Calls `build_fallback_report(reason_codes=reason_codes, case_id=case_id)`
    - Reconstructs with triage_hash: `DiagnosisReportV1.model_validate({**raw.model_dump(mode="json"), "triage_hash": triage_hash, "case_id": case_id, "gaps": list(gaps)})`
    - Builds `CaseFileDiagnosisV1` with placeholder hash → computes hash → rebuilds
    - Calls `persist_casefile_diagnosis_write_once()`
    - Logs `cold_path_fallback_diagnosis_json_written` with `case_id`, `reason_codes`
    - Returns the `DiagnosisReportV1`

- [x] Task 2: Replace `except BaseException` block in `run_cold_path_diagnosis()` with 4 targeted except
  clauses (AC: 1, 2, 3, 4, 7)
  - [x] `except asyncio.TimeoutError` → `reason="cold_path_timeout"`, `reason_codes=("LLM_TIMEOUT",)`,
    call `_make_and_persist_fallback()`, return fallback (do NOT raise)
  - [x] `except pydantic.ValidationError` → `reason="cold_path_schema_invalid"`,
    `reason_codes=("LLM_SCHEMA_INVALID",)`, `gaps=("LLM output failed schema validation",)`,
    call `_make_and_persist_fallback()`, return fallback
  - [x] `except httpx.ConnectError` → `reason="cold_path_unavailable"`,
    `reason_codes=("LLM_UNAVAILABLE",)`, call `_make_and_persist_fallback()`, return fallback
  - [x] `except Exception as exc` (catch-all, replaces `BaseException`) → `reason="cold_path_invocation_failed"`,
    `reason_codes=("LLM_ERROR",)`, call `_make_and_persist_fallback()`, return fallback
  - [x] `finally: llm_inflight_add(-1)` remains unchanged
  - [x] Add `import httpx` and `import pydantic` at module top of `graph.py`
  - [x] Add `from aiops_triage_pipeline.diagnosis.fallback import build_fallback_report` at module top

- [x] Task 3: Update module docstring of `diagnosis/graph.py` (AC: none, code hygiene)
  - [x] Add Story 6.4 to module docstring: "Story 6.4 additions: targeted exception handling per failure
    scenario (timeout, schema-invalid, unavailable, error), fallback DiagnosisReport written to
    diagnosis.json for all failure paths."

- [x] Task 4: Update 3 existing tests in `tests/unit/diagnosis/test_graph.py` (AC: 8)
  - [x] `test_timeout_raises_asyncio_timeout_error` → rewrite: remove `pytest.raises`; verify
    fallback returned with `reason_codes == ("LLM_TIMEOUT",)` and `triage_hash == _FAKE_TRIAGE_HASH`
    and HealthRegistry DEGRADED
  - [x] `test_inflight_gauge_balanced_on_failure` → rewrite: remove `pytest.raises(RuntimeError)`;
    verify fallback returned AND gauge balanced (+1, -1) — the RuntimeError from mock is now caught
    by `except Exception` and returns LLM_ERROR fallback
  - [x] `test_health_registry_degraded_on_generic_exception` → rewrite: remove `pytest.raises(RuntimeError)`;
    verify fallback returned AND `registry.get("llm") == HealthStatus.DEGRADED`

- [x] Task 5: Add 9 new tests to `tests/unit/diagnosis/test_graph.py` (AC: 8)
  - [x] `test_timeout_fallback_writes_diagnosis_json` — simulate timeout, verify `mock_store.put_if_absent`
    called with key containing `"diagnosis.json"`, return value is LLM_TIMEOUT fallback
  - [x] `test_timeout_fallback_has_triage_hash` — simulate timeout, verify `report.triage_hash == _FAKE_TRIAGE_HASH`
  - [x] `test_schema_validation_error_returns_schema_invalid_fallback` — `mock_client.invoke` raises
    `pydantic.ValidationError` (use `DiagnosisReportV1.model_validate({})` to generate one), verify
    `reason_codes == ("LLM_SCHEMA_INVALID",)` and `gaps` contains schema validation message
  - [x] `test_schema_validation_error_writes_diagnosis_json` — same scenario, verify `put_if_absent` called
  - [x] `test_connect_error_returns_unavailable_fallback` — `mock_client.invoke` raises `httpx.ConnectError`,
    verify `reason_codes == ("LLM_UNAVAILABLE",)`
  - [x] `test_connect_error_writes_diagnosis_json` — same, verify `put_if_absent` called
  - [x] `test_http_error_returns_llm_error_fallback` — `mock_client.invoke` raises
    `httpx.HTTPStatusError` (see construction below), verify `reason_codes == ("LLM_ERROR",)`
  - [x] `test_no_retry_on_timeout` — simulate timeout with `mock_wait_for` raising `asyncio.TimeoutError`,
    verify `mock_wait_for` called exactly once (no retry loop)
  - [x] `test_fallback_report_is_schema_valid` — simulate any failure, verify returned report passes
    `DiagnosisReportV1.model_validate(report.model_dump(mode="json"))` without raising

- [x] Task 6: Quality gates
  - [x] `uv run ruff check` — 0 new errors
  - [x] `uv run pytest -q -m "not integration"` — baseline 624 + 9 new = ~633 passed, 0 failures,
    0 skipped

### Review Follow-ups (AI)

- [x] [AI-Review][High] Narrow `except pydantic.ValidationError` handling to LLM-output validation scope; currently it can misclassify internal model/invariant validation failures as `LLM_SCHEMA_INVALID` and set incorrect health reason [`src/aiops_triage_pipeline/diagnosis/graph.py:213`]
- [x] [AI-Review][High] Expand unavailable-path exception mapping beyond `httpx.ConnectError` to include connection timeout/network transport failures so network/connection failures consistently emit `LLM_UNAVAILABLE` [`src/aiops_triage_pipeline/diagnosis/graph.py:227`]
- [x] [AI-Review][Medium] Add a unit test asserting `diagnosis.json` write-once persistence for the generic error path (`LLM_ERROR`) to fully satisfy AC8 coverage for per-scenario persistence verification [`tests/unit/diagnosis/test_graph.py:529`]
- [x] [AI-Review][High] Keep successful LLM results from being overwritten by fallback when persistence has a transient failure: `persist_casefile_diagnosis_write_once()` exceptions in the success path are now fail-loud (degraded + re-raise), not remapped to `LLM_ERROR` fallback [`src/aiops_triage_pipeline/diagnosis/graph.py:286`]
- [x] [AI-Review][Medium] Add regression coverage for success-path persistence failure behavior (first write fails, fallback write succeeds) to enforce critical-dependency semantics and prevent silent downgrade to `LLM_ERROR` fallback [`tests/unit/diagnosis/test_graph.py:597`]
- [x] [AI-Review][Low] Refresh stale review metadata and counters in this story file (Debug Log References/validation block updated to current run counts) [`artifact/implementation-artifacts/6-4-llm-output-schema-validation-and-deterministic-fallback.md:530`]

## Dev Notes

### Developer Context Section

- Story key: `6-4-llm-output-schema-validation-and-deterministic-fallback`
- Story ID: 6.4
- Epic 6 context: Fourth (final) story in Epic 6 (LLM-Enriched Diagnosis). Stories 6.1–6.3 done:
  - 6.1: `LLMClient` with MOCK/LOG/LIVE modes + `LLMFailureMode` injection in `integrations/llm.py`
  - 6.2: Fire-and-forget LangGraph cold path in `diagnosis/graph.py`; denylist enforcement;
    HealthRegistry; in-flight gauge
  - 6.3: `diagnosis/prompt.py` (prompt builder); LIVE mode structured output parsing; `diagnosis.json`
    write-once on SUCCESS; `triage_hash` hash chain
  - 6.4 (this story): Replace bare `except BaseException: raise` with targeted fallback handlers;
    all failure scenarios produce schema-valid fallback + write `diagnosis.json`
- **Scope boundary**:
  - Story 6.4 adds: `_make_and_persist_fallback()` helper; 4 targeted except clauses in
    `run_cold_path_diagnosis()`; 3 test updates + 9 new tests
  - Story 6.4 does NOT add: retry logic, circuit breakers, new config variables, changes to
    `fallback.py`, `llm.py`, `contracts/`, `storage/`
  - Do NOT touch `diagnosis/fallback.py` — it is already correct and complete

### Technical Requirements

**`_make_and_persist_fallback()` — new module-level sync function in `graph.py`:**
```python
def _make_and_persist_fallback(
    *,
    reason_codes: tuple[str, ...],
    case_id: str,
    triage_hash: str,
    object_store_client: ObjectStoreClientProtocol,
    gaps: tuple[str, ...] = (),
) -> DiagnosisReportV1:
    """Build fallback DiagnosisReportV1, inject triage_hash/gaps, write diagnosis.json."""
    raw = build_fallback_report(reason_codes=reason_codes, case_id=case_id)
    report = DiagnosisReportV1.model_validate(
        {**raw.model_dump(mode="json"), "triage_hash": triage_hash, "case_id": case_id, "gaps": list(gaps)}
    )
    casefile_placeholder = CaseFileDiagnosisV1(
        case_id=case_id,
        diagnosis_report=report,
        triage_hash=triage_hash,
        diagnosis_hash=DIAGNOSIS_HASH_PLACEHOLDER,
    )
    computed_hash = compute_casefile_diagnosis_hash(casefile_placeholder)
    casefile = CaseFileDiagnosisV1(
        case_id=case_id,
        diagnosis_report=report,
        triage_hash=triage_hash,
        diagnosis_hash=computed_hash,
    )
    persist_casefile_diagnosis_write_once(object_store_client=object_store_client, casefile=casefile)
    _logger.info(
        "cold_path_fallback_diagnosis_json_written",
        case_id=case_id,
        reason_codes=reason_codes,
    )
    return report
```

**Updated except block in `run_cold_path_diagnosis()` — replaces the existing `except BaseException` block entirely:**
```python
    except asyncio.TimeoutError:
        await health_registry.update("llm", HealthStatus.DEGRADED, reason="cold_path_timeout")
        _logger.warning("cold_path_diagnosis_failed", case_id=case_id, error_type="TimeoutError")
        return _make_and_persist_fallback(
            reason_codes=("LLM_TIMEOUT",),
            case_id=case_id,
            triage_hash=triage_hash,
            object_store_client=object_store_client,
        )
    except pydantic.ValidationError:
        await health_registry.update("llm", HealthStatus.DEGRADED, reason="cold_path_schema_invalid")
        _logger.warning("cold_path_diagnosis_failed", case_id=case_id, error_type="ValidationError")
        return _make_and_persist_fallback(
            reason_codes=("LLM_SCHEMA_INVALID",),
            case_id=case_id,
            triage_hash=triage_hash,
            object_store_client=object_store_client,
            gaps=("LLM output failed schema validation",),
        )
    except httpx.ConnectError:
        await health_registry.update("llm", HealthStatus.DEGRADED, reason="cold_path_unavailable")
        _logger.warning("cold_path_diagnosis_failed", case_id=case_id, error_type="ConnectError")
        return _make_and_persist_fallback(
            reason_codes=("LLM_UNAVAILABLE",),
            case_id=case_id,
            triage_hash=triage_hash,
            object_store_client=object_store_client,
        )
    except Exception as exc:
        await health_registry.update(
            "llm", HealthStatus.DEGRADED, reason="cold_path_invocation_failed"
        )
        _logger.warning(
            "cold_path_diagnosis_failed", case_id=case_id, error_type=type(exc).__name__
        )
        return _make_and_persist_fallback(
            reason_codes=("LLM_ERROR",),
            case_id=case_id,
            triage_hash=triage_hash,
            object_store_client=object_store_client,
        )
    finally:
        llm_inflight_add(-1)
```

**New imports at top of `diagnosis/graph.py`:**
```python
import httpx
import pydantic

from aiops_triage_pipeline.diagnosis.fallback import build_fallback_report
```

**`pydantic.ValidationError` construction for tests** — use the model to self-generate:
```python
import pydantic
try:
    from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
    DiagnosisReportV1.model_validate({})  # missing required fields → raises ValidationError
except pydantic.ValidationError as e:
    validation_error = e
```
Use `AsyncMock(side_effect=validation_error)` for the mock client.

**`httpx.HTTPStatusError` construction for tests:**
```python
import httpx
request = httpx.Request("POST", "http://llm-base-url/diagnose")
response = httpx.Response(500, request=request)
http_error = httpx.HTTPStatusError("500 Internal Server Error", request=request, response=response)
```

**`httpx.ConnectError` construction for tests:**
```python
import httpx
connect_error = httpx.ConnectError("Connection refused")
```

**Updated test: `test_timeout_raises_asyncio_timeout_error` → rewrite body:**
```python
async def test_timeout_raises_asyncio_timeout_error() -> None:
    """asyncio.wait_for timeout → fallback LLM_TIMEOUT returned, registry DEGRADED."""
    registry = HealthRegistry()

    async def slow_coroutine(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(10)
        return {}

    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=slow_coroutine)
    mock_store = _make_mock_store()

    report = await run_cold_path_diagnosis(
        case_id="test-timeout-real",
        triage_excerpt=_make_eligible_excerpt("test-timeout-real"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=mock_store,
        triage_hash=_FAKE_TRIAGE_HASH,
        timeout_seconds=0.01,
    )

    assert report.reason_codes == ("LLM_TIMEOUT",)
    assert report.triage_hash == _FAKE_TRIAGE_HASH
    assert registry.get("llm") == HealthStatus.DEGRADED
    mock_store.put_if_absent.assert_called_once()
```

**Updated test: `test_inflight_gauge_balanced_on_failure` → rewrite body:**
```python
async def test_inflight_gauge_balanced_on_failure() -> None:
    """llm_inflight_add(-1) called in finally even when invocation fails (fallback returned)."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=RuntimeError("llm exploded"))

    with patch(
        "aiops_triage_pipeline.diagnosis.graph.llm_inflight_add",
    ) as mock_gauge:
        report = await run_cold_path_diagnosis(
            case_id="test-gauge-balance",
            triage_excerpt=_make_eligible_excerpt("test-gauge-balance"),
            evidence_summary=_EVIDENCE_SUMMARY,
            llm_client=mock_client,
            denylist=_EMPTY_DENYLIST,
            health_registry=registry,
            object_store_client=_make_mock_store(),
            triage_hash=_FAKE_TRIAGE_HASH,
        )

    # RuntimeError caught by except Exception → LLM_ERROR fallback returned
    assert report.reason_codes == ("LLM_ERROR",)
    # +1 on entry, -1 in finally — always balanced
    assert mock_gauge.call_count == 2
    assert mock_gauge.call_args_list[0][0][0] == 1
    assert mock_gauge.call_args_list[1][0][0] == -1
```

**Updated test: `test_health_registry_degraded_on_generic_exception` → rewrite body:**
```python
async def test_health_registry_degraded_on_generic_exception() -> None:
    """HealthRegistry 'llm' → DEGRADED when invocation raises — fallback returned, not raised."""
    registry = HealthRegistry()
    mock_client = MagicMock(spec=LLMClient)
    mock_client.invoke = AsyncMock(side_effect=RuntimeError("unexpected llm error"))

    report = await run_cold_path_diagnosis(
        case_id="test-degraded-generic",
        triage_excerpt=_make_eligible_excerpt("test-degraded-generic"),
        evidence_summary=_EVIDENCE_SUMMARY,
        llm_client=mock_client,
        denylist=_EMPTY_DENYLIST,
        health_registry=registry,
        object_store_client=_make_mock_store(),
        triage_hash=_FAKE_TRIAGE_HASH,
    )

    assert report.reason_codes == ("LLM_ERROR",)
    assert registry.get("llm") == HealthStatus.DEGRADED
```

### Architecture Compliance

- **`diagnosis/` import boundary**: `graph.py` may add `import httpx` and `import pydantic` — both are
  external packages, not from restricted layers. `graph.py` already imports from `diagnosis/fallback.py`
  was not done in 6.3 — add it now. Allowed per architecture import rules (external libs are unrestricted).
  [Source: `artifact/planning-artifacts/architecture.md` import rules table]
- **`BaseException` → `Exception`**: Changing the catch from `BaseException` to `Exception` means
  `SystemExit` and `KeyboardInterrupt` are no longer caught — they propagate normally, which is CORRECT
  behavior. `BaseException` should never be caught in business logic.
  [Source: Python best practices; architecture NFR-R2: "Critical invariants/dependencies raise
  halt-class exceptions — NEVER catch"]
- **`LLMUnavailable(DegradableError)` exists** in `errors/exceptions.py` but is NOT used here — `graph.py`
  catches raw `httpx.ConnectError` directly. This is intentional for Story 6.4 simplicity. A future
  refactor could wrap in `llm.py` and catch `LLMUnavailable` in `graph.py`.
  [Source: `src/aiops_triage_pipeline/errors/exceptions.py:52`]
- **`_make_and_persist_fallback()` is sync**: `persist_casefile_diagnosis_write_once()` is synchronous.
  The helper does NOT need `async def`. Called from within the async except blocks.
  [Source: `src/aiops_triage_pipeline/storage/casefile_io.py` — no `async` on that function]
- **No retry**: `asyncio.TimeoutError` is caught once and immediately returns fallback. No retry loop.
  This is enforced by the single `try/except/finally` structure — once the exception is caught, the
  finally runs, gauge decremented, and fallback returned. NFR-P4 explicitly says "no retry within
  cycle".
- **Write-once fallback**: `persist_casefile_diagnosis_write_once()` is idempotent — if somehow called
  twice for the same case_id+payload, it succeeds silently. For fallback paths this is fine.
  [Source: `src/aiops_triage_pipeline/storage/casefile_io.py:235`]
- **`httpx.TimeoutException` (httpx internal) vs `asyncio.TimeoutError`**: the `asyncio.wait_for`
  timeout fires at 60s (asyncio.TimeoutError). httpx's internal timeout (also 60s from
  `httpx.AsyncClient(timeout=60.0)`) can fire first → `httpx.ReadTimeout` which is NOT caught
  by `except asyncio.TimeoutError` → falls to `except Exception` → mapped to LLM_ERROR. This is a
  known boundary. For prod, both timeouts are set to 60s; in practice asyncio timeout fires at the
  same wall-clock moment. Do NOT change this behavior — not in scope for 6.4.

### Library / Framework Requirements

Verification date: 2026-03-07.

- **`pydantic.ValidationError` module path**: import via `import pydantic` then catch
  `pydantic.ValidationError`. OR `from pydantic import ValidationError`. Both work.
  In tests, construct with: `DiagnosisReportV1.model_validate({})` — missing required `verdict`,
  `confidence`, `evidence_pack` fields guarantees `ValidationError` is raised.
  [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py`]
- **`httpx==0.28.1`**: pinned in `pyproject.toml`. `httpx.ConnectError` is raised when TCP
  connection to server is refused or fails. `httpx.HTTPStatusError` is raised by `raise_for_status()`
  for non-2xx responses. `httpx.Request("POST", url)` + `httpx.Response(status_code, request=...)` for test construction.
  [Source: `pyproject.toml`; httpx 0.28 docs]
- **`httpx.HTTPStatusError` constructor**: `httpx.HTTPStatusError(message, request=request, response=response)`
  where `request = httpx.Request("POST", "http://test/diagnose")` and
  `response = httpx.Response(500, request=request)`. Both `request` and `response` kwargs required.
  [Source: httpx source `_exceptions.py`]
- **`build_fallback_report(reason_codes, case_id)` signature**: already correct in `fallback.py`;
  `reason_codes` is `tuple[str, ...]` not `list`. Pass as `("LLM_TIMEOUT",)` (tuple).
  `case_id` is `str | None`, defaults to `None`. Always pass `case_id` explicitly in Story 6.4.
  [Source: `src/aiops_triage_pipeline/diagnosis/fallback.py:7`]
- **`gaps` field in `DiagnosisReportV1`**: `tuple[str, ...]`, defaults to `()`. When using
  `model_validate({..., "gaps": list(gaps)})`, Pydantic v2 converts `list` → `tuple` for `tuple[str, ...]`
  fields. Passing `list(gaps)` is correct. An empty list `[]` is valid.
  [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py:28`]
- **`_make_and_persist_fallback()` placement**: define ABOVE `run_cold_path_diagnosis()` in the file
  (module-level, not nested). This is consistent with `build_diagnosis_graph()` and
  `meets_invocation_criteria()` being module-level. Add just above `async def run_cold_path_diagnosis`.

### File Structure Requirements

**Files to modify (only 2):**
- `src/aiops_triage_pipeline/diagnosis/graph.py` — add 3 imports; add `_make_and_persist_fallback()`
  helper; replace `except BaseException` with 4 targeted except clauses; update module docstring
- `tests/unit/diagnosis/test_graph.py` — rewrite 3 existing tests (remove `pytest.raises`); add 9
  new tests; add `import httpx` and `import pydantic` to test file imports

**Files to read before implementing (do not modify):**
- `src/aiops_triage_pipeline/diagnosis/graph.py` — CURRENT FULL IMPLEMENTATION — read carefully before
  editing (especially the `run_cold_path_diagnosis()` try/except/finally structure)
- `src/aiops_triage_pipeline/diagnosis/fallback.py` — `build_fallback_report()` signature; frozen
  `DiagnosisReportV1` construction pattern
- `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — `DiagnosisReportV1` fields; `gaps` field
- `src/aiops_triage_pipeline/errors/exceptions.py` — `LLMUnavailable` exists but NOT used in 6.4
- `tests/unit/diagnosis/test_graph.py` — ALL existing tests to update signatures; understand helpers

**Files NOT to modify:**
- `src/aiops_triage_pipeline/diagnosis/fallback.py` — already complete
- `src/aiops_triage_pipeline/integrations/llm.py` — no changes needed for 6.4
- `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — frozen contract, no changes
- `src/aiops_triage_pipeline/storage/casefile_io.py` — already has all needed functions
- Any file in `pipeline/stages/` — hot path is off-limits

### Previous Story Intelligence

From Story 6.3 (`6-3-structured-diagnosisreport-output-and-evidence-citation.md`):
- **Baseline test count**: After Story 6.3 code review fixes: 618 passed. Current re-run shows **624
  collected** (17 deselected) — run `uv run pytest -q -m "not integration"` to confirm baseline before
  starting.
- **`_FAKE_TRIAGE_HASH = "a" * 64`** already defined in `test_graph.py` — reuse in new tests.
- **`_make_mock_store()` helper** already defined — returns `MagicMock(spec=ObjectStoreClientProtocol)`
  with `put_if_absent.return_value = PutIfAbsentResult.CREATED` — reuse in new tests.
- **Story 6.3 code review M1**: `response.json()` inside `async with` block in `llm.py` — not
  relevant to 6.4 but shows the careful code review expectations.
- **`frozen=True` means no mutation**: use `model_validate({**..., "field": value})` to reconstruct.
  Already done in Story 6.3 for `triage_hash`. Same pattern for `gaps` in fallback path.
- **`build_diagnosis_graph()` must remain inside `try` block**: Story 6.3 code review M1 — preserve.
  Story 6.4 only changes the `except` block, not the `try` body.
- **`_make_and_persist_fallback()` is identical to the success path build logic in Story 6.3** (lines
  128–148 of current `graph.py`). Extract that pattern but without `asyncio`/`await` calls.

From recent commits:
- `f46f654` review: fix code review findings for story 6.3 — current baseline
- `4975e5b` story 6.3: structured DiagnosisReport output and evidence citation
- `82cedbc` review: fix code review findings for story 6.2

Actionable patterns:
- Test discipline: `async def` for async tests, sync `def` for sync tests. All tests in
  `test_graph.py` are `async def` — keep this.
- **`asyncio_mode=auto`**: in `pyproject.toml`. All async tests run automatically — no need for
  `@pytest.mark.asyncio`.
- **Do NOT add `pytest.raises` for the 3 updated tests** — behavior changed from raise to return.
- New tests: use the `mock_client.invoke = AsyncMock(side_effect=...)` pattern from existing tests.
- Existing `_make_eligible_excerpt()` helper: reuse for all new tests.

### Git Intelligence Summary

Recent commits (most recent first):
- `f46f654` review: fix code review findings for story 6.3
- `4975e5b` story 6.3: structured DiagnosisReport output and evidence citation
- `82cedbc` review: fix code review findings for story 6.2

Actionable patterns from recent work:
- Code review typically finds: import ordering (ruff I), missing edge case tests for new branches,
  docstring staleness. Expect similar findings for 6.4.
- The `_make_and_persist_fallback()` function introduces a new code path. Ensure ALL 4 exception
  handlers are covered by targeted tests (not just 1 generic test).
- Story 6.3 added 618 tests; baseline now 624 (6 extra from code review). Confirm baseline before
  starting with `uv run pytest -q -m "not integration"`.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- **Consistency over novelty**: reuse `_make_and_persist_fallback()` for all 4 fallback paths.
  Do NOT duplicate the build+persist block 4 times inline. One helper = DRY.
- **`BaseException` → `Exception`**: the architecture says "Critical dependency failures halt
  pipeline (no silent fallback)". Catching `BaseException` would swallow `SystemExit`. Use `Exception`.
- **Degradable failures**: `LLMUnavailable` is a `DegradableError` — pipeline continues. Story 6.4's
  fallback behavior implements the degraded-mode posture: update HealthRegistry, return fallback, do
  not halt the pipeline task.
- **Test discipline**: avoid placeholder-only coverage. Test each of the 4 failure scenarios
  independently with both reason_code assertion AND `put_if_absent` call assertion.
- **No silent fallbacks for Critical**: the `_make_and_persist_fallback()` MUST successfully write
  `diagnosis.json`. If `persist_casefile_diagnosis_write_once()` itself fails (e.g., object storage
  down), that exception should propagate — it is a `CriticalDependencyError` scenario, not caught
  by the LLM fallback handlers.

### Project Structure Notes

- `src/aiops_triage_pipeline/diagnosis/graph.py` — the ONLY source file to modify; add 3 imports,
  add `_make_and_persist_fallback()` before `run_cold_path_diagnosis()`, replace except block
- `tests/unit/diagnosis/test_graph.py` — update 3 existing tests, add 9 new at bottom; add
  `import httpx` and `import pydantic` to the import section
- No new files needed — `fallback.py` already exists with `build_fallback_report()`
- Ruff import order: stdlib first (`asyncio`, `pydantic`), then third-party (`httpx`, `langgraph`),
  then local (`aiops_triage_pipeline.*`). Add `httpx` and `pydantic` to the existing third-party group.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 6.4` — full AC and FR39/FR40 requirements]
- [Source: `artifact/planning-artifacts/architecture.md` import rules table — diagnosis/ boundaries]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py` — current implementation (Story 6.3 state)]
- [Source: `src/aiops_triage_pipeline/diagnosis/fallback.py` — `build_fallback_report()` signature]
- [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — `DiagnosisReportV1` fields,
  `gaps: tuple[str, ...] = ()`]
- [Source: `src/aiops_triage_pipeline/errors/exceptions.py` — `LLMUnavailable` exists (not used here)]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py` — `persist_casefile_diagnosis_write_once()`,
  `compute_casefile_diagnosis_hash()`, `DIAGNOSIS_HASH_PLACEHOLDER`]
- [Source: `src/aiops_triage_pipeline/models/case_file.py` — `CaseFileDiagnosisV1` frozen model]
- [Source: `tests/unit/diagnosis/test_graph.py` — existing 3 tests to update, helpers to reuse]
- [Source: `artifact/project-context.md` — consistency rules, degradable failure posture, test discipline]
- [Source: `pyproject.toml` — `httpx==0.28.1`, `pydantic==2.12.5`]

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Implementation Plan

- Add a shared fallback helper in `diagnosis/graph.py` to avoid duplicate failure-path persistence logic.
- Replace broad `BaseException` handling with targeted exception-to-reason-code mapping and deterministic fallback returns.
- Expand diagnosis graph unit coverage for timeout/schema/connect/http and no-retry guarantees.
- Validate with lint + unit tests + full Docker-backed regression run (zero skipped tests).

### Debug Log References

- Updated sprint status `6-4-llm-output-schema-validation-and-deterministic-fallback`: `ready-for-dev` -> `in-progress`.
- Implemented Story 6.4 code changes in `src/aiops_triage_pipeline/diagnosis/graph.py`.
- Updated and expanded failure-path tests in `tests/unit/diagnosis/test_graph.py`.
- `uv run ruff check src/aiops_triage_pipeline/diagnosis/graph.py tests/unit/diagnosis/test_graph.py` -> pass.
- `uv run pytest -q tests/unit/diagnosis/test_graph.py` -> `30 passed`.
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` -> `654 passed, 0 skipped`.

### Completion Notes List

- Implemented `_make_and_persist_fallback()` to produce schema-valid fallback reports with triage hash + optional gaps and persist deterministic `diagnosis.json`.
- Replaced `except BaseException` with targeted handlers:
  - `asyncio.TimeoutError` -> `LLM_TIMEOUT`
  - `pydantic.ValidationError` -> `LLM_SCHEMA_INVALID` + schema-validation gap
  - `httpx.ConnectError` -> `LLM_UNAVAILABLE`
  - generic `Exception` -> `LLM_ERROR`
- Ensured all failure paths update HealthRegistry to `DEGRADED`, persist fallback diagnosis, and keep inflight gauge balanced.
- Rewrote 3 existing tests for return-based fallback behavior and added 9 new tests for all required failure scenarios and persistence/no-retry/schema validity checks.
- Full regression completed with zero skipped tests after running Docker-enabled suite outside sandbox constraints.
- Applied AI review follow-up fixes:
  - Scoped `LLM_SCHEMA_INVALID` mapping to invoke/output-validation errors only.
  - Mapped all `httpx.TransportError` failures to `LLM_UNAVAILABLE`.
  - Added `LLM_ERROR` persistence coverage and regression test for internal-validation classification.
- Validation rerun after fixes: `29` diagnosis graph unit tests passed and full regression passed (`653 passed, 0 skipped`).
- Follow-up fix pack (this turn):
  - Scoped fallback mapping to LLM invocation/output failures only; success-path persistence/invariant failures now degrade and re-raise (no fallback remap).
  - Added regression test for success-path persistence failure to enforce fail-loud behavior.
  - Validation rerun passed: `30` diagnosis graph unit tests, full regression `654 passed, 0 skipped`.

### Senior Developer Review (AI)

- Outcome: Approved
- Summary:
  - High/medium/low follow-ups from prior review are fixed and validated.
  - Success-path persistence failure now fails loud (no `LLM_ERROR` fallback remap).
  - Regression coverage added for this boundary; story metadata refreshed.
- Validation run:
  - `uv run ruff check src/aiops_triage_pipeline/diagnosis/graph.py tests/unit/diagnosis/test_graph.py` -> pass
  - `uv run pytest -q tests/unit/diagnosis/test_graph.py` -> `30 passed`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` -> `654 passed, 1 warning, 0 skipped`

### File List

- src/aiops_triage_pipeline/diagnosis/graph.py
- tests/unit/diagnosis/test_graph.py
- artifact/implementation-artifacts/sprint-status.yaml
- artifact/implementation-artifacts/6-4-llm-output-schema-validation-and-deterministic-fallback.md

## Change Log

- 2026-03-07: Final code-review closeout completed (approved, no open high/medium findings); status moved to done and sprint-status synced.
- 2026-03-07: Implemented follow-up fix pack from re-review (critical fail-loud persistence path, new regression test, metadata refresh); status moved to review; validation passed (`30` unit, `654` full, `0 skipped`).
- 2026-03-07: Senior developer re-review executed; status moved to in-progress; 3 follow-up items added (1 High, 1 Medium, 1 Low).
- 2026-03-08: Implemented Story 6.4 fallback schema-validation and deterministic fallback flow; expanded tests; passed full regression (650 passed, 0 skipped).
- 2026-03-07: Senior developer review executed; status moved to in-progress; 3 follow-up items added (2 High, 1 Medium).
- 2026-03-07: Fixed all AI review follow-ups; status moved back to review; regression rerun passed (653 passed, 0 skipped).
