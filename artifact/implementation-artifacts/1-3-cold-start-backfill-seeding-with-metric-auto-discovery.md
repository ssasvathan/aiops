# Story 1.3: Cold-Start Backfill Seeding with Metric Auto-Discovery

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform engineer,
I want seasonal baselines automatically seeded from 30-day Prometheus history on startup for all discovered metrics and scopes,
so that detection is ready on the first pipeline cycle without manual data population or code changes for new metrics.

## Acceptance Criteria

1. **Given** the pipeline starts with empty Redis seasonal baseline keys
   **When** the startup backfill sequence runs
   **Then** `seed_from_history()` on `SeasonalBaselineClient` is called with the same 30-day Prometheus `query_range` data already fetched for peak history (D5)
   **And** each data point is partitioned into its `(dow, hour)` time bucket using `time_to_bucket()`
   **And** partitioned values are written to Redis seasonal baseline keys for all scopes × all metrics × 168 buckets

2. **Given** a new metric is added to the Prometheus metrics contract YAML
   **When** the pipeline restarts and backfill runs
   **Then** the new metric receives baseline seeding alongside all existing metrics (FR22, FR23)
   **And** no code changes are required (NFR-S3)

3. **Given** a new scope appears in evidence stage scope discovery
   **When** the next startup backfill runs
   **Then** the new scope receives baseline seeding for all contract metrics (FR24)

4. **Given** backfill is in progress
   **When** the pipeline attempts to start cycling
   **Then** the pipeline blocks until both peak history and baseline seeding complete (D5)
   **And** a `baseline_deviation_backfill_seeded` structured log event is emitted with scope count, metric count, and bucket count

5. **Given** 500 scopes × 9 metrics × 168 buckets
   **When** cold-start backfill runs
   **Then** it completes within 10 minutes (NFR-P4)

6. **Given** unit and integration tests
   **When** tests are executed
   **Then** `seed_from_history` correctly partitions time-series data into 168 buckets
   **And** integration tests in `tests/integration/test_baseline_deviation.py` verify Redis-backed seeding
   **And** `docs/runtime-modes.md` and `docs/developer-onboarding.md` are updated to document the extended backfill

## Tasks / Subtasks

- [x] Task 1: Add `seed_from_history()` to `SeasonalBaselineClient` (AC: 1, 2, 3, 5)
  - [x] 1.1 Open `src/aiops_triage_pipeline/baseline/client.py`
  - [x] 1.2 Add method `seed_from_history(scope, metric_key, time_series) -> None` that:
    - Accepts `scope: BaselineScope`, `metric_key: str`, `time_series: Sequence[tuple[datetime, float]]`
    - Iterates over `(dt, value)` pairs and calls `time_to_bucket(dt)` to derive `(dow, hour)`
    - Groups values by `(dow, hour)` bucket
    - For each bucket, appends all values to the existing bucket contents via `update_bucket()` OR uses a bulk write approach that reads existing and writes the merged+capped result in one SET call
    - **Preferred implementation**: use a dict accumulator keyed by `(dow, hour)`, merge with existing via `read_buckets()`, cap at `MAX_BUCKET_VALUES`, write back via `_build_key()` + `self._redis.set()`
    - Must call `time_to_bucket()` from `baseline.computation` — NEVER derive buckets inline
  - [x] 1.3 Confirm method signature uses `datetime` objects with timezone info (mirrors `time_to_bucket` naive guard)

- [x] Task 2: Extend `backfill_baselines_from_prometheus` to call `seed_from_history()` (AC: 1, 2, 3, 4)
  - [x] 2.1 Open `src/aiops_triage_pipeline/pipeline/baseline_backfill.py`
  - [x] 2.2 Add `seasonal_baseline_client` parameter of type `SeasonalBaselineClient` to `backfill_baselines_from_prometheus()`
  - [x] 2.3 In the per-metric processing loop, after processing `raw_records`, build `time_series: list[tuple[datetime, float]]` from `(ts_float, value)` pairs — convert Unix float timestamps to timezone-aware `datetime` objects using `datetime.fromtimestamp(ts, tz=UTC)`
  - [x] 2.4 Call `seasonal_baseline_client.seed_from_history(scope, metric_key, time_series)` for each scope and metric
  - [x] 2.5 Track `bucket_count` (total number of `(scope, metric_key, dow, hour)` combinations written) for the log summary
  - [x] 2.6 After backfill completes, emit the `baseline_deviation_backfill_seeded` structured log event:
    ```python
    logger.info(
        "baseline_deviation_backfill_seeded",
        event_type="backfill.seasonal_seeded",
        scope_count=<n_scopes>,
        metric_count=<n_metrics>,
        bucket_count=<n_buckets>,
    )
    ```
    This event name is canonical from P6 — do NOT invent a different name.

- [x] Task 3: Wire `SeasonalBaselineClient` into `__main__.py` startup (AC: 1, 4)
  - [x] 3.1 Open `src/aiops_triage_pipeline/__main__.py`
  - [x] 3.2 Construct `SeasonalBaselineClient` at startup (alongside `peak_history_retention` creation, near line 559):
    ```python
    from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
    seasonal_baseline_client = SeasonalBaselineClient(redis_client=redis_client)
    ```
  - [x] 3.3 Pass `seasonal_baseline_client` to `backfill_baselines_from_prometheus()` in the existing `asyncio.wait_for(...)` call (near line 581)
  - [x] 3.4 Do NOT add `SeasonalBaselineClient` to the per-cycle hot-path loop — it is only needed at startup backfill (Story 1.4 will wire it into the weekly recompute; Story 2.3 will wire it into the stage)

- [x] Task 4: Unit tests for `seed_from_history()` (AC: 6)
  - [x] 4.1 Open `tests/unit/baseline/test_client.py` (existing file from Story 1.2)
  - [x] 4.2 Add tests using the existing `_FakeRedis` pattern:
    - `test_seed_from_history_partitions_into_correct_buckets()` — Provide a time series spanning multiple `(dow, hour)` buckets, verify each bucket key contains the correct float values
    - `test_seed_from_history_respects_max_bucket_values_cap()` — Seed more than `MAX_BUCKET_VALUES` data points into the same bucket, verify cap is enforced (only most recent `MAX_BUCKET_VALUES` retained)
    - `test_seed_from_history_merges_with_existing_bucket_data()` — Pre-populate a bucket, then call `seed_from_history()`, verify existing + new values appear (capped)
    - `test_seed_from_history_covers_all_168_buckets()` — Verify that seeding 7 days of hourly data (168 timestamps) results in values in all 168 `(dow, hour)` buckets
    - `test_seed_from_history_uses_time_to_bucket_for_partitioning()` — Use a non-UTC timezone datetime, confirm the bucket matches the UTC-normalized `(dow, hour)`, not the local `(dow, hour)`
  - [x] 4.3 All tests use `def test_*(...)  -> None:` signatures (sync, not async — `SeasonalBaselineClient` is sync)

- [x] Task 5: Unit tests for extended `backfill_baselines_from_prometheus` (AC: 1, 4)
  - [x] 5.1 Open `tests/unit/pipeline/test_baseline_backfill.py` (existing file from tech-spec)
  - [x] 5.2 Add a mock `SeasonalBaselineClient` or `_FakeSeasonalClient` following `_FakePeakRetention` pattern
  - [x] 5.3 Add tests:
    - `test_backfill_calls_seed_from_history_for_each_scope_and_metric()` — Verify `seed_from_history()` is called for every (scope, metric_key) pair discovered
    - `test_backfill_converts_unix_timestamps_to_utc_datetimes()` — Verify `datetime.fromtimestamp(ts, tz=UTC)` conversion before passing to `seed_from_history`
    - `test_backfill_emits_baseline_deviation_backfill_seeded_log()` — Verify the structured log event is emitted with correct `scope_count`, `metric_count`, `bucket_count`
    - `test_backfill_seeds_all_metrics_not_just_topic_messages()` — Confirm ALL 9 contract metrics (not just `topic_messages_in_per_sec`) are passed to `seed_from_history` (AC2 — auto-discovery)
  - [x] 5.4 Update `test_backfill_continues_on_individual_metric_failure()` to pass `seasonal_baseline_client` to the function signature

- [x] Task 6: Integration test for Redis-backed seeding (AC: 6)
  - [x] 6.1 Create `tests/integration/test_baseline_deviation.py` (new file)
  - [x] 6.2 Test `test_seed_from_history_writes_to_real_redis()`:
    - Use `testcontainers` Redis container (follow pattern from existing integration tests in `tests/integration/`)
    - Construct a real `SeasonalBaselineClient` with the container Redis client
    - Call `seed_from_history()` with known time-series data
    - Assert that `redis_client.get(key)` returns a non-empty JSON float list for the expected bucket keys
    - Assert key schema matches `aiops:seasonal_baseline:{scope_str}:{metric_key}:{dow}:{hour}`
  - [x] 6.3 Mark with `@pytest.mark.integration` if convention exists — check existing integration tests for marker usage

- [x] Task 7: Update documentation (AC: 6)
  - [x] 7.1 Update `docs/runtime-modes.md` — add a "Startup backfill" subsection under `## hot-path` documenting:
    - Both backfill layers: Layer A (Redis peak cache), Layer B (peak history deque), AND Layer C (seasonal baseline buckets via `seed_from_history`)
    - Configurable settings: `BASELINE_BACKFILL_LOOKBACK_DAYS`, `BASELINE_BACKFILL_TIMEOUT_SECONDS`, `BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS`
    - Cold-start behavior when Prometheus unreachable: pipeline starts in degraded mode
  - [x] 7.2 Update `docs/developer-onboarding.md` — add mention of baseline seeding in the pipeline journey section, noting that the baseline layer is seeded before the first cycle

- [x] Task 8: Run full regression suite (AC: 6)
  - [x] 8.1 Run `uv run pytest tests/unit/ -q` — 1201 passed, 0 failed, 0 skipped
  - [x] 8.2 Confirm 0 skipped tests and no regressions

## Dev Notes

### What This Story Delivers

Story 1.3 extends the existing `backfill_baselines_from_prometheus()` (already wired in `__main__.py`) to also populate the **seasonal baseline buckets** in Redis via a new `seed_from_history()` method on `SeasonalBaselineClient`.

**The existing backfill already handles:**
- Layer A: Redis peak cache (`aiops:baseline:prometheus:{scope}:{metric_key}`) via `persist_metric_baselines()`
- Layer B: In-memory `_PeakHistoryRetention` deque via `peak_history_retention.seed()`

**Story 1.3 adds:**
- Layer C: Seasonal baseline Redis buckets (`aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}`) via `SeasonalBaselineClient.seed_from_history()`

The auto-discovery aspect (FR22, FR23, NFR-S3) comes for free: `backfill_baselines_from_prometheus()` already iterates over `metric_queries` which is built from the Prometheus contract YAML. No new code is needed for metric discovery — it is inherited from the existing loop.

### Critical: `seed_from_history()` Method Specification

`seed_from_history()` is the **new method** to add to `SeasonalBaselineClient`. Architecture decision D3 listed this as part of the client interface: `read_buckets()`, `update_bucket()`, `seed_from_history()`, `bulk_recompute()`.

**Recommended implementation sketch:**

```python
def seed_from_history(
    self,
    scope: BaselineScope,
    metric_key: str,
    time_series: Sequence[tuple[datetime, float]],
) -> None:
    """Partition a time-series into 168 (dow, hour) buckets and write to Redis.

    Used during cold-start backfill to seed baselines from Prometheus range data.
    Each (dt, value) pair is bucketed by UTC (dow, hour) via time_to_bucket().
    Existing bucket contents are read first and merged; MAX_BUCKET_VALUES cap enforced.
    """
    from aiops_triage_pipeline.baseline.computation import time_to_bucket

    # Group values by bucket
    bucket_values: dict[tuple[int, int], list[float]] = {}
    for dt, value in time_series:
        bucket = time_to_bucket(dt)  # raises ValueError for naive datetimes
        bucket_values.setdefault(bucket, []).append(value)

    for (dow, hour), new_values in bucket_values.items():
        existing = self.read_buckets(scope, metric_key, dow, hour)
        merged = existing + new_values
        if len(merged) > MAX_BUCKET_VALUES:
            merged = merged[-MAX_BUCKET_VALUES:]
        key = self._build_key(scope, metric_key, dow, hour)
        self._redis.set(key, json.dumps(merged))
```

**Anti-patterns to prevent:**
- Do NOT call `datetime.weekday()` or `.hour` directly in `seed_from_history()` — always delegate to `time_to_bucket()` (P3)
- Do NOT hardcode `12` for cap — import `MAX_BUCKET_VALUES` from `baseline.constants` (P2)
- Do NOT accept naive datetimes — `time_to_bucket()` raises `ValueError` for naive datetimes (established in Story 1.1 review)

### Critical: Unix Timestamp to datetime Conversion

Prometheus `query_range` returns `(unix_timestamp_float, value_float)` pairs. To call `seed_from_history()`, the backfill module must convert Unix floats to timezone-aware `datetime` objects:

```python
from datetime import UTC, datetime

dt = datetime.fromtimestamp(ts_float, tz=UTC)
```

This produces a UTC-aware `datetime`. **Do NOT** use `datetime.utcfromtimestamp()` (returns naive datetime) or `datetime.fromtimestamp(ts)` without `tz=UTC` (uses local timezone).

The backfill loop already has `(ts, val)` tuples in `ts_map` and `values` — use these to build `time_series: list[tuple[datetime, float]]` before calling `seed_from_history()`.

### Critical: `baseline_deviation_backfill_seeded` Log Event (P6)

The canonical event name is exactly `baseline_deviation_backfill_seeded` with prefix `baseline_deviation_`. This is defined in P6 of `implementation-patterns-consistency-rules.md`:

```python
logger.info(
    "baseline_deviation_backfill_seeded",
    event_type="backfill.seasonal_seeded",
    scope_count=<n>,
    metric_count=<n>,
    bucket_count=<n>,
)
```

**Do NOT** emit this as `backfill.seeded`, `baseline_seeded`, or any other name. The exact event name is validated by consumers.

### Existing Code to Extend (NOT Replace)

**`pipeline/baseline_backfill.py`** — This file already exists and implements the peak history backfill. Story 1.3 **extends** it by:
1. Adding a `seasonal_baseline_client: SeasonalBaselineClient` parameter
2. Building `time_series: list[tuple[datetime, float]]` from existing `raw_records`
3. Calling `seasonal_baseline_client.seed_from_history(scope, metric_key, time_series)` for each scope/metric pair

The existing Layer A and Layer B logic in the backfill function is **unchanged** — do NOT modify the `latest_by_scope_metric` (Layer A) or `ts_max_by_scope` (Layer B) logic. Only add the seasonal seeding as Layer C.

**`baseline/client.py`** — Story 1.2 implemented `read_buckets`, `read_buckets_batch`, `update_bucket`. Story 1.3 adds `seed_from_history`. Do NOT modify existing methods.

**`__main__.py`** — The backfill is already wired inside `asyncio.wait_for(...)`. Only two changes needed:
1. Construct `SeasonalBaselineClient` before the `wait_for` call
2. Pass it as `seasonal_baseline_client=seasonal_baseline_client` to `backfill_baselines_from_prometheus()`

### Existing Test File to Extend

`tests/unit/pipeline/test_baseline_backfill.py` already exists with:
- `_FakeRedis` — in-memory Redis mock
- `_FakePeakRetention` — mock for `_PeakHistoryRetention.seed()`
- `_ttl_policy()` — helper for `RedisTtlPolicyV1`
- `_make_metric_queries()` — builds `dict[str, MetricQueryDefinition]`
- `_matrix_record()` — builds Prometheus matrix response record

Add a `_FakeSeasonalClient` following the `_FakePeakRetention` pattern to capture `seed_from_history` calls.

**Important:** ALL existing tests in this file that call `backfill_baselines_from_prometheus()` will need to pass the new `seasonal_baseline_client` parameter. Add it to all existing test call sites.

### Integration Test Pattern

Check `tests/integration/` for the Redis container setup pattern. The existing integration tests use `testcontainers`:

```python
from testcontainers.redis import RedisContainer
import redis

with RedisContainer() as container:
    r = redis.Redis(host=container.get_container_host_ip(), port=container.get_exposed_port(6379))
    # ... test using r
```

If an integration conftest already provides a Redis fixture, reuse it.

### Key Distinction: Three Redis Keyspaces

Do NOT confuse these three co-existing Redis keyspaces:

| Keyspace | Key Pattern | Value | Purpose |
|---|---|---|---|
| Peak cache (Layer A) | `aiops:baseline:{source}:{scope}:{metric_key}` | JSON `{baseline_value, computed_at, source}` | Latest baseline for hot-path comparison |
| Peak history (Layer B) | In-memory deque — not in Redis | N/A | Per-cycle peak profile computation |
| Seasonal baseline (Layer C, THIS STORY) | `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` | JSON `list[float]`, max 12 | 168-bucket time-aware baseline for MAD computation |

Layer C keys are what `SeasonalBaselineClient` manages. They use a completely different keyspace and value format from Layer A.

### Scope Construction

`seed_from_history()` receives scopes as `tuple[str, ...]`. These come from `build_evidence_scope_key(labels, metric_key)` in the backfill loop (already called for Layer A/B). Reuse the same scope values — do NOT re-derive scopes from labels in the seasonal seeding path.

The per-metric loop in `baseline_backfill.py` already builds `scope = build_evidence_scope_key(labels, metric_key)`. The seasonal seeding should use the same `scope` variable — no additional scope construction logic needed.

### Project Structure Notes

- **Modified files:**
  - `src/aiops_triage_pipeline/baseline/client.py` — add `seed_from_history()` method
  - `src/aiops_triage_pipeline/pipeline/baseline_backfill.py` — add `seasonal_baseline_client` param + Layer C seeding
  - `src/aiops_triage_pipeline/__main__.py` — construct `SeasonalBaselineClient` + pass to backfill
  - `tests/unit/baseline/test_client.py` — add `seed_from_history` tests
  - `tests/unit/pipeline/test_baseline_backfill.py` — add `_FakeSeasonalClient` + new tests + update existing call sites
  - `docs/runtime-modes.md` — add backfill layer documentation
  - `docs/developer-onboarding.md` — add baseline seeding mention

- **New files:**
  - `tests/integration/test_baseline_deviation.py` — Redis-backed integration test

- **Files NOT to touch:**
  - `baseline/constants.py` — no changes (constants already defined in Story 1.1)
  - `baseline/computation.py` — no changes (time_to_bucket already defined in Story 1.1)
  - `baseline/__init__.py` — stays empty (no exports)
  - Any `pipeline/stages/` file — Stage wiring is Story 2.3
  - `models/anomaly_finding.py` — Extension is Story 2.x
  - `baseline/models.py` — Pydantic models are Story 2.2 (leave as stub)
  - `pipeline/scheduler.py` — No changes to scheduler (only `__main__.py` wiring)

### Cross-Story Dependencies

**Depends on (DONE):**
- Story 1.1: `time_to_bucket()` in `baseline/computation.py`, `MAX_BUCKET_VALUES` in `baseline/constants.py`
- Story 1.2: `SeasonalBaselineClient` with `read_buckets()`, `update_bucket()`, `_build_key()` in `baseline/client.py`

**Blocks:**
- Story 1.4 (Weekly Recomputation): `bulk_recompute()` on `SeasonalBaselineClient` — a separate method, NOT this story
- Story 2.1 (MAD Engine): Reads from the same seasonal baseline Redis keys populated here
- Story 2.3 (Baseline Deviation Stage): Injects `SeasonalBaselineClient` for per-cycle reads

**Do NOT implement `bulk_recompute()` in this story** — that belongs to Story 1.4.

### Testing Discipline (from project-context.md)

- `asyncio_mode=auto` is set globally — `backfill_baselines_from_prometheus()` is async; use `async def` tests for it
- `SeasonalBaselineClient.seed_from_history()` is sync — use `def` tests (no `async def`)
- 0 skipped tests policy — do not use `pytest.mark.skip` or `pytest.mark.xfail`
- Type annotations on all test signatures: `def test_*(...)  -> None:`
- ruff `E,F,I,N,W` lint selection, line length 100 — no inline magic numbers

### Previous Story Learnings (Stories 1.1, 1.2)

From Story 1.1 code review (applied lessons for this story):
1. **Naive datetime guard in `time_to_bucket()`**: Already enforces `ValueError` for naive datetimes. Call `datetime.fromtimestamp(ts, tz=UTC)` (not `utcfromtimestamp`) to avoid passing naive datetimes to `seed_from_history`.
2. **Integer constant type assertions**: In `test_client.py`, integer constants need `isinstance(..., int)` checks alongside value equality. Apply same rigor to any integer assertions in new tests.
3. **Module-level imports**: All imports at module level. No import-inside-function except where critically needed (avoid ruff I001).
4. **No `noqa` for inactive rules**: Do not add `noqa` comments for rules not in active ruff select set (`E,F,I,N,W`).
5. **No `xfail` markers**: All tests must pass from the first run.

From Story 1.2 code review (applied lessons):
1. **Test key schema assertions**: Assert on `_EXPECTED_KEY in redis.store` (tests implementation), not on fixture constants (tautological). When testing `seed_from_history`, assert that the built Redis key matches the expected pattern `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}`.
2. **No invalid `noqa`**: `ARG002` and similar rules are not active. No `noqa` in `_Fake*` helper methods.
3. **E501 compliance**: Lines ≤ 100 chars. Extract long expected key strings into local helper constants `_SCOPE_STR`, `_EXPECTED_KEY` etc. to keep test lines short.
4. **Ruff clean**: Run `ruff check` on all modified files before marking done.

### References

- Architecture decision D3 (SeasonalBaselineClient interface): [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#D3]
- Architecture decision D5 (cold-start backfill extension): [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#D5]
- P2 (constants import): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P2]
- P3 (time_to_bucket sole source): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P3]
- P6 (`baseline_deviation_backfill_seeded` event name): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P6]
- FR22 (auto-discovery), FR23 (zero-code new metric), FR24 (new scope discovery): [Source: artifact/planning-artifacts/epics.md#FR22-FR24]
- NFR-P4 (backfill within 10 minutes), NFR-S3 (no code changes for new metrics): [Source: artifact/planning-artifacts/epics.md#NonFunctional-Requirements]
- Story 1.3 acceptance criteria: [Source: artifact/planning-artifacts/epics.md#Story-1.3]
- Existing backfill implementation: [Source: src/aiops_triage_pipeline/pipeline/baseline_backfill.py]
- SeasonalBaselineClient implementation: [Source: src/aiops_triage_pipeline/baseline/client.py]
- time_to_bucket implementation: [Source: src/aiops_triage_pipeline/baseline/computation.py]
- Existing test patterns: [Source: tests/unit/baseline/test_client.py, tests/unit/pipeline/test_baseline_backfill.py]
- Python 3.13 typing style, frozen models, structlog: [Source: artifact/project-context.md#Critical-Implementation-Rules]
- Test framework (pytest, asyncio_mode=auto, 0 skips): [Source: artifact/project-context.md#Testing-Rules]
- Full regression command: [Source: artifact/project-context.md#Testing-Rules]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation proceeded cleanly with no debug sessions required.

### Completion Notes List

- Added `seed_from_history()` to `SeasonalBaselineClient` using `time_to_bucket()` delegation, dict accumulator for bucket grouping, `read_buckets()` for merge, and `MAX_BUCKET_VALUES` cap enforcement.
- Added `_build_best_effort_scope()` helper to `baseline_backfill.py` to handle lag metrics (e.g., `consumer_group_lag`) where `build_evidence_scope_key()` raises `ValueError` due to missing `group` label — Layer C still seeds these metrics using a fallback scope.
- Extended `backfill_baselines_from_prometheus()` with `seasonal_baseline_client` parameter, Layer C collection using Unix→UTC datetime conversion (`datetime.fromtimestamp(ts, tz=UTC)`), and the canonical `baseline_deviation_backfill_seeded` log event.
- Wired `SeasonalBaselineClient` into `__main__.py` startup, constructed once before `asyncio.wait_for()`, not in the per-cycle loop.
- Integration tests in `tests/integration/test_baseline_deviation.py` were pre-written and are marked `@pytest.mark.integration` — they require Docker/Testcontainers.
- All 1201 unit tests pass, 0 skipped; ruff check clean.

### File List

- `src/aiops_triage_pipeline/baseline/client.py` — added `seed_from_history()` method; added `datetime` import and `time_to_bucket` import at module level
- `src/aiops_triage_pipeline/pipeline/baseline_backfill.py` — added `SeasonalBaselineClient` import; added `seasonal_baseline_client` parameter; added `_build_best_effort_scope()` helper; added Layer C collection and seeding loop; added `baseline_deviation_backfill_seeded` log event
- `src/aiops_triage_pipeline/__main__.py` — added `SeasonalBaselineClient` import; construct `seasonal_baseline_client` at startup; pass to `backfill_baselines_from_prometheus()`
- `tests/unit/baseline/test_client.py` — 8 new `seed_from_history` tests (pre-written as ATDD)
- `tests/unit/pipeline/test_baseline_backfill.py` — 4 new Layer C tests + updated all existing call sites to pass `seasonal_baseline_client` (pre-written as ATDD)
- `tests/integration/test_baseline_deviation.py` — 4 new Redis-backed integration tests (pre-written as ATDD, `@pytest.mark.integration`)
- `docs/runtime-modes.md` — added "Startup backfill" subsection documenting all three layers and configurable settings
- `docs/developer-onboarding.md` — added "Startup: Baseline Layer Seeding" section before Stage Flow

### Change Log

- 2026-04-05: Story 1.3 implemented — added `seed_from_history()` to `SeasonalBaselineClient`, extended `backfill_baselines_from_prometheus()` with Layer C seasonal baseline seeding, wired into `__main__.py` startup. All 1201 unit tests pass.
- 2026-04-05: Code review completed — 6 findings fixed (2 Medium, 4 Low). P3 violation (inline bucket derivation) fixed by importing and delegating to `time_to_bucket()`. `scope_count` log field corrected to track unique scopes (was counting (scope, metric_key) pairs). Module-level imports enforced in test files (`timedelta` added, inline `import json` removed). Invalid `# noqa: BLE001` removed. 8 new unit tests added for `_build_best_effort_scope()`. 1209 unit tests pass, 0 skipped.
