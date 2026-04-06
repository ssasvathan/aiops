---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-05'
story_id: 1-3-cold-start-backfill-seeding-with-metric-auto-discovery
tdd_phase: RED
inputDocuments:
  - artifact/implementation-artifacts/1-3-cold-start-backfill-seeding-with-metric-auto-discovery.md
  - src/aiops_triage_pipeline/baseline/client.py
  - src/aiops_triage_pipeline/baseline/computation.py
  - src/aiops_triage_pipeline/baseline/constants.py
  - src/aiops_triage_pipeline/pipeline/baseline_backfill.py
  - tests/unit/baseline/test_client.py
  - tests/unit/pipeline/test_baseline_backfill.py
  - tests/integration/conftest.py
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-quality.md
---

# ATDD Checklist: Story 1.3 — Cold-Start Backfill Seeding with Metric Auto-Discovery

## Step 1: Preflight & Context

**Stack Detection:** `backend` (Python, pyproject.toml, no frontend artifacts)
**Generation Mode:** AI Generation (backend stack, clear acceptance criteria)
**Test Framework:** pytest + asyncio_mode=auto
**Config Flags:** tea_use_playwright_utils (N/A for backend), no Pact tests needed

**Inputs Loaded:**
- Story 1.3 acceptance criteria (6 ACs)
- `SeasonalBaselineClient` (Story 1.2 — existing methods: `read_buckets`, `update_bucket`, `read_buckets_batch`)
- `time_to_bucket()` in `baseline/computation.py`
- `MAX_BUCKET_VALUES = 12` in `baseline/constants.py`
- `backfill_baselines_from_prometheus()` in `pipeline/baseline_backfill.py`
- Existing test patterns (`_FakeRedis`, `_FakePeakRetention`) from Story 1.2 tests

---

## Step 2: Generation Mode

**Mode:** AI Generation (sequential)
**Reason:** Backend-only Python project; no browser UI; acceptance criteria are clear and well-specified.

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Scenarios

| AC | Scenario | Level | Priority | File |
|----|----------|-------|----------|------|
| AC1 | seed_from_history() partitions into correct (dow,hour) buckets | Unit | P0 | test_client.py |
| AC1 | seed_from_history() covers all 168 buckets (7 days × 24h) | Unit | P0 | test_client.py |
| AC2 | MAX_BUCKET_VALUES cap enforced during seeding | Unit | P0 | test_client.py |
| AC3 | Merge with existing bucket data | Unit | P0 | test_client.py |
| AC3 | Merge + cap when combined exceeds MAX_BUCKET_VALUES | Unit | P1 | test_client.py |
| AC4 | time_to_bucket() used — UTC normalization verified | Unit | P0 | test_client.py |
| AC4 | Naive datetime raises ValueError | Unit | P1 | test_client.py |
| AC1 | Empty time-series is a no-op | Unit | P2 | test_client.py |
| AC1 | backfill calls seed_from_history for each scope/metric pair | Unit | P0 | test_baseline_backfill.py |
| AC1 | backfill converts Unix timestamps to UTC datetimes | Unit | P0 | test_baseline_backfill.py |
| AC2 | All 9 contract metrics seeded (auto-discovery, not just topic_messages) | Unit | P0 | test_baseline_backfill.py |
| AC4 | baseline_deviation_backfill_seeded log event emitted | Unit | P0 | test_baseline_backfill.py |
| AC6 | seed_from_history writes to real Redis (key schema correct) | Integration | P0 | test_baseline_deviation.py |
| AC6 | Redis key schema exact: aiops:seasonal_baseline:{scope}:{metric}:{dow}:{hour} | Integration | P0 | test_baseline_deviation.py |
| AC6 | Redis merge with existing bucket data | Integration | P1 | test_baseline_deviation.py |
| AC6 | All 168 Redis keys written for 7 days of data | Integration | P0 | test_baseline_deviation.py |

**No E2E tests** — pure backend story, no UI or API endpoints.

---

## Step 4: TDD Red Phase — Generated Tests

### Summary

| Category | Count | All Failing (RED) |
|----------|-------|-------------------|
| Unit: seed_from_history (test_client.py) | 8 | ✅ |
| Unit: backfill extension (test_baseline_backfill.py) | 13 | ✅ (4 new + 9 updated) |
| Integration: Redis-backed (test_baseline_deviation.py) | 4 | (requires Docker) |
| **Total** | **25** | |

### Unit Tests: `tests/unit/baseline/test_client.py` (8 new tests)

All fail with `AttributeError: 'SeasonalBaselineClient' object has no attribute 'seed_from_history'`

**New tests added (Story 1.3):**
- `test_seed_from_history_partitions_into_correct_buckets` [P0]
- `test_seed_from_history_covers_all_168_buckets` [P0]
- `test_seed_from_history_respects_max_bucket_values_cap` [P0]
- `test_seed_from_history_merges_with_existing_bucket_data` [P0]
- `test_seed_from_history_merge_enforces_cap_on_combined_data` [P1]
- `test_seed_from_history_uses_time_to_bucket_for_partitioning` [P0]
- `test_seed_from_history_rejects_naive_datetime` [P1]
- `test_seed_from_history_empty_time_series_is_a_noop` [P2]

### Unit Tests: `tests/unit/pipeline/test_baseline_backfill.py` (4 new + 9 updated)

All fail with `TypeError: backfill_baselines_from_prometheus() got an unexpected keyword argument 'seasonal_baseline_client'`

**New tests added (Story 1.3):**
- `test_backfill_calls_seed_from_history_for_each_scope_and_metric` [P0]
- `test_backfill_converts_unix_timestamps_to_utc_datetimes` [P0]
- `test_backfill_emits_baseline_deviation_backfill_seeded_log` [P0]
- `test_backfill_seeds_all_metrics_not_just_topic_messages` [P0]

**Existing tests updated** (added `seasonal_baseline_client=_FakeSeasonalClient()` to all 9 call sites)

**New helper added:** `_FakeSeasonalClient` — captures `seed_from_history()` calls

### Integration Tests: `tests/integration/test_baseline_deviation.py` (4 new tests, @pytest.mark.integration)

- `test_seed_from_history_writes_to_real_redis` [P0]
- `test_seed_from_history_key_schema_is_correct` [P0]
- `test_seed_from_history_merge_with_existing_redis_data` [P1]
- `test_seed_from_history_all_168_buckets_written_to_redis` [P0]

---

## Step 5: Validation

### Prerequisites ✅
- Story 1.3 has clear acceptance criteria
- Test framework configured (pytest, asyncio_mode=auto, pyproject.toml)
- Stories 1.1 and 1.2 done (time_to_bucket, SeasonalBaselineClient with read/update)

### TDD Red Phase Compliance ✅
- All new tests fail before implementation
- No `@pytest.mark.xfail` or `@pytest.mark.skip` used
- All tests use proper `def test_*(…) -> None:` signatures
- Sync tests for `seed_from_history()` (sync method)
- Async tests for `backfill_baselines_from_prometheus()` (async function)
- Integration tests marked `@pytest.mark.integration`

### Quality ✅
- ruff clean (E,F,I,N,W): All checks passed
- Lines ≤ 100 chars
- No inline magic numbers (imports `MAX_BUCKET_VALUES` from constants)
- No duplicate coverage across levels
- Explicit assertions in test bodies (no hidden assertions)
- `_FakeRedis` and `_FakeSeasonalClient` follow established project patterns

### Acceptance Criteria Coverage

| AC | Covered by Tests | Status |
|----|-----------------|--------|
| AC1 — seed_from_history() partitions 30-day data into 168 buckets | test_seed_from_history_partitions_into_correct_buckets, test_seed_from_history_covers_all_168_buckets, test_backfill_calls_seed_from_history_for_each_scope_and_metric | RED |
| AC2 — new metric auto-discovery (all contract metrics seeded) | test_backfill_seeds_all_metrics_not_just_topic_messages | RED |
| AC3 — new scope discovery (all scopes seeded) | test_backfill_calls_seed_from_history_for_each_scope_and_metric | RED |
| AC4 — pipeline blocks until seeding + baseline_deviation_backfill_seeded event | test_backfill_emits_baseline_deviation_backfill_seeded_log | RED |
| AC5 — performance (500×9×168 within 10 min) | Not unit-testable; NFR validated at integration/load test level | N/A |
| AC6 — seed_from_history partitions correctly + integration Redis test | test_seed_from_history_writes_to_real_redis, test_seed_from_history_all_168_buckets_written_to_redis | RED |

---

## Next Steps (TDD Green Phase)

After implementing the feature:

1. Add `seed_from_history()` to `SeasonalBaselineClient` in `src/aiops_triage_pipeline/baseline/client.py`
2. Add `seasonal_baseline_client: SeasonalBaselineClient` parameter to `backfill_baselines_from_prometheus()` in `pipeline/baseline_backfill.py`
3. Add Layer C seeding loop + `baseline_deviation_backfill_seeded` log event to `backfill_baselines_from_prometheus()`
4. Wire `SeasonalBaselineClient` into `__main__.py` startup
5. Run tests: `uv run pytest tests/unit/baseline/test_client.py tests/unit/pipeline/test_baseline_backfill.py -q`
6. Verify all 21 previously-failing tests now PASS (green phase)
7. Run integration tests: `TESTCONTAINERS_RYUK_DISABLED=true uv run pytest tests/integration/test_baseline_deviation.py -q`
8. Full regression: `TESTCONTAINERS_RYUK_DISABLED=true uv run pytest -q -rs`

## Risks / Assumptions

- `consumer_group_lag` and `consumer_group_lag_seconds` use a 4-tuple scope (env, cluster, group, topic); `seed_from_history` must handle variable-length scope tuples — already supported via `tuple[str, ...]`
- Integration tests require Docker and Testcontainers — excluded from default unit run
- The 168-bucket assertion assumes exactly 1 data point per hour over 7 days; real backfill may have multiple points per bucket (cap applies)
