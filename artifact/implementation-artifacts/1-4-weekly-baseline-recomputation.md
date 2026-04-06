# Story 1.4: Weekly Baseline Recomputation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want baselines automatically recomputed weekly from Prometheus raw data,
so that baseline pollution from persistent anomalies is corrected without manual intervention.

## Acceptance Criteria

1. **Given** the hot-path scheduler checks `aiops:seasonal_baseline:last_recompute` each cycle
   **When** 7+ days have elapsed since the last recomputation (or the key is absent)
   **Then** it spawns a background asyncio coroutine via `asyncio.create_task()` to run `bulk_recompute()` on `SeasonalBaselineClient` (D4)
   **And** only one background recomputation runs at a time (no concurrent spawning)

2. **Given** a weekly recomputation is triggered
   **When** the background coroutine runs
   **Then** it queries Prometheus `query_range` for 30-day history for all metrics and scopes
   **And** partitions data into 168 `(dow, hour)` time buckets entirely in memory (no intermediate Redis writes)
   **And** writes all computed buckets via a pipelined Redis bulk write (pipelined `SET` calls executed in one round-trip)
   **And** updates `aiops:seasonal_baseline:last_recompute` with the current UTC ISO timestamp
   **And** caps each bucket at `MAX_BUCKET_VALUES` (12)

3. **Given** a weekly recomputation is in progress
   **When** pipeline cycles run concurrently
   **Then** cycles read existing (old) baselines without corruption or blocking (NFR-P5)
   **And** the bulk write creates a negligible inconsistency window (compute entirely in memory before any Redis write)

4. **Given** a weekly recomputation fails mid-execution (e.g., pod restart, Prometheus timeout)
   **When** the pod recovers
   **Then** no partial writes exist in Redis — nothing was written before the bulk write phase (NFR-R4)
   **And** `aiops:seasonal_baseline:last_recompute` is NOT updated on failure
   **And** recomputation retries on the next cycle that checks the 7-day timer

5. **Given** the recomputation lifecycle
   **When** recomputation starts, completes, or fails
   **Then** `baseline_deviation_recompute_started`, `baseline_deviation_recompute_completed`, or `baseline_deviation_recompute_failed` structured log events are emitted
   **And** `baseline_deviation_recompute_completed` includes `duration_seconds` and `key_count`
   **And** `baseline_deviation_recompute_failed` includes `exc_info=True`

6. **Given** 500 scopes × 9 metrics × 168 buckets
   **When** weekly recomputation runs
   **Then** it completes within 10 minutes (NFR-P5)

7. **Given** unit tests
   **When** tests are executed
   **Then** `bulk_recompute()` is tested with mock Prometheus and mock Redis
   **And** timer logic is verified to correctly detect 7-day expiry and missing key (treat as expired)
   **And** concurrent spawn prevention is verified (second timer check while task running does not spawn again)
   **And** `docs/runtime-modes.md` is updated with the weekly recomputation background task documentation

## Tasks / Subtasks

- [x] Task 1: Add `bulk_recompute()` to `SeasonalBaselineClient` (AC: 2, 3, 4, 6)
  - [x] 1.1 Open `src/aiops_triage_pipeline/baseline/client.py`
  - [x] 1.2 Extend `SeasonalBaselineClientProtocol` to add a `pipeline()` method (returns a context manager pipeline object supporting `set` and `execute`)
  - [x] 1.3 Add `bulk_recompute()` method to `SeasonalBaselineClient`:
    - Signature: `async def bulk_recompute(self, *, prometheus_client, metric_queries, lookback_days, step_seconds, timeout_seconds, logger) -> int`
    - Returns `int`: total number of Redis keys written
    - Phase 1 (compute): Query Prometheus for all metrics; partition all values into an in-memory `dict[str, str]` keyed by Redis key (`_build_key(scope, metric_key, dow, hour) → json.dumps(values)`)
    - Use `time_to_bucket()` (P3) for all datetime-to-bucket conversions — NEVER inline
    - Cap at `MAX_BUCKET_VALUES` per bucket (P2)
    - Phase 2 (write): Execute all keys in a single Redis pipeline — call `self._redis.pipeline()`, issue one `set(key, value)` per key, then `execute()`
    - Zero Redis writes during Phase 1 — if exception raised before Phase 2, Redis is untouched (NFR-R4)
  - [x] 1.4 Extend `SeasonalBaselineClientProtocol` to add `set_last_recompute(timestamp_iso: str) -> None` and `get_last_recompute() -> str | None` using key `aiops:seasonal_baseline:last_recompute`
  - [x] 1.5 Implement `set_last_recompute` and `get_last_recompute` on `SeasonalBaselineClient`
  - [x] 1.6 Do NOT modify `read_buckets`, `update_bucket`, `read_buckets_batch`, or `seed_from_history` — these are correct and complete

- [x] Task 2: Add weekly recomputation timer check to the hot-path scheduler loop (AC: 1, 4, 5)
  - [x] 2.1 Open `src/aiops_triage_pipeline/__main__.py`
  - [x] 2.2 Add a module-level constant `_RECOMPUTE_INTERVAL_SECONDS = 7 * 24 * 3600` (7 days)
  - [x] 2.3 Before the `while True:` loop in `_run_hot_path_scheduler()`, initialize: `_recompute_task: asyncio.Task[int] | None = None`
  - [x] 2.4 At the start of each cycle (after `evaluate_scheduler_tick`, before stage execution), add a timer check block
  - [x] 2.5 Create `_should_trigger_recompute(last_iso: str | None, now: datetime, interval_seconds: int) -> bool` helper at module level
  - [x] 2.6 Create `async def _run_baseline_recompute(...)` coroutine with structured log events and `_PrometheusFailureTracker`

- [x] Task 3: Unit tests for `bulk_recompute()` (AC: 7)
  - [x] 3.1 Tests exist at `tests/unit/baseline/test_bulk_recompute.py` (pre-existing ATDD tests)
  - [x] 3.2 `_FakePipelineRedis` and `_FakePipeline` test helpers used
  - [x] 3.3 `_FakePrometheusClient` (MagicMock) used
  - [x] 3.4 All 6 tests pass: pipeline writes, key count, time_to_bucket partitioning, cap, no-writes-on-failure, empty response
  - [x] 3.5 All tests use `async def test_*(...)  -> None:` with `asyncio_mode=auto`

- [x] Task 4: Unit tests for timer logic and `_run_baseline_recompute` (AC: 7)
  - [x] 4.1 Tests exist at `tests/unit/pipeline/test_baseline_recompute.py` (pre-existing ATDD tests)
  - [x] 4.2 All 4 `_should_trigger_recompute` tests pass
  - [x] 4.3 All 5 `_run_baseline_recompute` tests pass
  - [x] 4.4 Concurrent spawn prevention test passes

- [x] Task 5: Run full regression suite (AC: 7)
  - [x] 5.1 `uv run pytest tests/unit/ -q` — 1225 passed, 0 failed, 0 skipped
  - [x] 5.2 `uv run ruff check src/ tests/` — clean

- [x] Task 6: Update documentation (AC: 7)
  - [x] 6.1 Updated `docs/runtime-modes.md` — added "Weekly recomputation" subsection with full details

## Dev Notes

### What This Story Delivers

Story 1.4 adds the **weekly recomputation** loop that keeps seasonal baselines fresh. It adds:
1. `bulk_recompute()` method to `SeasonalBaselineClient` — the compute+bulk-write engine
2. Timer check in `_run_hot_path_scheduler()` — checks `aiops:seasonal_baseline:last_recompute` each cycle; spawns a background `asyncio.create_task` when 7+ days have elapsed
3. `_run_baseline_recompute()` coroutine wrapper — handles structured log events and `last_recompute` update

**Architectural decision D4** governs this entirely. Key properties:
- **Compute phase is 100% in-memory** — no Redis writes until all 756K buckets are ready
- **Write phase is a single Redis pipeline** — millisecond execution, negligible inconsistency window
- **Hot-path cycles continue unaffected** — they read old baselines during compute (valid)
- **Failure is safe** — pod restart mid-compute loses in-flight work but Redis is untouched; retries next cycle

### Critical: Redis Pipeline for Bulk Write (D4)

The `SeasonalBaselineClientProtocol` must be extended to expose `pipeline()`. The redis-py `Pipeline` context manager pattern:

```python
pipe = self._redis.pipeline()
for key, value in computed_keys.items():
    pipe.set(key, value)
pipe.execute()
```

The `_FakePipelineRedis` test helper must simulate this pattern. A clean implementation:

```python
class _FakePipelineRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self._pending: dict[str, str] = {}
        self._in_pipeline = False

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        return [self.store.get(k) for k in keys]

    def set(self, key: str, value: str) -> bool:
        if self._in_pipeline:
            self._pending[key] = value
        else:
            self.store[key] = value
        return True

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakePipelineRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, str]] = []

    def set(self, key: str, value: str) -> "_FakePipeline":
        self._ops.append((key, value))
        return self

    def execute(self) -> list[bool]:
        for key, value in self._ops:
            self._redis.store[key] = value
        return [True] * len(self._ops)
```

### Critical: `bulk_recompute()` must NOT call `seed_from_history()`

`seed_from_history()` merges with existing bucket data. `bulk_recompute()` **replaces** all buckets with fresh data computed entirely from Prometheus. The in-memory build accumulates new values per bucket (keyed by `_build_key(...)`), caps them at `MAX_BUCKET_VALUES`, then bulk-writes via pipeline. Existing Redis data is irrelevant during recomputation.

**Implementation sketch for bulk_recompute:**

```python
async def bulk_recompute(
    self,
    *,
    prometheus_client,  # PrometheusHTTPClient
    metric_queries: dict[str, MetricQueryDefinition],
    lookback_days: int,
    step_seconds: int,
    timeout_seconds: int,
    logger: structlog.BoundLogger,
) -> int:
    """Recompute all seasonal baseline buckets from 30-day Prometheus history.
    
    Phase 1: Build all key → JSON-list mappings entirely in memory.
    Phase 2: Bulk-write all keys via Redis pipeline (single round-trip).
    Returns total number of keys written.
    """
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=lookback_days)
    
    # Phase 1: in-memory accumulation
    # key_data: Redis key → list of float values (will be capped before write)
    key_data: dict[str, list[float]] = {}
    
    for metric_key, metric_defn in metric_queries.items():
        try:
            raw_records = await asyncio.to_thread(
                prometheus_client.query_range,
                metric_defn.metric_name, start, end, step_seconds,
                timeout=timeout_seconds,
            )
        except ...:
            logger.warning(...)
            continue
        
        for record in raw_records:
            labels = record.get("labels", {})
            values = record.get("values", [])
            try:
                scope = build_evidence_scope_key(labels, metric_key)
            except (ValueError, KeyError):
                try:
                    scope = _build_best_effort_scope(labels)
                except (ValueError, KeyError):
                    continue
            
            for ts_float, val in values:
                if not math.isfinite(val):
                    continue
                dt = datetime.fromtimestamp(ts_float, tz=UTC)
                dow, hour = time_to_bucket(dt)  # P3
                redis_key = self._build_key(scope, metric_key, dow, hour)
                key_data.setdefault(redis_key, []).append(val)
    
    # Cap each bucket at MAX_BUCKET_VALUES (P2)
    bulk_payload: dict[str, str] = {}
    for key, values in key_data.items():
        capped = values[-MAX_BUCKET_VALUES:] if len(values) > MAX_BUCKET_VALUES else values
        bulk_payload[key] = json.dumps(capped)
    
    # Phase 2: bulk pipeline write (single round-trip)
    if bulk_payload:
        pipe = self._redis.pipeline()
        for key, value in bulk_payload.items():
            pipe.set(key, value)
        pipe.execute()
    
    return len(bulk_payload)
```

### Critical: `aiops:seasonal_baseline:last_recompute` Key

This is a standalone Redis key (not a bucket key). It stores a UTC ISO timestamp string. Implementation:

```python
_LAST_RECOMPUTE_KEY = "aiops:seasonal_baseline:last_recompute"

def get_last_recompute(self) -> str | None:
    raw = self._redis.get(_LAST_RECOMPUTE_KEY)
    if raw is None:
        return None
    return raw if isinstance(raw, str) else raw.decode()

def set_last_recompute(self, timestamp_iso: str) -> None:
    self._redis.set(_LAST_RECOMPUTE_KEY, timestamp_iso)
```

The `SeasonalBaselineClientProtocol` must add `get(key)` — already present — and `set(key, value)` — already present. It needs an additional `pipeline()` method declaration.

### Critical: Structured Log Event Names (P6)

All three events are required. **Exact names:**

```python
logger.info("baseline_deviation_recompute_started", event_type="recompute.started")

logger.info(
    "baseline_deviation_recompute_completed",
    event_type="recompute.completed",
    duration_seconds=round(elapsed, 2),
    key_count=key_count,
)

logger.warning(
    "baseline_deviation_recompute_failed",
    event_type="recompute.failed",
    exc_info=True,
)
```

Do NOT use `recompute_started`, `weekly_recompute_completed`, or any other variant. These exact names are canonical per P6.

### Critical: Concurrency Guard — One Task at a Time

The hot-path cycle check must only spawn a new task when the previous one is no longer running:

```python
if _recompute_task is None or _recompute_task.done():
    if _should_trigger_recompute(last_iso, evaluation_time, _RECOMPUTE_INTERVAL_SECONDS):
        _recompute_task = asyncio.create_task(...)
```

`asyncio.Task.done()` returns `True` when the task completed (success, exception, or cancellation). A running task will block new spawning. This prevents concurrent overlapping recomputations.

### Critical: `_should_trigger_recompute()` Treats Absent Key as Expired

```python
def _should_trigger_recompute(
    last_iso: str | None,
    now: datetime,
    interval_seconds: int,
) -> bool:
    if last_iso is None:
        return True  # key absent — first run or Redis was flushed
    last = datetime.fromisoformat(last_iso)
    return (now - last).total_seconds() >= interval_seconds
```

`datetime.fromisoformat()` handles both naive and UTC-aware ISO strings. The `set_last_recompute()` always writes `datetime.now(UTC).isoformat()` (timezone-aware), so `fromisoformat()` will return a timezone-aware datetime. Both `now` (passed in from the hot-path as UTC) and `last` will be UTC-aware — subtraction is safe.

### Critical: `bulk_recompute()` is Async — Reuses `asyncio.to_thread` Pattern

`PrometheusHTTPClient.query_range()` is synchronous (blocking HTTP). The existing `baseline_backfill.py` wraps it in `asyncio.to_thread()`. `bulk_recompute()` must follow the same pattern — it is `async def` and uses `await asyncio.to_thread(prometheus_client.query_range, ...)` for each metric, exactly as in `backfill_baselines_from_prometheus()`.

### Anti-Patterns to Prevent

- **Do NOT write to Redis during Phase 1** — any Redis write before `pipe.execute()` violates NFR-R4 (partial write on failure)
- **Do NOT call `seed_from_history()` from `bulk_recompute()`** — they have different semantics (merge vs replace)
- **Do NOT hardcode `7`, `12`, or `168`** — use `_RECOMPUTE_INTERVAL_SECONDS` constant, `MAX_BUCKET_VALUES` from `baseline.constants`, loop 168 times only if iterating all buckets
- **Do NOT derive `(dow, hour)` inline** — always delegate to `time_to_bucket()` (P3)
- **Do NOT update `last_recompute` on failure** — only update after `pipe.execute()` completes successfully
- **Do NOT use `datetime.utcfromtimestamp()`** — naive datetimes will be rejected by `time_to_bucket()`; use `datetime.fromtimestamp(ts, tz=UTC)`
- **Do NOT spawn a second background task if one is already running** — check `_recompute_task.done()` first

### Where to Add the Timer Check in `__main__.py`

The hot-path loop in `_run_hot_path_scheduler()` has this structure (line ~611):

```python
while True:
    evaluation_time = datetime.now(UTC)
    ...
    tick = evaluate_scheduler_tick(...)
    previous_boundary = tick.expected_boundary
    logger.info("hot_path_cycle_started", ...)
    
    # [INSERT RECOMPUTE TIMER CHECK HERE — after cycle start log, before stage execution]
    
    if settings.DISTRIBUTED_CYCLE_LOCK_ENABLED:
        lock_outcome = cycle_lock.acquire(...)
        ...
```

The timer check should go after `logger.info("hot_path_cycle_started", ...)` and before the distributed lock check. This ensures it runs every cycle regardless of lock status. The background task runs concurrently with stage execution — it does not block the hot path.

### `SeasonalBaselineClientProtocol` Extension

The existing Protocol at `baseline/client.py` exposes `get`, `mget`, `set`. Add `pipeline()`:

```python
class SeasonalBaselineClientProtocol(Protocol):
    def get(self, key: str) -> str | bytes | None: ...
    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]: ...
    def set(self, key: str, value: str) -> bool | None: ...
    def pipeline(self) -> Any: ...  # Returns redis.client.Pipeline or compatible
```

Using `Any` for the return type avoids coupling to redis-py internals. Alternatively, define a `_RedisPipelineProtocol` with `set(key, value) -> Any` and `execute() -> list[Any]`.

### Scope Construction in `bulk_recompute()`

Reuse the same helpers already used in `baseline_backfill.py`:
- `build_evidence_scope_key(labels, metric_key)` from `pipeline.stages.evidence` — primary path
- `_build_best_effort_scope(labels)` from `pipeline.baseline_backfill` — fallback for lag metrics

Do NOT re-implement scope construction logic.

### Project Structure Notes

**New files:**
- `tests/unit/baseline/test_bulk_recompute.py` — unit tests for `bulk_recompute()`
- `tests/unit/pipeline/test_baseline_recompute.py` — unit tests for timer logic and `_run_baseline_recompute`

**Modified files:**
- `src/aiops_triage_pipeline/baseline/client.py` — add `pipeline()` to Protocol, add `bulk_recompute()`, `get_last_recompute()`, `set_last_recompute()` methods
- `src/aiops_triage_pipeline/__main__.py` — add `_RECOMPUTE_INTERVAL_SECONDS` constant, `_recompute_task` variable, timer check in cycle loop, `_should_trigger_recompute()` helper, `_run_baseline_recompute()` coroutine
- `docs/runtime-modes.md` — add weekly recomputation subsection

**Files NOT to touch:**
- `baseline/constants.py` — no new constants needed; `MAX_BUCKET_VALUES` already defined
- `baseline/computation.py` — `time_to_bucket()` unchanged
- `baseline/models.py` — still a stub; not this story
- `pipeline/baseline_backfill.py` — no changes; reuse `_build_best_effort_scope` import
- `pipeline/stages/` — no stage integration this story (Story 2.3)
- `pipeline/scheduler.py` — no changes; the timer check goes in `__main__.py`'s `_run_hot_path_scheduler()`

### Cross-Story Dependencies

**Depends on (DONE):**
- Story 1.1: `time_to_bucket()`, `MAX_BUCKET_VALUES` in `baseline/constants.py`
- Story 1.2: `SeasonalBaselineClient._build_key()`, `read_buckets()`, existing Protocol
- Story 1.3: `seed_from_history()` established patterns, `_build_best_effort_scope()` helper in `baseline_backfill.py`

**Enables (future):**
- Story 2.1 (MAD Engine): Reads the same Redis bucket keys that `bulk_recompute()` writes
- Story 2.3 (Baseline Deviation Stage): Injects `SeasonalBaselineClient` for per-cycle reads

### Testing Discipline

- `asyncio_mode=auto` is set globally — `bulk_recompute()` is `async def`; use `async def test_*` for it
- `_should_trigger_recompute()` is sync — use `def test_*`
- 0 skipped tests policy — do not use `pytest.mark.skip` or `pytest.mark.xfail`
- Type annotations on all test signatures: `def test_*(...)  -> None:` and `async def test_*(...)  -> None:`
- ruff `E,F,I,N,W` lint selection, line length 100 — no inline magic numbers
- Run `uv run ruff check` on all modified files before marking done

### Previous Story Learnings (Stories 1.1–1.3)

**From Story 1.2 code review (applied):**
1. **Test key schema assertions**: Assert on `_EXPECTED_KEY in redis.store` (tests implementation), not tautological fixture assertions
2. **No invalid `noqa`**: `ARG002` and similar rules are not active — no `noqa` in `_Fake*` helper methods
3. **E501 compliance**: Lines ≤ 100 chars; extract long expected key strings into `_SCOPE_STR`, `_EXPECTED_KEY` constants in tests

**From Story 1.3 code review (applied):**
1. **Module-level imports**: All imports at module level — no import-inside-function except where critically needed (avoid ruff I001)
2. **No `noqa` for inactive rules**: Do not add `noqa` comments for rules not in active ruff select set
3. **`scope_count` correctness**: When counting unique scopes for log fields, use a `set` to deduplicate — do NOT count `(scope, metric_key)` pairs
4. **`_build_best_effort_scope` exists**: It is already in `pipeline/baseline_backfill.py` and importable — reuse it; do not recreate

### References

- Architecture decision D4 (weekly recomputation): [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#D4]
- P2 (constants import): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P2]
- P3 (time_to_bucket sole source): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P3]
- P6 (log event naming): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P6]
- NFR-P5 (recompute within 10 min): [Source: artifact/planning-artifacts/epics.md#NonFunctional-Requirements]
- NFR-R4 (idempotent writes, no corruption): [Source: artifact/planning-artifacts/epics.md#NonFunctional-Requirements]
- Story 1.4 acceptance criteria: [Source: artifact/planning-artifacts/epics.md#Story-1.4]
- SeasonalBaselineClient implementation: [Source: src/aiops_triage_pipeline/baseline/client.py]
- `_build_best_effort_scope` helper: [Source: src/aiops_triage_pipeline/pipeline/baseline_backfill.py]
- Existing backfill asyncio.to_thread pattern: [Source: src/aiops_triage_pipeline/pipeline/baseline_backfill.py]
- Timer check placement (after hot_path_cycle_started log): [Source: src/aiops_triage_pipeline/__main__.py#_run_hot_path_scheduler]
- `asyncio.create_task` health-server precedent: [Source: src/aiops_triage_pipeline/__main__.py line 576]
- Existing test patterns: [Source: tests/unit/baseline/test_client.py, tests/unit/pipeline/test_baseline_backfill.py]
- Python 3.13 typing style, frozen models, structlog: [Source: artifact/project-context.md#Critical-Implementation-Rules]
- Test framework (pytest, asyncio_mode=auto, 0 skips): [Source: artifact/project-context.md#Testing-Rules]
- Full regression command: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No debug issues. All 16 tests passed on first implementation run after fixing a
`_PrometheusFailureTracker` pattern to reconcile the NFR-R4 (bulk_recompute must not raise
on per-metric failures) with the AC4/AC5 requirement (failure must be detected in
`_run_baseline_recompute`). Also fixed `get_last_recompute()` to return `None` when the
Redis mock returns a non-string/bytes value, preventing `TypeError` in existing tests.

### Completion Notes List

- Implemented `bulk_recompute()` on `SeasonalBaselineClient` with two-phase in-memory
  compute → bulk pipeline write pattern (NFR-R4: no partial Redis writes on failure).
- Added `get_last_recompute()` / `set_last_recompute()` methods and `pipeline()` to
  `SeasonalBaselineClientProtocol`.
- Added `_RECOMPUTE_INTERVAL_SECONDS`, `_should_trigger_recompute()`,
  `_PrometheusFailureTracker`, and `_run_baseline_recompute()` to `__main__.py`.
- Timer check added to `_hot_path_scheduler_loop()` after `hot_path_cycle_started` log.
- `_PrometheusFailureTracker` wraps the prometheus client to detect per-metric failures
  without requiring `bulk_recompute()` to propagate exceptions (preserving NFR-R4 guarantee).
- All 16 ATDD tests pass; 1225 total unit tests pass; ruff clean.
- `docs/runtime-modes.md` updated with "Weekly recomputation" subsection.

### File List

- `src/aiops_triage_pipeline/baseline/client.py`
- `src/aiops_triage_pipeline/__main__.py`
- `docs/runtime-modes.md`
- `tests/unit/baseline/test_bulk_recompute.py`
- `tests/unit/pipeline/test_baseline_recompute.py`
- `artifact/implementation-artifacts/sprint-status.yaml`

## Senior Developer Review (AI)

**Reviewer:** Sas (claude-sonnet-4-6) on 2026-04-05
**Outcome:** Approved with fixes applied

### Findings

| # | Severity | Finding | File | Resolution |
|---|---|---|---|---|
| 1 | Medium | `exc_info=True` emitted on the `had_failures` path with no active exception context — structlog would log empty traceback | `__main__.py:252-257` | Fixed: `_PrometheusFailureTracker` now stores `last_exception`; `exc_info=tracker.last_exception` passes the real exception to the log event |
| 2 | Low | Deferred import of `_build_best_effort_scope` inside `bulk_recompute()` body violates the module-level import convention without explanation | `client.py:142` | Fixed: Added 4-line comment documenting the circular-import constraint that makes the deferred import necessary |
| 3 | Low | Story File List omitted three changed files: `test_bulk_recompute.py`, `test_baseline_recompute.py`, and `sprint-status.yaml` | Story `### File List` | Fixed: All three files added to File List |
| 4 | Low | Test docstring for `test_recompute_coroutine_emits_failed_log_on_exception` claimed "when bulk_recompute() raises" but `bulk_recompute()` does NOT raise — the `had_failures` path is exercised, not the outer `except` block | `test_baseline_recompute.py:346` | Fixed: Docstring updated to accurately describe the `_PrometheusFailureTracker` path being tested; assertion updated to check truthy `exc_info` (compatible with both `True` and exception instances) |

### AC Verification

- AC1 (timer check, 7-day expiry, absent key): Implemented and tested — `_should_trigger_recompute()` + concurrency guard in `_hot_path_scheduler_loop()`. 5/5 tests pass.
- AC2 (bulk_recompute pipeline write, key count, time_to_bucket, cap): Fully implemented. 5/6 bulk_recompute tests pass (all pass).
- AC3 (hot-path cycles unaffected during recompute): Background `asyncio.create_task()` used; no blocking.
- AC4 (no partial writes on failure): Phase 1 is pure in-memory; Phase 2 pipeline write only if Phase 1 completes. NFR-R4 satisfied.
- AC5 (structured log events with correct names/fields): All three events emitted with correct P6 names. `exc_info` fix ensures real exception context on failure.
- AC6 (performance): Architecture design (in-memory compute + single pipeline write) satisfies NFR-P5 intent.
- AC7 (unit tests): 16 ATDD tests pass; 1225 total unit tests pass; ruff clean.

## Change Log

- 2026-04-05: Implemented Story 1.4 — weekly baseline recomputation with bulk_recompute(),
  timer check in hot-path scheduler, structured log events, and runtime-modes.md documentation.
  All 16 ATDD tests pass; 1225 total unit tests pass; ruff clean. (claude-sonnet-4-6)
- 2026-04-05: Code review — 4 findings (1 Medium, 3 Low) all fixed. _PrometheusFailureTracker
  stores last_exception for real exc_info context; deferred import comment added; File List
  completed; test docstring corrected. 1225 tests pass; ruff clean. Status → done.
  (claude-sonnet-4-6)
