---
title: 'Prometheus 30-Day Baseline Backfill on Startup'
slug: 'prometheus-baseline-backfill'
created: '2026-04-05'
status: 'implementation-complete'
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8, 9]
tech_stack: ['Python 3.13', 'urllib.request (Prometheus HTTP)', 'Redis (baseline cache)', 'structlog', 'pydantic', 'asyncio']
files_to_modify:
  - 'src/aiops_triage_pipeline/integrations/prometheus.py'
  - 'src/aiops_triage_pipeline/__main__.py'
  - 'src/aiops_triage_pipeline/pipeline/baseline_store.py'
  - 'src/aiops_triage_pipeline/config/settings.py'
  - 'tests/unit/integrations/test_prometheus.py'
  - 'tests/unit/test_main.py'
  - 'tests/unit/pipeline/test_baseline_store.py'
code_patterns:
  - 'PrometheusClientProtocol structural protocol for client abstraction'
  - 'PrometheusHTTPClient uses urllib.request.urlopen with 5s timeout'
  - 'build_metric_queries() returns dict[str, MetricQueryDefinition] from frozen contract YAML'
  - '_PeakHistoryRetention uses dict[3-tuple, deque[float]] with bounded maxlen'
  - 'baseline_store uses Redis SET/GET with JSON serialization and env-specific TTL'
  - '_compute_baselines_from_rows() takes MAX value per scope per metric'
  - 'Scopes: 3-tuple (env, cluster_id, topic) for topic metrics; 4-tuple adds group for lag metrics'
test_patterns:
  - 'tests/unit/integrations/test_prometheus.py — metric query building, label normalization'
  - 'tests/unit/test_main.py — _PeakHistoryRetention bounds, _load_peak_baseline_windows'
  - 'tests/unit/pipeline/test_baseline_store.py — cache key format, batch reads, TTL, degradation'
  - 'tests/integration/integrations/test_prometheus_local.py — real Prometheus container'
  - 'tests/integration/pipeline/test_evidence_prometheus_integration.py — stage 1→2 flow'
---

# Tech-Spec: Prometheus 30-Day Baseline Backfill on Startup

**Created:** 2026-04-05

## Overview

### Problem Statement

Every application restart loses all in-memory peak history (`_PeakHistoryRetention`), forcing the pipeline to operate with `INSUFFICIENT_HISTORY` for many scheduler cycles until baselines rebuild organically. This degrades anomaly detection and peak classification quality during the warm-up period.

### Solution

On hot-path startup, before the first scheduler cycle, query Prometheus with `query_range()` over a 30-day lookback (at 300s step intervals matching the scheduler cycle) for all 9 metrics in `prometheus-metrics-contract-v1.yaml`. Use the results to backfill both the in-memory peak history deque (Layer B) and refresh the Redis baseline cache (Layer A). This blocks the hot path until complete, so the first cycle operates with full historical context.

### Scope

**In Scope:**
- New `query_range()` capability in Prometheus integration
- Backfill logic that runs at hot-path startup (blocking)
- Populate `_PeakHistoryRetention` deque from range query results
- Refresh Redis baseline cache with latest values from range query
- All 9 metrics from `prometheus-metrics-contract-v1.yaml`

**Out of Scope:**
- Changes to peak profile computation logic (it rebuilds naturally)
- Changes to the scheduler cycle interval or evidence stage flow
- Persistent on-disk storage of history (Redis + Prometheus lookback replaces the need)
- Cold-path changes

## Context for Development

### Codebase Patterns

- **Prometheus client** (`integrations/prometheus.py`): `PrometheusHTTPClient` class uses `urllib.request.urlopen` with 5s timeout. Implements `PrometheusClientProtocol` (structural protocol). Only has `query_instant(metric_name, at_time) -> list[dict]` today. Returns normalized `{"labels": dict, "value": float}` records, filtering NaN/Inf. Uses `/api/v1/query` endpoint.
- **Metric query building** (`integrations/prometheus.py:78-90`): `build_metric_queries()` loads `prometheus-metrics-contract-v1.yaml` and returns `dict[str, MetricQueryDefinition]` keyed by metric_key (e.g. `"topic_messages_in_per_sec"`). `MetricQueryDefinition` is a frozen dataclass with `metric_key`, `metric_name` (canonical PromQL name), and `role`.
- **Baseline persistence** (`pipeline/baseline_store.py`): Redis SET/GET with JSON payload `{"baseline_value": float, "computed_at": iso8601, "source": str}`. Key format: `aiops:baseline:{source}:{scope_key}:{metric_key}`. TTL from `redis_ttl_policy.ttls_by_env[env].peak_profile_seconds`. Uses `mget()` for bulk reads.
- **Baseline computation** (`pipeline/stages/evidence.py:313-332`): `_compute_baselines_from_rows()` takes MAX value across all samples per scope per metric. Scopes are 3-tuples `(env, cluster_id, topic)` for topic metrics, 4-tuples `(env, cluster_id, group, topic)` for lag metrics.
- **Peak history retention** (`__main__.py:157-260`): `_PeakHistoryRetention` class. `_history_by_scope: dict[tuple[str,str,str], deque[float]]` with `maxlen=max_depth`. `update()` accepts 3-tuple scopes only and appends one float per scope per call. Returns `dict[3-tuple, tuple[float, ...]]`.
- **Peak baseline window loading** (`__main__.py:1021-1047`): `_load_peak_baseline_windows()` loads ONE value from Redis per scope (`topic_messages_in_per_sec` only), passes to `_PeakHistoryRetention.update()`.
- **Scheduler loop** (`__main__.py:498-960`): `_hot_path_scheduler_loop()` is async. Creates `_PeakHistoryRetention` at line 527 with `max_depth=settings.STAGE2_PEAK_HISTORY_MAX_DEPTH`. The `while True` loop starts after initialization.
- **Evidence collection** (`pipeline/stages/evidence.py:225-301`): `collect_prometheus_samples_with_diagnostics()` is async, uses `asyncio.to_thread()` for blocking HTTP calls. Per-metric isolation — one failure doesn't prevent others.

### Files to Reference

| File | Purpose | Key Lines |
| ---- | ------- | --------- |
| `src/aiops_triage_pipeline/integrations/prometheus.py` | Prometheus client — add `query_range()` here, extend `PrometheusClientProtocol` | 20-25 (protocol), 37-68 (client), 78-90 (query builder) |
| `src/aiops_triage_pipeline/__main__.py` | `_PeakHistoryRetention` — add `seed()` method; backfill injection point in scheduler loop init | 157-260 (retention class), 527 (creation), 1021-1047 (load windows) |
| `src/aiops_triage_pipeline/pipeline/baseline_store.py` | Redis baseline persistence — used for Layer A refresh | 30-38 (key format), 60-110 (load), 113-149 (persist) |
| `src/aiops_triage_pipeline/config/settings.py` | Add `BASELINE_BACKFILL_LOOKBACK_DAYS` setting; update `STAGE2_PEAK_HISTORY_MAX_DEPTH` default | 103-104 (PROMETHEUS_URL, interval), 119-120 (peak history settings) |
| `src/aiops_triage_pipeline/pipeline/stages/evidence.py` | Evidence stage — scope building and baseline computation patterns to follow | 57-80 (scope keys), 313-332 (baseline MAX computation) |
| `src/aiops_triage_pipeline/pipeline/stages/peak.py` | Peak stage — consumes `historical_windows_by_scope` | 70-88 (collect_peak_stage_output signature) |
| `config/policies/prometheus-metrics-contract-v1.yaml` | All 9 canonical metric names | Full file |
| `config/policies/redis-ttl-policy-v1.yaml` | TTL: local=1h, dev=2h, uat=4h, prod=24h | Full file |
| `tests/unit/integrations/test_prometheus.py` | Existing Prometheus unit tests — add `query_range()` tests here | |
| `tests/unit/test_main.py` | Existing peak history retention tests — add `seed()` and backfill tests here | 538, 551, 587, 623 |
| `tests/unit/pipeline/test_baseline_store.py` | Existing baseline store tests | |

### Technical Decisions

- **Blocking startup**: Backfill blocks inside `_hot_path_scheduler_loop()` before the `while True` loop to ensure full context from cycle 1.
- **Step interval = 300s**: Matches `HOT_PATH_SCHEDULER_INTERVAL_SECONDS` for 1:1 history point alignment.
- **30-day lookback**: Configurable via new `BASELINE_BACKFILL_LOOKBACK_DAYS` setting (default 30).
- **All 9 metrics to Redis (Layer A)**: Full contract coverage — latest MAX per scope per metric persisted to Redis baseline cache.
- **`topic_messages_in_per_sec` to peak history (Layer B)**: Per-step MAX per scope over the 30-day range, seeded directly into `_PeakHistoryRetention` deque.
- **`STAGE2_PEAK_HISTORY_MAX_DEPTH` increased to 8640**: 30 days x 24h x 12 intervals/h = 8,640 data points per scope. Memory estimate: ~138MB worst case at 2,000 scopes.
- **Two-layer backfill**: Layer A (Redis) gets all 9 metrics' latest value. Layer B (in-memory deque) gets `topic_messages_in_per_sec` time-series for peak profile computation.
- **New `seed()` method on `_PeakHistoryRetention`**: Bulk-loads historical values into deques without incrementing the cycle counter or triggering eviction logic.
- **Scope discovery from range query results**: No separate cardinality query needed — scopes are extracted from the Prometheus response labels using the same `normalize_labels()` + `build_evidence_scope_key()` pattern.
- **Longer HTTP timeout for range queries**: 30-day range queries return large payloads; `query_range()` should use a configurable timeout (e.g. 60s) vs the 5s instant query timeout.
- **Total backfill timeout**: `BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS` (default 300s / 5 min) caps the entire backfill wall-clock time. Prevents slow Prometheus from blocking startup indefinitely.
- **`seed()` safety guard**: `RuntimeError` if called after first `update()`. Prevents latent bug where seeded scopes get stale-evicted due to `_last_seen_cycle=0` vs current cycle.
- **Startup memory log**: After seeding, log estimated memory footprint to help operators tune `MAX_SCOPES` in high-cardinality environments.

## Implementation Plan

### Tasks

- [x] Task 1: Add `query_range()` to Prometheus client and protocol
  - File: `src/aiops_triage_pipeline/integrations/prometheus.py`
  - Action: Extend `PrometheusClientProtocol` (line 20-25) with `query_range(self, metric_name: str, start: datetime, end: datetime, step_seconds: int) -> list[dict[str, object]]` method signature.
  - Action: Implement `query_range()` in `PrometheusHTTPClient` (after line 68):
    - Build URL: `/api/v1/query_range?query={metric}&start={iso8601}&end={iso8601}&step={step_seconds}s`
    - Use `urllib.request.urlopen` with configurable timeout (default 60s, vs 5s for instant).
    - Parse response: validate `status == "success"` and `resultType == "matrix"`.
    - Return normalized records: `[{"labels": dict[str, str], "values": list[tuple[float, float]]}]` where each tuple is `(unix_timestamp, metric_value)`.
    - Filter NaN/Inf values from each `(timestamp, value)` pair, consistent with `query_instant()` pattern.
  - Notes: Prometheus `/api/v1/query_range` returns `{"data": {"resultType": "matrix", "result": [{"metric": {...}, "values": [[ts, "val"], ...]}]}}`. Values are string-encoded floats.

- [x] Task 2: Add configuration settings for backfill
  - File: `src/aiops_triage_pipeline/config/settings.py`
  - Action: Add `BASELINE_BACKFILL_LOOKBACK_DAYS: int = 30` setting (near line 104, alongside `PROMETHEUS_URL`).
  - Action: Add `BASELINE_BACKFILL_TIMEOUT_SECONDS: int = 60` setting for range query HTTP timeout.
  - Action: Add `BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS: int = 300` setting — maximum wall-clock time for the entire backfill across all metrics. If exceeded, log warning and proceed with whatever was backfilled so far.
  - Action: Change `STAGE2_PEAK_HISTORY_MAX_DEPTH: int = 8640` default (line 119) from 12 to 8640.
  - Notes: 8640 = 30 days x 24h x 12 intervals/h. Existing deployments may override via env var. Total timeout prevents a slow Prometheus from blocking startup indefinitely.

- [x] Task 3: Add `seed()` method to `_PeakHistoryRetention`
  - File: `src/aiops_triage_pipeline/__main__.py`
  - Action: Add method to `_PeakHistoryRetention` class (after `update()`, before `_evict_oldest_scope()`):
    ```python
    def seed(
        self,
        *,
        history_by_scope: dict[tuple[str, str, str], Sequence[float]],
    ) -> None:
    ```
  - Action: Implementation logic:
    - **Safety guard**: If `self._cycle > 0`, raise `RuntimeError("seed() must be called before first update()")`. This prevents seeded scopes from being immediately stale-evicted (since `_last_seen_cycle_by_scope` would be set to 0, making them look stale relative to the current cycle).
    - For each scope in `history_by_scope`:
      - If scope not already in `_history_by_scope`, create new `deque(maxlen=self._max_depth)`.
      - Extend the deque with the provided values (deque maxlen auto-truncates to most recent).
      - Set `_last_seen_cycle_by_scope[scope] = self._cycle` (marks as active).
    - Respect `_max_scopes` limit: skip scopes beyond capacity (log warning if skipped).
    - Do NOT increment `_cycle` (seeding is not a cycle).
    - Do NOT trigger stale eviction (no cycles have passed yet).
  - Notes: `deque.extend()` with `maxlen` naturally keeps the most recent N values if input exceeds capacity. The safety guard is critical — without it, seeded scopes would have `_last_seen_cycle=0` and become stale-eviction candidates as soon as `_cycle > max_idle_cycles`.

- [x] Task 4: Create baseline backfill module
  - File: `src/aiops_triage_pipeline/pipeline/baseline_backfill.py` (NEW)
  - Action: Create module with the following function:
    ```python
    async def backfill_baselines_from_prometheus(
        *,
        prometheus_client: PrometheusHTTPClient,
        metric_queries: dict[str, MetricQueryDefinition],
        redis_client: BaselineStoreClientProtocol,
        redis_ttl_policy: RedisTtlPolicyV1,
        peak_history_retention: _PeakHistoryRetention,
        lookback_days: int,
        step_seconds: int,
        timeout_seconds: int,
        total_timeout_seconds: int,
        logger: structlog.BoundLogger,
    ) -> None:
    ```
  - Action: Implementation flow:
    1. Compute `start = now - timedelta(days=lookback_days)`, `end = now`. Record `backfill_start_time = time.monotonic()`.
    2. For each metric in `metric_queries`:
       - **Check total timeout**: If `time.monotonic() - backfill_start_time > total_timeout_seconds`, log warning with metrics completed vs remaining, break out of loop.
       - Call `prometheus_client.query_range(metric_name, start, end, step_seconds)` via `asyncio.to_thread()` (follows existing async-wrapping pattern from evidence collection).
       - On failure (URLError, TimeoutError, ValueError): log warning, continue to next metric (per-metric isolation).
    3. Normalize labels and build scopes using `normalize_labels()` + `build_evidence_scope_key()` from `pipeline/stages/evidence.py`.
    4. **Layer A (Redis baseline cache)**: For each metric, at the LAST timestamp step, compute MAX value per scope. Call `persist_metric_baselines()` with these values.
    5. **Layer B (Peak history deque)**: For `topic_messages_in_per_sec` only — for each scope, at each timestamp step, compute MAX across all series (partitions/instances). Build ordered `list[float]` of MAX values sorted by timestamp ascending. Call `peak_history_retention.seed(history_by_scope=...)`.
    6. **Log memory footprint**: After seeding, log total scopes seeded and estimated memory usage (`sum(len(deque) for deque in history_by_scope.values()) * 8` bytes for floats, plus Python object overhead estimate).
    7. Log summary: total scopes backfilled, metrics succeeded/failed, data points loaded, wall-clock duration.
  - Notes: Scope construction must use the same `normalize_labels()` and scope-building logic as evidence stage to ensure key consistency. Import from `pipeline/stages/evidence.py`.

- [x] Task 5: Wire backfill into hot-path scheduler loop
  - File: `src/aiops_triage_pipeline/__main__.py`
  - Action: In `_hot_path_scheduler_loop()`, after `peak_history_retention` creation (line 527-532) and before the `while True` loop:
    ```python
    await backfill_baselines_from_prometheus(
        prometheus_client=prometheus_client,
        metric_queries=metric_queries,
        redis_client=redis_client,
        redis_ttl_policy=redis_ttl_policy,
        peak_history_retention=peak_history_retention,
        lookback_days=settings.BASELINE_BACKFILL_LOOKBACK_DAYS,
        step_seconds=interval_seconds,
        timeout_seconds=settings.BASELINE_BACKFILL_TIMEOUT_SECONDS,
        total_timeout_seconds=settings.BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS,
        logger=logger,
    )
    ```
  - Action: Import `backfill_baselines_from_prometheus` from `pipeline.baseline_backfill`.
  - Notes: This is blocking (awaited) so the first scheduler cycle has full context. If Prometheus is unreachable or total timeout is exceeded, the backfill logs warnings and returns — the pipeline starts in degraded mode as it does today.

- [x] Task 6: Unit tests for `query_range()`
  - File: `tests/unit/integrations/test_prometheus.py`
  - Action: Add tests:
    - `test_query_range_returns_matrix_results()` — Mock HTTP response with matrix resultType, verify normalized output structure with `(timestamp, value)` tuples.
    - `test_query_range_filters_nan_inf_values()` — Verify NaN/Inf filtering at individual data points within a series.
    - `test_query_range_raises_on_non_success_status()` — Verify ValueError on bad Prometheus response.
    - `test_query_range_raises_on_non_matrix_result_type()` — Verify ValueError if resultType != "matrix".
    - `test_query_range_builds_correct_url_params()` — Verify start/end/step URL encoding.
  - Notes: Follow existing test patterns from `test_build_metric_queries_*` tests.

- [x] Task 7: Unit tests for `_PeakHistoryRetention.seed()`
  - File: `tests/unit/test_main.py`
  - Action: Add tests:
    - `test_peak_history_retention_seed_populates_history()` — Seed with known values, verify `update()` returns them in subsequent calls.
    - `test_peak_history_retention_seed_respects_max_depth()` — Seed with more values than `max_depth`, verify deque truncates to most recent.
    - `test_peak_history_retention_seed_respects_max_scopes()` — Seed with more scopes than `max_scopes`, verify excess skipped.
    - `test_peak_history_retention_seed_does_not_increment_cycle()` — Verify `_cycle` remains 0 after seed.
    - `test_peak_history_retention_seed_then_update_appends()` — Seed, then call `update()`, verify seeded values + new value are present and oldest seeded values are truncated first when deque maxlen is exceeded.
    - `test_peak_history_retention_seed_raises_after_first_update()` — Call `update()` first, then `seed()`, verify `RuntimeError` is raised.
  - Notes: Follow existing test patterns from `test_peak_history_retention_bounds_depth_*` tests.

- [x] Task 8: Unit tests for backfill orchestration
  - File: `tests/unit/pipeline/test_baseline_backfill.py` (NEW)
  - Action: Add tests:
    - `test_backfill_persists_latest_max_to_redis_for_all_metrics()` — Mock Prometheus range response for multiple metrics, verify `persist_metric_baselines()` called with correct latest MAX values.
    - `test_backfill_seeds_peak_history_with_topic_messages_timeseries()` — Verify `seed()` called with ordered MAX values per scope from `topic_messages_in_per_sec` only.
    - `test_backfill_aggregates_max_across_partitions_per_timestamp()` — Multiple series for same scope (different partitions), verify MAX aggregation at each step.
    - `test_backfill_continues_on_individual_metric_failure()` — One metric query fails, verify others still processed (per-metric isolation).
    - `test_backfill_handles_empty_prometheus_response()` — Empty results for all metrics, verify no errors and no data persisted.
    - `test_backfill_builds_correct_scopes_from_labels()` — Verify scope construction matches evidence stage pattern (3-tuple for topic metrics, 4-tuple for lag metrics).
    - `test_backfill_respects_total_timeout()` — Set total timeout to near-zero, verify backfill exits early with warning log and processes only the metrics completed before timeout.
    - `test_backfill_with_partial_prometheus_retention()` — Prometheus returns only 7 days of data (not 30), verify backfill seeds with available data (~2,016 values per scope) without error.
    - `test_backfill_logs_memory_footprint_after_seeding()` — Verify structured log event emitted with scope count and estimated memory usage.
  - Notes: Use mock Prometheus client and mock Redis client.

- [x] Task 9: Backfill wiring integration test
  - File: `tests/unit/test_main.py`
  - Action: Add test:
    - `test_hot_path_scheduler_loop_calls_backfill_before_first_cycle()` — Mock `backfill_baselines_from_prometheus`, verify it is called exactly once with correct parameters during `_hot_path_scheduler_loop` initialization, and that the first scheduler cycle runs after backfill completes.
  - Notes: This tests the critical integration seam between Task 5 (wiring) and Task 4 (backfill module). Use `unittest.mock.patch` on the imported function.

### Acceptance Criteria

- [x] AC 1: Given a fresh application startup with Prometheus containing 30 days of metric history, when the hot-path scheduler loop initializes, then `_PeakHistoryRetention` is seeded with up to 8,640 `topic_messages_in_per_sec` MAX values per scope before the first scheduler cycle executes.

- [x] AC 2: Given a fresh application startup with Prometheus containing 30 days of metric history, when the backfill completes, then the Redis baseline cache contains the latest MAX value per scope for all 9 metrics in the contract.

- [x] AC 3: Given Prometheus is unreachable during startup backfill, when `query_range()` fails for all metrics, then the backfill logs warnings and returns without error, allowing the pipeline to start in degraded mode (same as today's cold-start behavior).

- [x] AC 4: Given a `query_range()` call for a metric that returns multiple time series per scope (e.g., multiple partitions), when computing baseline values, then the MAX value across all series is used at each timestamp step (consistent with `_compute_baselines_from_rows()` behavior).

- [x] AC 5: Given `BASELINE_BACKFILL_LOOKBACK_DAYS=30` and `HOT_PATH_SCHEDULER_INTERVAL_SECONDS=300`, when `query_range()` is called, then the query uses `start=now-30d`, `end=now`, `step=300s`.

- [x] AC 6: Given the `_PeakHistoryRetention.seed()` method receives more values than `max_depth` for a scope, when seeding, then only the most recent `max_depth` values are retained (deque maxlen truncation).

- [x] AC 7: Given one metric's range query fails (e.g., timeout) during backfill, when other metrics succeed, then the successful metrics are still backfilled to both Redis and peak history (per-metric isolation).

- [x] AC 8: Given `STAGE2_PEAK_HISTORY_MAX_DEPTH` is set to 8640, when the application runs normally after backfill, then `_PeakHistoryRetention.update()` continues appending values correctly to the pre-seeded deques, with oldest seeded values truncated first when deque capacity is reached.

- [x] AC 9: Given `seed()` is called after `update()` has already been called at least once, when `seed()` executes, then it raises `RuntimeError("seed() must be called before first update()")`.

- [x] AC 10: Given the total backfill timeout (`BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS=300`) is exceeded during metric queries, when the timeout is detected, then the backfill logs a warning with completed vs remaining metrics, stops querying further metrics, and proceeds with whatever data was successfully collected.

- [x] AC 11: Given Prometheus has only 7 days of retention (less than the configured 30-day lookback), when `query_range()` returns partial data, then the backfill seeds the available history without error and logs the actual data range received.

- [x] AC 12: Given the backfill completes successfully, when the summary is logged, then the structured log event includes: total scopes seeded, metrics succeeded/failed count, data points loaded, estimated memory footprint, and wall-clock duration.

## Additional Context

### Dependencies

- **Prometheus server**: Must support `/api/v1/query_range` endpoint (standard since Prometheus 2.x; project uses v2.50.1).
- **30-day retention**: Prometheus must be configured with sufficient retention to serve 30 days of data. Default Prometheus retention is 15 days — verify production Prometheus has `--storage.tsdb.retention.time=30d` or greater.
- **No new Python packages**: Uses existing `urllib.request` for HTTP, no new dependencies needed.
- **Redis**: No schema changes — uses existing `persist_metric_baselines()` with same key format and TTL policy.

### Testing Strategy

**Unit Tests (Tasks 6, 7, 8):**
- Mock `PrometheusHTTPClient` with canned matrix responses for `query_range()`.
- Mock Redis client for baseline persistence verification.
- Test `_PeakHistoryRetention.seed()` in isolation with known data.
- Verify scope construction consistency between backfill and evidence stage.

**Integration Tests:**
- Extend `tests/integration/integrations/test_prometheus_local.py` with a `query_range()` test against real Prometheus container if feasible (requires seeding historical data into Prometheus, which may be complex).
- Primary integration validation: manual startup test against a Prometheus instance with real metric history.

**Manual Testing:**
- Start pipeline against dev/UAT Prometheus with 30 days of Kafka metrics.
- Verify log output: backfill summary with scope count, metric success/failure, data point count.
- Verify first scheduler cycle produces peak profiles with `has_sufficient_history=True`.
- Verify Redis baseline keys populated for all 9 metrics using `redis-cli KEYS aiops:baseline:*`.

**Regression:**
- Run full unit suite: `uv run pytest -q tests/unit`
- Verify existing `_PeakHistoryRetention` tests still pass with new `max_depth=8640` default.
- Verify existing baseline store tests still pass (no schema changes).

### Notes

**High-risk items:**
- **Prometheus retention mismatch**: If production Prometheus has <30 days retention, `query_range()` returns partial data. The backfill handles this gracefully (seeds whatever is available), but peak profiles may still show `INSUFFICIENT_HISTORY` if data is too sparse. Document the Prometheus retention requirement.
- **Large response payloads**: 30 days x 300s step x 9 metrics x N scopes can produce large HTTP responses. The 60s timeout and per-metric isolation mitigate this, but very high-cardinality environments may need tuning.
- **Memory increase**: `STAGE2_PEAK_HISTORY_MAX_DEPTH` going from 12 to 8640 is a 720x increase per scope. At 2,000 scopes max, worst case is ~138MB. Monitor memory usage after deployment.

**Known limitations:**
- Backfill only runs at startup. If the pipeline runs continuously for >30 days without restart, the in-memory history naturally grows beyond what the initial backfill provided.
- The backfill does not populate the sustained window state (`SustainedWindowState`) — this still builds up organically per cycle.

**Future considerations (out of scope):**
- Periodic re-backfill (e.g., weekly refresh) to correct any drift between in-memory history and Prometheus ground truth.
- Configurable per-metric backfill (only backfill specific metrics rather than all 9).
- Prometheus recording rules to pre-aggregate MAX per scope, reducing range query payload size.

## Adversarial Review Resolution

**Review conducted:** 2026-04-05. All 11 findings (F1–F11) resolved.

| Finding | Severity | Resolution |
|---------|----------|------------|
| F1: No hard timeout enforcement | High | Wrapped `backfill_baselines_from_prometheus()` call in `asyncio.wait_for()` with `BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS`; `asyncio.TimeoutError` caught and logged as warning. |
| F2: Unhandled exceptions crash scheduler | High | Added `except Exception` block around the entire backfill call in `_hot_path_scheduler_loop()`; logs with `exc_info=True` and continues. |
| F3: `seed()` silently drops excess scopes | Medium | Added `logger.warning("peak_history_seed_scope_limit_reached", ...)` when `max_scopes` is reached, providing operational visibility. |
| F4: No validator for `TIMEOUT > TOTAL_TIMEOUT` | Medium | Added `@model_validator(mode="after")` in `settings.py` that raises `ValueError` if `BASELINE_BACKFILL_TIMEOUT_SECONDS >= BASELINE_BACKFILL_TOTAL_TIMEOUT_SECONDS`. |
| F5: `STAGE2_PEAK_HISTORY_MAX_DEPTH=8640` allowed for dev/uat | Medium | Updated `validate_peak_depth_not_default_for_named_envs` to reject both the old default (12) and new default (8640) for dev/uat environments. |
| F6: Double `normalize_labels()` call | Medium | Removed redundant `normalize_labels()` pre-call; `build_evidence_scope_key(labels, metric_key)` normalizes internally. |
| F7: No cardinality warning for large scope counts | Low | Added `_LARGE_SCOPE_WARN_THRESHOLD = 500`; emits `baseline_backfill_large_scope_count` warning with estimated intermediate memory before seeding. |
| F8: Default `TOTAL_TIMEOUT = 300` conflicts with validator | Low | Changed default to 270 (< `HOT_PATH_SCHEDULER_INTERVAL_SECONDS=300`); added cross-field validator that raises if `TOTAL_TIMEOUT >= SCHEDULER_INTERVAL`. |
| F9: Layer A uses last-series value, not latest-timestamp value | Low | Refactored Layer A accumulation to track `(latest_ts, latest_val)` pairs per scope/metric; updates only when new `ts > existing_ts` or equal ts with higher val. |
| F10: Misleading `remaining_metrics` variable name | Low | Renamed to `all_metrics` at point of iteration. |
| F11: Memory formula uses `step_seconds` instead of values count | Low | Fixed formula to `total_values * 8 + len(history_by_scope) * 200` where `total_values = sum(len(v) for v in history_by_scope.values())`. |
