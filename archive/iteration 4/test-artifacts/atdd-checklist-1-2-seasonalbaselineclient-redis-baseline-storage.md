---
stepsCompleted: ['step-01-preflight-and-context']
lastStep: 'step-01-preflight-and-context'
lastSaved: '2026-04-05'
inputDocuments:
  - artifact/implementation-artifacts/1-2-seasonalbaselineclient-redis-baseline-storage.md
  - tests/unit/pipeline/test_baseline_store.py
  - tests/unit/baseline/test_constants.py
  - src/aiops_triage_pipeline/baseline/constants.py
  - pyproject.toml
  - tests/conftest.py
---

# ATDD Checklist: Story 1.2 — SeasonalBaselineClient Redis Baseline Storage

## Step 1: Preflight & Context Loading

### Stack Detection
- **Detected Stack**: `backend` (Python — `pyproject.toml` present, no `package.json`)
- **Test Framework**: pytest 9.0.2 with `asyncio_mode=auto`, `pythonpath=["."]`
- **Generation Mode**: AI generation (backend stack, no browser recording needed)

### Story Summary
Story 1.2 creates `SeasonalBaselineClient` in `src/aiops_triage_pipeline/baseline/client.py`.
Tests live in `tests/unit/baseline/test_client.py`.

### Acceptance Criteria Loaded
1. `read_buckets(scope, metric_key, dow, hour)` → reads key `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}`, returns `list[float]`
2. `update_bucket(scope, metric_key, dow, hour, value)` → appends, caps at `MAX_BUCKET_VALUES` (12), writes back as JSON
3. `read_buckets_batch(scope, metric_keys, dow, hour)` → uses `mget` for single round-trip
4. Missing Redis key → returns empty list (no error)
5. Redis unavailable → raises exception (fail-open is caller's responsibility)
6. Tests in `tests/unit/baseline/test_client.py` using fake Redis, no real Redis dependency

### Prerequisites
- Story AC clearly defined ✅
- pytest configured (`conftest.py`, `pyproject.toml`) ✅
- `MAX_BUCKET_VALUES = 12` available from `aiops_triage_pipeline.baseline.constants` ✅
- `_FakeRedis` pattern identified in `tests/unit/pipeline/test_baseline_store.py` ✅
- `baseline/client.py` does NOT exist → all imports will fail → tests will fail (TDD RED) ✅
- No `@pytest.mark.xfail` policy in force ✅

---

## Step 2: Generation Mode Selection

- **Mode**: AI Generation (backend Python project, no browser needed)
- **Rationale**: Acceptance criteria are fully defined; `SeasonalBaselineClient` is pure Python with sync Redis I/O. Unit tests with `_FakeRedis` in-memory dict cover all ACs.

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Scenarios

| AC | Scenario | Level | Priority |
|----|----------|-------|----------|
| AC1 | `read_buckets` returns float list for existing key | Unit | P0 |
| AC1 | `read_buckets` key format uses `\|`-joined scope tuple | Unit | P0 |
| AC2 | `update_bucket` appends value to existing list | Unit | P0 |
| AC2 | `update_bucket` enforces `MAX_BUCKET_VALUES` cap (13→12, oldest dropped) | Unit | P0 |
| AC2 | `update_bucket` creates new list if key is missing | Unit | P1 |
| AC3 | `read_buckets_batch` issues single `mget` for multiple metrics | Unit | P0 |
| AC3 | `read_buckets_batch` returns correct float lists for all metrics | Unit | P0 |
| AC4 | `read_buckets` returns `[]` for missing key | Unit | P0 |
| AC4 | `read_buckets_batch` returns `[]` for each missing key | Unit | P1 |
| AC5 | Redis exception propagates from `read_buckets` (not swallowed) | Unit | P1 |
| AC5 | Redis exception propagates from `update_bucket` (not swallowed) | Unit | P1 |
| AC5 | Redis exception propagates from `read_buckets_batch` (not swallowed) | Unit | P1 |

### Test Level: Unit only
- `SeasonalBaselineClient` is a pure sync Python class with constructor-injected Redis client
- No integration/E2E needed; all logic covered by unit tests with `_FakeRedis`
- No E2E (backend-only project)

### TDD Red Phase
- `baseline/client.py` does not exist → `ImportError` on test collection → all tests fail ✅
- Tests assert EXPECTED behavior; failure is from missing implementation, not bad test logic

---

## Step 4: Test Generation (API/Unit — Sequential mode)

### Test File Generated
- **Path**: `tests/unit/baseline/test_client.py`
- **Tests**: 12 unit tests
- **TDD Phase**: RED (import will fail until `baseline/client.py` is implemented)

*(See actual test file written to disk)*

---

## Step 5: Validation & Completion

### Validation Checklist
- [x] Prerequisites satisfied (story has clear ACs, pytest configured, Story 1.1 constants available)
- [x] Test file created: `tests/unit/baseline/test_client.py`
- [x] All 12 tests assert EXPECTED behavior (not placeholders)
- [x] Tests will fail because `SeasonalBaselineClient` does not exist (TDD RED)
- [x] No `@pytest.mark.xfail` markers used
- [x] No `@pytest.mark.skip` markers used
- [x] `_FakeRedis` pattern mirrors `tests/unit/pipeline/test_baseline_store.py`
- [x] `_FailingRedis` included for exception propagation tests
- [x] All imports at module level (ruff I001 compliance)
- [x] Type annotations on all test functions (`-> None`)
- [x] `MAX_BUCKET_VALUES` imported from `aiops_triage_pipeline.baseline.constants`
- [x] No hardcoded `12` in tests
- [x] Plain `def` tests (not `async def`) — `SeasonalBaselineClient` is sync

### Acceptance Criteria Coverage
| AC | Tests Covering |
|----|----------------|
| AC1 | `test_read_buckets_returns_float_list`, `test_read_buckets_key_schema` |
| AC2 | `test_update_bucket_appends_value`, `test_update_bucket_cap_enforcement`, `test_update_bucket_creates_new_list` |
| AC3 | `test_read_buckets_batch_single_mget_call`, `test_read_buckets_batch_returns_all_metrics` |
| AC4 | `test_read_buckets_missing_key_returns_empty_list`, `test_read_buckets_batch_missing_keys_return_empty_lists` |
| AC5 | `test_read_buckets_propagates_redis_exception`, `test_update_bucket_propagates_redis_exception`, `test_read_buckets_batch_propagates_redis_exception` |

### Summary
- **Test file**: `tests/unit/baseline/test_client.py`
- **Tests created**: 12
- **Expected result when run now**: FAIL (ImportError — `baseline/client.py` not implemented)
- **Next steps**: Implement `src/aiops_triage_pipeline/baseline/client.py`, then run `uv run pytest tests/unit/baseline/test_client.py -q` to verify GREEN

### Key Assumptions
- `SeasonalBaselineClient` constructor takes a Redis-protocol-compatible client (injected)
- `_build_key` uses `"|".join(scope)` for the scope portion (consistent with `baseline_store.py`)
- `read_buckets_batch` uses `mget` in a single call (NFR-P2)
- `update_bucket` appends then slices to `[-MAX_BUCKET_VALUES:]` (drops oldest)
