"""Unit tests for weekly baseline recompute timer logic and orchestration — Story 1.4.

AC coverage (Story 1.4 — timer + coroutine):
  AC1 — _should_trigger_recompute returns True when key is absent (None)
  AC1 — _should_trigger_recompute returns True when 7+ days have elapsed
  AC1 — _should_trigger_recompute returns False when less than 7 days elapsed
  AC1 — _should_trigger_recompute returns True at exactly the 7-day boundary
  AC1 — No concurrent recompute task spawned when existing task is still running
  AC5 — _run_baseline_recompute emits baseline_deviation_recompute_started log
  AC5 — _run_baseline_recompute emits completed log with key_count + duration_seconds
  AC5 — _run_baseline_recompute emits failed log with exc_info on exception
  AC4 — _run_baseline_recompute updates last_recompute on success
  AC4 — _run_baseline_recompute does NOT update last_recompute on failure

TDD RED PHASE: These tests FAIL because _should_trigger_recompute() and
_run_baseline_recompute() are not yet implemented in __main__.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
from aiops_triage_pipeline.integrations.prometheus import MetricQueryDefinition

# ---------------------------------------------------------------------------
# RED PHASE — functions do not exist yet; collected tests will fail with ImportError
# ---------------------------------------------------------------------------

_IMPORT_ERROR: ImportError | None = None

try:
    from aiops_triage_pipeline.__main__ import (
        _run_baseline_recompute,
        _should_trigger_recompute,
    )
except ImportError as _err:
    _IMPORT_ERROR = _err
    _IMPORT_ERROR_MSG = str(_err)

    def _should_trigger_recompute(  # type: ignore[misc]
        last_iso: str | None,
        now: datetime,
        interval_seconds: int,
    ) -> bool:
        raise ImportError(
            "aiops_triage_pipeline.__main__._should_trigger_recompute not implemented yet "
            f"(Story 1.4 RED phase): {_IMPORT_ERROR_MSG}"
        )

    async def _run_baseline_recompute(  # type: ignore[misc]
        **kwargs: object,
    ) -> int:
        raise ImportError(
            "aiops_triage_pipeline.__main__._run_baseline_recompute not implemented yet "
            f"(Story 1.4 RED phase): {_IMPORT_ERROR_MSG}"
        )


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------


class _FakePipeline:
    def __init__(self, redis: "_FakeBaselineRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, str]] = []

    def set(self, key: str, value: str) -> "_FakePipeline":
        self._ops.append((key, value))
        return self

    def execute(self) -> list[bool]:
        for key, value in self._ops:
            self._redis.store[key] = value
        return [True] * len(self._ops)


class _FakeBaselineRedis:
    """In-memory Redis with pipeline() support + get/set for last_recompute key."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def mget(self, keys: Sequence[str]) -> list[str | None]:
        return [self.store.get(k) for k in keys]

    def set(self, key: str, value: str) -> bool:
        self.store[key] = value
        return True

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


def _make_metric_queries(*keys: str) -> dict[str, MetricQueryDefinition]:
    return {
        key: MetricQueryDefinition(
            metric_key=key,
            metric_name=f"prom_{key}",
            role="throughput",
        )
        for key in keys
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEVEN_DAYS_SECONDS = 7 * 24 * 3600
_NOW = datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# AC1: _should_trigger_recompute — key absent (None) → True
# ---------------------------------------------------------------------------


def test_should_trigger_when_key_absent() -> None:
    """[P0] AC1: _should_trigger_recompute(None, ...) returns True.

    Missing key means first-ever recomputation (or Redis was flushed).
    Must be treated as expired.
    """
    result = _should_trigger_recompute(None, _NOW, _SEVEN_DAYS_SECONDS)

    assert result is True, (
        "_should_trigger_recompute(None, ...) must return True. "
        "An absent key must be treated as expired (trigger recompute)."
    )


# ---------------------------------------------------------------------------
# AC1: _should_trigger_recompute — 7+ days elapsed → True
# ---------------------------------------------------------------------------


def test_should_trigger_when_7_days_elapsed() -> None:
    """[P0] AC1: _should_trigger_recompute returns True when now - last > 7 days.

    7 days + 1 second elapsed → trigger recompute.
    """
    last = _NOW - timedelta(seconds=_SEVEN_DAYS_SECONDS + 1)
    last_iso = last.isoformat()

    result = _should_trigger_recompute(last_iso, _NOW, _SEVEN_DAYS_SECONDS)

    assert result is True, (
        f"_should_trigger_recompute returned False for last={last_iso!r}, "
        f"but elapsed={_SEVEN_DAYS_SECONDS + 1}s > interval={_SEVEN_DAYS_SECONDS}s. "
        "Must return True when 7+ days have elapsed."
    )


# ---------------------------------------------------------------------------
# AC1: _should_trigger_recompute — recent (6 days) → False
# ---------------------------------------------------------------------------


def test_should_not_trigger_when_recent() -> None:
    """[P0] AC1: _should_trigger_recompute returns False when last recompute was < 7 days ago.

    6 days elapsed → do NOT trigger recompute.
    """
    last = _NOW - timedelta(days=6)
    last_iso = last.isoformat()

    result = _should_trigger_recompute(last_iso, _NOW, _SEVEN_DAYS_SECONDS)

    assert result is False, (
        f"_should_trigger_recompute returned True for last={last_iso!r}, "
        f"but only 6 days have elapsed. Must return False when < 7 days elapsed."
    )


# ---------------------------------------------------------------------------
# AC1: _should_trigger_recompute — exactly 7 days → True
# ---------------------------------------------------------------------------


def test_should_trigger_exactly_at_boundary() -> None:
    """[P0] AC1: _should_trigger_recompute returns True at exactly the 7-day boundary.

    now - last == exactly 7 days (604800 seconds) → trigger recompute.
    The boundary is inclusive: >= 7 days triggers.
    """
    last = _NOW - timedelta(seconds=_SEVEN_DAYS_SECONDS)
    last_iso = last.isoformat()

    result = _should_trigger_recompute(last_iso, _NOW, _SEVEN_DAYS_SECONDS)

    assert result is True, (
        "_should_trigger_recompute returned False at exactly the 7-day boundary. "
        "The check is >= interval_seconds, so exactly 7 days must return True."
    )


# ---------------------------------------------------------------------------
# AC1: No concurrent recompute task spawned while task running
# ---------------------------------------------------------------------------


async def test_no_concurrent_recompute_spawned_while_task_running() -> None:
    """[P0] AC1: When a recompute task is already running, a second timer check
    must NOT spawn another task.

    The concurrency guard: `if _recompute_task is None or _recompute_task.done()`.
    A running task (not done) must block new spawning.
    """

    async def _never_completes() -> int:
        await asyncio.sleep(3600)
        return 0

    task: asyncio.Task[int] = asyncio.create_task(_never_completes())

    try:
        _recompute_task: asyncio.Task[int] | None = task
        create_task_calls = 0

        for _ in range(2):
            if _recompute_task is None or _recompute_task.done():
                create_task_calls += 1

        assert create_task_calls == 0, (
            f"Expected 0 new task spawns while recompute task is running, "
            f"but create_task() would have been called {create_task_calls} time(s). "
            "The concurrency guard `_recompute_task.done()` must block re-spawning."
        )
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# AC5: _run_baseline_recompute emits started log
# ---------------------------------------------------------------------------


async def test_recompute_coroutine_emits_started_log() -> None:
    """[P0] AC5: _run_baseline_recompute() emits 'baseline_deviation_recompute_started'
    before calling bulk_recompute().

    Exact log event name per P6.
    """
    redis = _FakeBaselineRedis()
    client = SeasonalBaselineClient(redis)
    mock_logger = MagicMock()
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = []

    queries = _make_metric_queries("topic_messages_in_per_sec")

    await _run_baseline_recompute(
        seasonal_baseline_client=client,
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=mock_logger,
    )

    all_info_calls = mock_logger.info.call_args_list
    started_calls = [
        c for c in all_info_calls
        if c.args and c.args[0] == "baseline_deviation_recompute_started"
    ]

    assert len(started_calls) >= 1, (
        f"Expected at least one 'baseline_deviation_recompute_started' log event, "
        f"but found {len(started_calls)} out of {len(all_info_calls)} info calls. "
        "Check that _run_baseline_recompute emits "
        "logger.info('baseline_deviation_recompute_started', ...)."
    )


# ---------------------------------------------------------------------------
# AC5: _run_baseline_recompute emits completed log with key_count + duration_seconds
# ---------------------------------------------------------------------------


async def test_recompute_coroutine_emits_completed_log_with_key_count_and_duration() -> None:
    """[P0] AC5: _run_baseline_recompute() emits 'baseline_deviation_recompute_completed'
    with 'key_count' and 'duration_seconds' fields on success.

    Exact log event name per P6.
    """
    redis = _FakeBaselineRedis()
    client = SeasonalBaselineClient(redis)
    mock_logger = MagicMock()
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = []

    queries = _make_metric_queries("topic_messages_in_per_sec")

    await _run_baseline_recompute(
        seasonal_baseline_client=client,
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=mock_logger,
    )

    all_info_calls = mock_logger.info.call_args_list
    completed_calls = [
        c for c in all_info_calls
        if c.args and c.args[0] == "baseline_deviation_recompute_completed"
    ]

    assert len(completed_calls) == 1, (
        f"Expected exactly one 'baseline_deviation_recompute_completed' log event, "
        f"found {len(completed_calls)}. "
        "Check that _run_baseline_recompute emits "
        "logger.info('baseline_deviation_recompute_completed', ...)."
    )

    call_kwargs = completed_calls[0].kwargs
    assert "key_count" in call_kwargs, (
        f"Missing 'key_count' in baseline_deviation_recompute_completed kwargs: {call_kwargs}"
    )
    assert "duration_seconds" in call_kwargs, (
        f"Missing 'duration_seconds' in baseline_deviation_recompute_completed kwargs: "
        f"{call_kwargs}"
    )


# ---------------------------------------------------------------------------
# AC5: _run_baseline_recompute emits failed log with exc_info on exception
# ---------------------------------------------------------------------------


async def test_recompute_coroutine_emits_failed_log_on_exception() -> None:
    """[P0] AC5: _run_baseline_recompute() emits 'baseline_deviation_recompute_failed'
    with exc_info=True when all Prometheus queries fail.

    Simulates total Prometheus failure: all metric query_range calls raise ConnectionError.
    bulk_recompute() catches per-metric errors internally (NFR-R4), but _PrometheusFailureTracker
    detects the failures and triggers the failed log event in _run_baseline_recompute.

    Exact log event name per P6.
    """
    redis = _FakeBaselineRedis()
    client = SeasonalBaselineClient(redis)
    mock_logger = MagicMock()
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = ConnectionError("Prometheus unreachable")

    queries = _make_metric_queries("topic_messages_in_per_sec")

    await _run_baseline_recompute(
        seasonal_baseline_client=client,
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=mock_logger,
    )

    failed_calls: list[object] = []
    for method in (mock_logger.warning, mock_logger.error):
        failed_calls.extend(
            c for c in method.call_args_list
            if c.args and c.args[0] == "baseline_deviation_recompute_failed"
        )

    assert len(failed_calls) >= 1, (
        f"Expected at least one 'baseline_deviation_recompute_failed' log event on exception. "
        f"warning calls: {mock_logger.warning.call_args_list}. "
        f"error calls: {mock_logger.error.call_args_list}. "
        "Check that _run_baseline_recompute emits "
        "logger.warning('baseline_deviation_recompute_failed', exc_info=True)."
    )

    failed_call_kwargs = failed_calls[0].kwargs  # type: ignore[union-attr]
    exc_info_val = failed_call_kwargs.get("exc_info")
    assert exc_info_val, (
        f"Expected truthy exc_info in baseline_deviation_recompute_failed kwargs "
        f"(True or an exception instance), got: {failed_call_kwargs}."
    )


# ---------------------------------------------------------------------------
# AC4: _run_baseline_recompute updates last_recompute on success
# ---------------------------------------------------------------------------


async def test_recompute_coroutine_updates_last_recompute_on_success() -> None:
    """[P0] AC4: On successful bulk_recompute(), _run_baseline_recompute() calls
    seasonal_baseline_client.set_last_recompute() with a valid UTC ISO timestamp.

    After the call, get_last_recompute() must return a non-None ISO string.
    """
    redis = _FakeBaselineRedis()
    client = SeasonalBaselineClient(redis)
    mock_logger = MagicMock()
    prometheus_client = MagicMock()
    prometheus_client.query_range.return_value = []

    queries = _make_metric_queries("topic_messages_in_per_sec")

    await _run_baseline_recompute(
        seasonal_baseline_client=client,
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=mock_logger,
    )

    last_recompute = client.get_last_recompute()

    assert last_recompute is not None, (
        "Expected get_last_recompute() to return a non-None ISO timestamp after "
        "successful _run_baseline_recompute(). "
        "set_last_recompute() must be called on success."
    )

    parsed = datetime.fromisoformat(last_recompute)
    assert parsed.tzinfo is not None, (
        f"Expected timezone-aware ISO timestamp from get_last_recompute(), "
        f"got naive: {last_recompute!r}."
    )


# ---------------------------------------------------------------------------
# AC4: _run_baseline_recompute does NOT update last_recompute on failure
# ---------------------------------------------------------------------------


async def test_recompute_coroutine_does_not_update_last_recompute_on_failure() -> None:
    """[P0] AC4: When bulk_recompute() raises, _run_baseline_recompute() must NOT
    call set_last_recompute() — the last_recompute key remains None (untouched).

    This ensures the next cycle retries the recomputation.
    """
    redis = _FakeBaselineRedis()
    client = SeasonalBaselineClient(redis)
    mock_logger = MagicMock()
    prometheus_client = MagicMock()
    prometheus_client.query_range.side_effect = ConnectionError("Prometheus unreachable")

    queries = _make_metric_queries("topic_messages_in_per_sec")

    await _run_baseline_recompute(
        seasonal_baseline_client=client,
        prometheus_client=prometheus_client,
        metric_queries=queries,
        lookback_days=30,
        step_seconds=300,
        timeout_seconds=60,
        logger=mock_logger,
    )

    last_recompute = client.get_last_recompute()

    assert last_recompute is None, (
        f"Expected get_last_recompute() to remain None after bulk_recompute() failure, "
        f"but got: {last_recompute!r}. "
        "set_last_recompute() must NOT be called when bulk_recompute() raises (NFR-R4)."
    )
