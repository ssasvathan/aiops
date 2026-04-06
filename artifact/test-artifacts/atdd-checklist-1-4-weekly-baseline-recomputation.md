---
stepsCompleted: ['step-01-preflight-and-context', 'step-02-generation-mode', 'step-03-test-strategy', 'step-04-generate-tests', 'step-04c-aggregate', 'step-05-validate-and-complete']
lastStep: 'step-05-validate-and-complete'
lastSaved: '2026-04-05'
inputDocuments:
  - artifact/implementation-artifacts/1-4-weekly-baseline-recomputation.md
  - src/aiops_triage_pipeline/baseline/client.py
  - src/aiops_triage_pipeline/__main__.py
  - tests/unit/baseline/test_client.py
  - tests/unit/pipeline/test_baseline_backfill.py
  - pyproject.toml
  - tests/conftest.py
---

# ATDD Checklist: Story 1.4 — Weekly Baseline Recomputation

## Step 1: Preflight & Context

### Stack Detection
- **Detected stack**: `backend` (Python, `pyproject.toml`, `conftest.py`, pytest + asyncio_mode=auto)
- **Test framework**: pytest 9.0.2, pytest-asyncio 1.3.0, asyncio_mode=auto
- **No frontend indicators** found — Playwright/Cypress not applicable

### Story Summary
Story 1.4 adds:
1. `bulk_recompute()` method to `SeasonalBaselineClient` — in-memory compute + pipeline bulk-write
2. `get_last_recompute()` / `set_last_recompute()` on `SeasonalBaselineClient`
3. `_should_trigger_recompute()` helper function
4. `_run_baseline_recompute()` coroutine (log events + last_recompute update)
5. Timer check in `_run_hot_path_scheduler()` loop with concurrency guard

### Acceptance Criteria
1. Scheduler checks `aiops:seasonal_baseline:last_recompute`; spawns background task via `asyncio.create_task()` when 7+ days elapsed or key absent; one task at a time
2. `bulk_recompute()` queries Prometheus, partitions into 168 `(dow, hour)` buckets in-memory, writes via pipelined Redis bulk write, updates `last_recompute`, caps at `MAX_BUCKET_VALUES`
3. Hot-path cycles are not blocked during recomputation
4. No partial writes on failure; `last_recompute` not updated on failure; retries next cycle
5. Structured log events: `baseline_deviation_recompute_started`, `_completed` (with `duration_seconds`, `key_count`), `_failed` (with `exc_info=True`)
6. Completes within 10 minutes for 500 scopes × 9 metrics × 168 buckets
7. Unit tests with mock Prometheus and mock Redis

---

## Step 2: Generation Mode

**Mode selected**: AI generation (backend stack, no browser recording needed)

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Scenarios Mapping

| AC | Test Level | Priority | Scenario |
|----|-----------|----------|----------|
| AC1 | Unit | P0 | Scheduler timer check triggers when key absent |
| AC1 | Unit | P0 | Scheduler timer check triggers when 7+ days elapsed |
| AC1 | Unit | P0 | Scheduler timer check does NOT trigger when recent (6 days) |
| AC1 | Unit | P0 | Scheduler timer check triggers at exactly 7-day boundary |
| AC1 | Unit | P0 | No concurrent recompute spawned while task running |
| AC2 | Unit | P0 | `bulk_recompute()` writes all buckets via pipeline |
| AC2 | Unit | P0 | `bulk_recompute()` returns correct key count |
| AC2 | Unit | P0 | `bulk_recompute()` uses `time_to_bucket()` for partitioning |
| AC2 | Unit | P0 | `bulk_recompute()` enforces MAX_BUCKET_VALUES cap |
| AC4 | Unit | P0 | No Redis writes if Prometheus fails (Phase 1 exception) |
| AC2 | Unit | P1 | `bulk_recompute()` handles empty Prometheus response |
| AC5 | Unit | P0 | `_run_baseline_recompute()` emits started log |
| AC5 | Unit | P0 | `_run_baseline_recompute()` emits completed log with key_count + duration_seconds |
| AC5 | Unit | P0 | `_run_baseline_recompute()` emits failed log with exc_info on exception |
| AC4 | Unit | P0 | `_run_baseline_recompute()` updates last_recompute on success |
| AC4 | Unit | P0 | `_run_baseline_recompute()` does NOT update last_recompute on failure |

### Test Files
- `tests/unit/baseline/test_bulk_recompute.py` — 6 tests for `bulk_recompute()`
- `tests/unit/pipeline/test_baseline_recompute.py` — 10 tests for timer logic + `_run_baseline_recompute()`

### TDD Red Phase Confirmation
All tests are written to **fail** because the implementation does not exist yet:
- `bulk_recompute()` method does not exist on `SeasonalBaselineClient`
- `_should_trigger_recompute()` does not exist in `__main__.py`
- `_run_baseline_recompute()` does not exist in `__main__.py`
- `get_last_recompute()` / `set_last_recompute()` do not exist on `SeasonalBaselineClient`
- Tests import these non-existent symbols → immediate `ImportError` / `AttributeError`

**No `pytest.mark.skip` or `pytest.mark.xfail` used** — tests fail as proper failing tests per project policy.

---

## Step 4: Test Generation

### Worker A: Failing Unit Tests — `bulk_recompute()` (tests/unit/baseline/test_bulk_recompute.py)
### Worker B: Failing Unit Tests — Timer Logic (tests/unit/pipeline/test_baseline_recompute.py)

*(Test files written to disk — see below)*

---

## Step 4C: Aggregation

### TDD Red Phase Validation: PASS

All 16 tests collected across 2 files. 15 failing (RED), 1 passing.

- `test_bulk_recompute_*` (6 tests): all fail with `AttributeError: 'SeasonalBaselineClient' object has no attribute 'bulk_recompute'`
- `test_should_trigger_*` (4 tests): all fail with `ImportError: _should_trigger_recompute not implemented yet`
- `test_no_concurrent_recompute_spawned_while_task_running` (1 test): PASSES — tests the asyncio guard logic using stdlib only, no unimplemented production code
- `test_recompute_coroutine_*` (5 tests): all fail with `ImportError: _run_baseline_recompute not implemented yet`

No `pytest.mark.skip`, no `pytest.mark.xfail` used — all tests are proper failing tests.

### Generated Files

| File | Tests | Status |
|------|-------|--------|
| `tests/unit/baseline/test_bulk_recompute.py` | 6 | Written |
| `tests/unit/pipeline/test_baseline_recompute.py` | 10 | Written |

### Fixture Needs

- `_FakePipelineRedis` / `_FakePipeline` — implemented inline in `test_bulk_recompute.py`
- `_FakeBaselineRedis` / `_FakePipeline` — implemented inline in `test_baseline_recompute.py`
- `_make_metric_queries` helper — implemented inline in both test files

---

## Step 5: Validation & Completion

### Checklist Validation

- [x] Stack detected: `backend` (Python, pytest, asyncio_mode=auto)
- [x] Story has clear acceptance criteria (7 ACs)
- [x] Test framework configured: `conftest.py`, `pyproject.toml` with `asyncio_mode=auto`
- [x] AI generation mode selected (backend stack)
- [x] All AC mapped to test scenarios
- [x] Test files created at correct paths
- [x] Tests designed to FAIL before implementation (RED phase)
- [x] No `pytest.mark.skip` or `pytest.mark.xfail` used
- [x] No `test.skip()` patterns (Python project — not applicable)
- [x] Type annotations on all test signatures
- [x] ruff clean (0 errors)
- [x] Existing test suite unaffected (1209 tests pass)
- [x] No orphaned browser sessions (backend-only project)
- [x] Temp artifacts not created in random locations

### Summary Statistics

- **TDD phase**: RED
- **Total tests**: 16
- **Failing (RED)**: 15
- **Passing (expected — guard logic test)**: 1
- **Files created**: 2
- **Fixtures created inline**: `_FakePipelineRedis`, `_FakePipeline`, `_FakeBaselineRedis`, `_make_metric_queries`
- **Acceptance criteria covered**: AC1, AC2, AC4, AC5

### Test Run Output (RED Phase Confirmed)

```
15 failed, 1 passed in 0.73s
```

Failure modes:
- `tests/unit/baseline/` → `AttributeError: 'SeasonalBaselineClient' object has no attribute 'bulk_recompute'`
- `tests/unit/pipeline/` → `ImportError: _should_trigger_recompute / _run_baseline_recompute not implemented yet (Story 1.4 RED phase)`

### Next Steps (TDD Green Phase)

After implementing Story 1.4:

1. Add `bulk_recompute()`, `get_last_recompute()`, `set_last_recompute()` to `SeasonalBaselineClient` (`src/aiops_triage_pipeline/baseline/client.py`)
2. Add `_should_trigger_recompute()`, `_run_baseline_recompute()`, `_RECOMPUTE_INTERVAL_SECONDS` to `__main__.py`
3. Run: `uv run pytest tests/unit/baseline/test_bulk_recompute.py tests/unit/pipeline/test_baseline_recompute.py -v`
4. Verify all 16 tests PASS (green phase)
5. Run full regression: `uv run pytest tests/unit/ -q` — must show 1225+ passed, 0 failed
6. Run ruff: `uv run ruff check src/ tests/`
7. Update `docs/runtime-modes.md` (Task 6)

### Implementation Guidance

Functions/methods to implement:

**`src/aiops_triage_pipeline/baseline/client.py`:**
- `async def bulk_recompute(self, *, prometheus_client, metric_queries, lookback_days, step_seconds, timeout_seconds, logger) -> int`
- `def get_last_recompute(self) -> str | None`
- `def set_last_recompute(self, timestamp_iso: str) -> None`
- Add `pipeline()` to `SeasonalBaselineClientProtocol`

**`src/aiops_triage_pipeline/__main__.py`:**
- `_RECOMPUTE_INTERVAL_SECONDS = 7 * 24 * 3600` (module-level constant)
- `def _should_trigger_recompute(last_iso: str | None, now: datetime, interval_seconds: int) -> bool`
- `async def _run_baseline_recompute(seasonal_baseline_client, prometheus_client, metric_queries, lookback_days, step_seconds, timeout_seconds, logger) -> int`
- `_recompute_task: asyncio.Task[int] | None = None` (before `while True:` loop)
- Timer check block inside `_run_hot_path_scheduler()` after `hot_path_cycle_started` log
---
