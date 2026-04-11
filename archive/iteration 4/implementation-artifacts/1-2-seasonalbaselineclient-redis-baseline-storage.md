# Story 1.2: SeasonalBaselineClient - Redis Baseline Storage

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform engineer,
I want seasonal baselines stored in Redis with per-scope, per-metric, per-time-bucket granularity,
so that the detection stage can read historical baselines for comparison and baselines stay bounded in size.

## Acceptance Criteria

1. **Given** a `SeasonalBaselineClient` instance with a Redis connection
   **When** `read_buckets(scope, metric_key, dow, hour)` is called
   **Then** it reads key `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` from Redis
   **And** returns a list of float values deserialized from JSON
   **And** the scope portion of the key is built by joining the tuple elements with `|` (consistent with existing key helpers in `pipeline/baseline_store.py`)

2. **Given** a `SeasonalBaselineClient` instance
   **When** `update_bucket(scope, metric_key, dow, hour, value)` is called
   **Then** it appends the new float value to the existing list at the corresponding Redis key
   **And** if the list length exceeds `MAX_BUCKET_VALUES` (12), the oldest value (index 0) is dropped
   **And** the updated list is written back as JSON

3. **Given** a scope with 9 metrics and a single time bucket
   **When** `read_buckets` is called for all metrics using a batch-read method
   **Then** it uses Redis `mget` to batch the reads in a single round-trip (NFR-P2)
   **And** completes within 50ms per scope batch of up to 500 scopes × 9 metrics = 4,500 keys

4. **Given** a Redis key that does not yet exist
   **When** `read_buckets` is called for that key
   **Then** it returns an empty list (no error, no exception)

5. **Given** Redis is unavailable
   **When** any `SeasonalBaselineClient` method is called
   **Then** it raises the Redis exception (or wraps it) for the caller to handle
   **And** does NOT silently swallow errors — fail-open behavior is the stage's responsibility (NFR-R2)

6. **Given** unit tests in `tests/unit/baseline/test_client.py`
   **When** tests are executed
   **Then** they use a mock/fake Redis client with no real Redis dependency
   **And** all read, write, mget batching, and cap enforcement behaviors are verified
   **And** `docs/data-models.md` is updated to replace the "forthcoming (Story 1.2)" placeholder with the confirmed key schema

## Tasks / Subtasks

- [x] Task 1: Create `baseline/client.py` with `SeasonalBaselineClient` class (AC: 1, 2, 3, 4, 5)
  - [x] 1.1 Create `src/aiops_triage_pipeline/baseline/client.py`
  - [x] 1.2 Define `SeasonalBaselineClientProtocol` (structural protocol for the Redis client dependency) mirroring the pattern in `pipeline/baseline_store.py`
  - [x] 1.3 Implement `_build_key(scope, metric_key, dow, hour) -> str` private helper using `aiops:seasonal_baseline:{scope_str}:{metric_key}:{dow}:{hour}` where `scope_str = "|".join(scope)`
  - [x] 1.4 Implement `read_buckets(scope, metric_key, dow, hour) -> list[float]` — single key read returning deserialized JSON float list; empty list if key missing
  - [x] 1.5 Implement `read_buckets_batch(scope, metric_keys, dow, hour) -> dict[str, list[float]]` — batched mget for all metrics in a single scope/bucket, returns mapping of metric_key → float list
  - [x] 1.6 Implement `update_bucket(scope, metric_key, dow, hour, value) -> None` — append + cap at MAX_BUCKET_VALUES, then SET back to Redis
  - [x] 1.7 Confirm class is injected (constructor takes Redis client), not constructed with global state

- [x] Task 2: Write unit tests for `SeasonalBaselineClient` (AC: 6)
  - [x] 2.1 Create `tests/unit/baseline/test_client.py`
  - [x] 2.2 Define `_FakeRedis` (same pattern as in `tests/unit/pipeline/test_baseline_store.py` — in-memory dict with `get`, `mget`, `set` methods)
  - [x] 2.3 Test `read_buckets` returns correct float list for an existing key
  - [x] 2.4 Test `read_buckets` returns empty list for a missing key
  - [x] 2.5 Test `update_bucket` appends value to existing list
  - [x] 2.6 Test `update_bucket` enforces `MAX_BUCKET_VALUES` cap — after inserting 13 values, list length is 12 and oldest is dropped
  - [x] 2.7 Test `read_buckets_batch` issues a single `mget` call for multiple metrics
  - [x] 2.8 Test `read_buckets_batch` returns empty lists for missing keys
  - [x] 2.9 Test that Redis exceptions propagate (not swallowed)

- [x] Task 3: Update `docs/data-models.md` (AC: 6)
  - [x] 3.1 Replace the "forthcoming (Story 1.2)" note with the confirmed seasonal baseline key schema and JSON value format (float list, max 12 items)
  - [x] 3.2 Confirm the Redis key schema entry matches: `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` where scope = `|`-joined tuple

- [x] Task 4: Run full regression suite
  - [x] 4.1 Run `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] 4.2 Confirm 0 skipped tests and no regressions in existing tests

## Dev Notes

### What This Story Delivers

This story creates `baseline/client.py` — the dedicated Redis I/O boundary for seasonal baselines (D3 from architecture). It implements `SeasonalBaselineClient` with:
- `read_buckets()` — single-key read
- `read_buckets_batch()` — batched `mget` for a single scope's metrics (NFR-P2 performance gate)
- `update_bucket()` — append + cap enforcement (FR5)

**NOT in this story:** `seed_from_history()` and `bulk_recompute()` are Story 1.3 and 1.4 respectively. Do not implement them here.

**NOT in this story:** Pydantic models (`BaselineDeviationContext`, `BaselineDeviationStageOutput`) in `baseline/models.py` belong to Story 2.2. Keep `models.py` as a docstring stub only.

### Critical: Redis Key Schema (D1)

```
aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}
```

- `{scope}` = `"|".join(scope_tuple)` — e.g., `("prod", "kafka-prod-east", "orders.completed")` → `prod|kafka-prod-east|orders.completed`
- `{metric_key}` = metric name string, e.g., `"topic_messages_in_per_sec"`
- `{dow}` = integer 0–6 (from `time_to_bucket()`, `datetime.weekday()` convention: Mon=0, Sun=6)
- `{hour}` = integer 0–23
- Value format: JSON-serialized `list[float]`, max 12 items

**Reference:** [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#D1]

### Critical: Scope Tuple Representation (P1)

Scope is always `tuple[str, ...]` — no joined strings, no typed model. Use `"|".join(scope)` only when building Redis keys.

```python
# Correct
scope: tuple[str, ...] = ("prod", "kafka-prod-east", "orders.completed")
# Scope key in Redis key: "prod|kafka-prod-east|orders.completed"
```

**Reference:** [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P1]

### Critical: Constants Import (P2)

Import `MAX_BUCKET_VALUES` from `baseline/constants.py`. Never hardcode `12`.

```python
from aiops_triage_pipeline.baseline.constants import MAX_BUCKET_VALUES
```

**Reference:** [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P2]

### Existing Pattern: Redis Protocol in baseline_store.py

The existing `pipeline/baseline_store.py` defines `BaselineStoreClientProtocol` for structural typing of a Redis-like client. Mirror this pattern in `baseline/client.py`:

```python
from collections.abc import Sequence
from typing import Protocol


class SeasonalBaselineClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by SeasonalBaselineClient."""

    def get(self, key: str) -> str | bytes | None: ...
    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]: ...
    def set(self, key: str, value: str) -> bool | None: ...
```

The `SeasonalBaselineClient` class takes an instance of this protocol in its constructor.

**Reference:** [Source: src/aiops_triage_pipeline/pipeline/baseline_store.py#BaselineStoreClientProtocol]

### Existing Pattern: _FakeRedis in test_baseline_store.py

The existing `tests/unit/pipeline/test_baseline_store.py` defines `_FakeRedis` with an in-memory dict and tracks `mget_calls`. Use the same pattern for `test_client.py`:

```python
class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.mget_calls: list[tuple[str, ...]] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        self.mget_calls.append(tuple(keys))
        return [self.store.get(key) for key in keys]

    def set(self, key: str, value: str) -> bool:
        self.store[key] = value
        return True
```

**Reference:** [Source: tests/unit/pipeline/test_baseline_store.py#_FakeRedis]

### SeasonalBaselineClient Implementation Sketch

```python
"""SeasonalBaselineClient — Redis I/O boundary for seasonal baseline data (D3)."""

import json
from collections.abc import Sequence
from typing import Protocol

from aiops_triage_pipeline.baseline.constants import MAX_BUCKET_VALUES

BaselineScope = tuple[str, ...]


class _RedisProtocol(Protocol):
    def get(self, key: str) -> str | bytes | None: ...
    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]: ...
    def set(self, key: str, value: str) -> bool | None: ...


class SeasonalBaselineClient:
    """Encapsulates all Redis I/O for seasonal baseline storage.

    Key schema: aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}
    Value format: JSON float list, max MAX_BUCKET_VALUES items.
    """

    def __init__(self, redis_client: _RedisProtocol) -> None:
        self._redis = redis_client

    def _build_key(
        self,
        scope: BaselineScope,
        metric_key: str,
        dow: int,
        hour: int,
    ) -> str:
        scope_str = "|".join(scope)
        return f"aiops:seasonal_baseline:{scope_str}:{metric_key}:{dow}:{hour}"

    def read_buckets(
        self,
        scope: BaselineScope,
        metric_key: str,
        dow: int,
        hour: int,
    ) -> list[float]:
        """Read historical float values for one bucket. Returns [] if key missing."""
        key = self._build_key(scope, metric_key, dow, hour)
        raw = self._redis.get(key)
        if raw is None:
            return []
        return json.loads(raw if isinstance(raw, str) else raw.decode())

    def read_buckets_batch(
        self,
        scope: BaselineScope,
        metric_keys: Sequence[str],
        dow: int,
        hour: int,
    ) -> dict[str, list[float]]:
        """Batch-read all metric buckets for one (scope, dow, hour) in a single mget."""
        keys = [self._build_key(scope, mk, dow, hour) for mk in metric_keys]
        raws = self._redis.mget(keys)
        result: dict[str, list[float]] = {}
        for metric_key, raw in zip(metric_keys, raws, strict=True):
            if raw is None:
                result[metric_key] = []
            else:
                result[metric_key] = json.loads(
                    raw if isinstance(raw, str) else raw.decode()
                )
        return result

    def update_bucket(
        self,
        scope: BaselineScope,
        metric_key: str,
        dow: int,
        hour: int,
        value: float,
    ) -> None:
        """Append value to bucket, enforcing MAX_BUCKET_VALUES cap (oldest dropped)."""
        existing = self.read_buckets(scope, metric_key, dow, hour)
        existing.append(value)
        if len(existing) > MAX_BUCKET_VALUES:
            existing = existing[-MAX_BUCKET_VALUES:]
        key = self._build_key(scope, metric_key, dow, hour)
        self._redis.set(key, json.dumps(existing))
```

**Important:** The sketch above is a starting point. Follow all project conventions: type annotations use built-in generics (`list[float]`, `dict[str, list[float]]`), no `typing.List`/`typing.Dict`. Module docstring on first line.

### Key Distinction: baseline/client.py vs pipeline/baseline_store.py

**Do NOT confuse these two:**

| File | Purpose | Redis keyspace |
|---|---|---|
| `pipeline/baseline_store.py` | Existing peak-history baseline cache (peak median values per scope/metric) | `aiops:baseline:{source}:{scope_key}:{metric_key}` |
| `baseline/client.py` (NEW this story) | Seasonal time-bucket baseline storage (168 buckets per scope/metric) | `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` |

These are **completely separate** Redis keyspaces with different value formats. Do NOT modify `pipeline/baseline_store.py`.

**Reference:** [Source: Story 1.1 Dev Notes#Important distinction]

### Project Structure Notes

- New file: `src/aiops_triage_pipeline/baseline/client.py` — follows baseline package layout from `artifact/planning-artifacts/architecture/project-structure-boundaries.md`
- New test file: `tests/unit/baseline/test_client.py` — mirrors source package structure, no integration/Docker required (unit tests use fake Redis)
- `baseline/__init__.py` stays empty — do not add exports
- No `pyproject.toml` changes needed — `json` is stdlib, no new dependencies

### Code Style Rules (from project-context.md)

- Python 3.13 typing: `X | None`, `list[float]`, `dict[str, list[float]]`, `tuple[str, ...]`
- Frozen models: not applicable here (SeasonalBaselineClient is a stateful service class, not a contract model)
- Line length: 100 characters (ruff)
- Ruff lint: `E,F,I,N,W` — avoid `noqa` unless necessary
- Module docstring pattern: one-line description on first line (see `pipeline/baseline_store.py`)
- Tests: `def test_*(...)  -> None:` signatures with type annotations

### Testing Rules

- `asyncio_mode=auto` is set globally — but `SeasonalBaselineClient` methods are **sync** (Redis client is sync). Use plain `def` tests, no `async def`.
- 0 skipped tests policy — do not use `pytest.mark.skip` or `pytest.mark.xfail`
- All tests must pass: `uv run pytest tests/unit/baseline/test_client.py -q`

### Previous Story Learnings (Story 1.1)

From the Story 1.1 code review (applied lessons):

1. **Naive datetime guard:** Story 1.1 added a `ValueError` guard for naive datetimes in `time_to_bucket()`. For this story, `dow` and `hour` are already integers passed in — callers are responsible for deriving them via `time_to_bucket()`. No datetime handling needed in client.
2. **Integer constant type assertions in tests:** Integer constants should be checked with `isinstance(..., int)` in addition to value equality. Apply same rigor to any integer checks in test_client.py.
3. **Import placement:** Keep all imports at module level (not inside functions). ruff rule I001.
4. **noqa:** Do not add `noqa` comments for rules not in the active ruff select list (`E,F,I,N,W`).
5. **`xfail` markers:** Do NOT use `@pytest.mark.xfail` in new tests — tests must pass from the first run.

### Git Context

Recent commits:
- `be5972d bmad(epic-1/1-1-baseline-constants-and-time-bucket-derivation): complete workflow and quality gates` — Story 1.1 done
- `4f84e26 feat(backfill): seed peak history and Redis baseline cache from Prometheus on startup` — existing backfill that Story 1.3 will extend

The `pipeline/baseline_store.py` and `pipeline/baseline_backfill.py` were part of the backfill commit and are the existing peak-history machinery. This story creates the new seasonal baseline client alongside them.

### Cross-Story Dependencies

**Depends on:** Story 1.1 (constants.py — `MAX_BUCKET_VALUES`) — DONE.

**Blocks:**
- Story 1.3: `seed_from_history()` method on `SeasonalBaselineClient` (added to `client.py`)
- Story 1.4: `bulk_recompute()` method on `SeasonalBaselineClient` (added to `client.py`)
- Story 2.3: Baseline deviation stage injects `SeasonalBaselineClient` as a dependency

**Do NOT implement `seed_from_history()` or `bulk_recompute()` in this story** — they belong in Stories 1.3 and 1.4 respectively. Only implement `read_buckets`, `read_buckets_batch`, and `update_bucket`.

### References

- Redis key schema (D1): [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#D1]
- SeasonalBaselineClient interface (D3): [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#D3]
- Scope tuple pattern (P1): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P1]
- Constants rule (P2): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P2]
- Project structure boundaries: [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#New-Files-Directories]
- Existing Redis protocol pattern: [Source: src/aiops_triage_pipeline/pipeline/baseline_store.py#BaselineStoreClientProtocol]
- Existing fake Redis test pattern: [Source: tests/unit/pipeline/test_baseline_store.py#_FakeRedis]
- Python 3.13 typing style, frozen models, structlog: [Source: artifact/project-context.md#Critical-Implementation-Rules]
- Test framework (pytest, asyncio_mode=auto, 0 skips): [Source: artifact/project-context.md#Testing-Rules]
- Full regression command: [Source: artifact/project-context.md#Testing-Rules]
- FR1 (168 time buckets), FR5 (cap at 12): [Source: artifact/planning-artifacts/epics.md#Story-1.2]
- NFR-P2 (mget within 50ms per scope batch): [Source: artifact/planning-artifacts/epics.md#NonFunctional-Requirements]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

_No debug issues encountered._

### Completion Notes List

- Implemented `SeasonalBaselineClient` in `src/aiops_triage_pipeline/baseline/client.py` with `SeasonalBaselineClientProtocol`, `_build_key`, `read_buckets`, `read_buckets_batch`, and `update_bucket`.
- Key schema: `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` where scope elements are `|`-joined.
- `MAX_BUCKET_VALUES` imported from `baseline/constants.py`; cap enforced by slicing to last 12 values.
- `read_buckets_batch` issues a single `mget` call for all metric keys in a given (scope, dow, hour) bucket.
- Redis exceptions propagate unhandled per AC5/NFR-R2.
- `docs/data-models.md` updated: "forthcoming (Story 1.2)" placeholder replaced with confirmed key schema and value format.
- All 12 ATDD tests pass; full regression suite: 1296 passed, 0 skipped, 0 failures.

### File List

- `src/aiops_triage_pipeline/baseline/client.py` (new)
- `tests/unit/baseline/test_client.py` (new)
- `docs/data-models.md` (modified)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified — story status set to review)

### Senior Developer Review (AI)

**Reviewer:** bmad-bmm-code-review | **Date:** 2026-04-05 | **Outcome:** Changes Applied → done

**Findings Fixed (6 total — 0 Critical, 1 High, 3 Medium, 2 Low):**

- **[HIGH] File List incomplete** — `tests/unit/baseline/test_client.py` and `sprint-status.yaml` were missing from Dev Agent Record File List. Fixed: both entries added.
- **[MEDIUM] Ruff E501 violations** — 4 lines over 100-char limit in `test_client.py` (lines 71, 91, 148, 191). Fixed: `_EXPECTED_KEY` refactored to use `_SCOPE_STR` interpolation; docstrings shortened.
- **[MEDIUM] Invalid `noqa: ARG002` comments** — `ARG002` is not in active ruff select set (`E,F,I,N,W`); violates Story 1.1 lesson carried forward in Dev Notes. Fixed: all three `# noqa: ARG002` comments removed from `_FailingRedis`.
- **[MEDIUM] Duplicate key schema in `docs/data-models.md`** — Two bullet points described the same Redis key schema (lines 71 and 73), the first being incomplete. Fixed: merged into one complete entry.
- **[MEDIUM] Tautological assertion in `test_read_buckets_key_schema`** — `assert "prod|kafka-prod-east|orders.completed" in _EXPECTED_KEY` tested the fixture constant, not the implementation. Fixed: replaced with `assert _EXPECTED_KEY in redis.store` and `assert _SCOPE_STR in _EXPECTED_KEY` using the new `_SCOPE_STR` helper constant.
- **[LOW] Missing `isinstance` checks for `_DOW` and `_HOUR`** — Per Story 1.1 lesson 2 (carried forward), integer constants need `isinstance(..., int)` assertions. Fixed: added module-level `assert isinstance(_DOW, int)` and `assert isinstance(_HOUR, int)`.

**Post-fix verification:** 12/12 `test_client.py` tests pass. 1189/1189 unit tests pass. `ruff check` clean on all modified files.

### Change Log

| Date | Change |
|---|---|
| 2026-04-05 | Implemented SeasonalBaselineClient with read_buckets, read_buckets_batch, update_bucket; updated data-models.md with confirmed key schema |
| 2026-04-05 | Code review: fixed 6 findings (File List gap, 4× E501, invalid noqa, duplicate docs entry, tautological assertion, missing isinstance checks) |
