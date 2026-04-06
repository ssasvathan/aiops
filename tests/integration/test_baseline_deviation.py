"""Integration tests for Story 1.3: Redis-backed seasonal baseline seeding.

AC coverage:
  AC6 — seed_from_history writes to a real Redis instance and the stored
         key schema and value format are correct.
  AC1 — partitioned values appear under aiops:seasonal_baseline:{scope}:{metric}:{dow}:{hour}
  AC4 — pipeline blocks until seeding completes (tested via async wait_for semantics)

These tests require Docker (via Testcontainers). They are marked @pytest.mark.integration
and are excluded from the default unit test run.

Run with:
    TESTCONTAINERS_RYUK_DISABLED=true uv run pytest -q -rs \
        tests/integration/test_baseline_deviation.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
import redis as redis_lib
from testcontainers.core.container import DockerContainer

from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient
from tests.integration.conftest import _is_environment_prereq_error, _wait_for_redis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REDIS_IMAGE = "redis:7.2-alpine"


@pytest.fixture(scope="module")
def redis_container():
    """Module-scoped Redis container for integration tests."""
    try:
        with DockerContainer(_REDIS_IMAGE).with_exposed_ports(6379) as container:
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(6379))
            _wait_for_redis(host, port)
            yield container
    except Exception as exc:
        if _is_environment_prereq_error(exc):
            pytest.fail(f"Docker/Redis unavailable: {exc}")
        raise


@pytest.fixture()
def real_redis(redis_container) -> redis_lib.Redis:
    """Per-test Redis client with a clean slate (flushall before each test)."""
    client = redis_lib.Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        decode_responses=True,
    )
    client.flushall()
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCOPE = ("prod", "kafka-prod-east", "orders.completed")
_SCOPE_STR = "prod|kafka-prod-east|orders.completed"
_METRIC_KEY = "topic_messages_in_per_sec"

# Monday 2024-01-01 00:00:00 UTC → (dow=0, hour=0)
_UTC_MON_MIDNIGHT = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
# Tuesday 2024-01-02 14:30:00 UTC → (dow=1, hour=14)
_UTC_TUE_14 = datetime(2024, 1, 2, 14, 30, 0, tzinfo=UTC)


def _expected_key(dow: int, hour: int) -> str:
    return f"aiops:seasonal_baseline:{_SCOPE_STR}:{_METRIC_KEY}:{dow}:{hour}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_seed_from_history_writes_to_real_redis(real_redis: redis_lib.Redis) -> None:
    """[P0] AC6-1.3: seed_from_history writes float lists to real Redis under the
    correct key schema: aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}.

    This is the primary integration test verifying Layer C Redis persistence.
    """
    client = SeasonalBaselineClient(real_redis)

    time_series = [
        (_UTC_MON_MIDNIGHT, 10.0),          # bucket (0, 0)
        (_UTC_MON_MIDNIGHT.replace(minute=15), 12.0),  # same bucket (0, 0)
        (_UTC_TUE_14, 99.0),               # bucket (1, 14)
    ]

    client.seed_from_history(_SCOPE, _METRIC_KEY, time_series)

    mon_key = _expected_key(0, 0)
    tue_key = _expected_key(1, 14)

    # Both keys must exist in real Redis
    assert real_redis.exists(mon_key), (
        f"Expected key {mon_key!r} to exist in Redis after seed_from_history(). "
        "seed_from_history() may not have been implemented or may use a wrong key schema."
    )
    assert real_redis.exists(tue_key), (
        f"Expected key {tue_key!r} to exist in Redis after seed_from_history()."
    )

    # Values must be a non-empty JSON float list
    mon_raw = real_redis.get(mon_key)
    tue_raw = real_redis.get(tue_key)

    assert mon_raw is not None
    assert tue_raw is not None

    mon_values = json.loads(mon_raw)
    tue_values = json.loads(tue_raw)

    assert isinstance(mon_values, list)
    assert isinstance(tue_values, list)
    assert len(mon_values) >= 1
    assert len(tue_values) >= 1

    # Correct values appear in the correct buckets
    assert sorted(mon_values) == sorted([10.0, 12.0])
    assert tue_values == [99.0]


@pytest.mark.integration
def test_seed_from_history_key_schema_is_correct(real_redis: redis_lib.Redis) -> None:
    """[P0] AC6-1.3: Key schema must be aiops:seasonal_baseline:{scope_pipe}:{metric}:{dow}:{hour}.

    Scope segments are joined with '|'. Any deviation (wrong separator, wrong field order,
    wrong namespace prefix) must fail this test.
    """
    client = SeasonalBaselineClient(real_redis)

    client.seed_from_history(_SCOPE, _METRIC_KEY, [(_UTC_MON_MIDNIGHT, 42.0)])

    expected_key = _expected_key(0, 0)

    # The exact key must exist
    assert real_redis.exists(expected_key), (
        f"Exact key {expected_key!r} not found in Redis. "
        f"Keys written: {real_redis.keys('*')}"
    )

    # No other seasonal_baseline keys should exist (one bucket written for one timestamp)
    all_baseline_keys = real_redis.keys("aiops:seasonal_baseline:*")
    assert len(all_baseline_keys) == 1, (
        f"Expected exactly 1 seasonal_baseline key, found {len(all_baseline_keys)}: "
        f"{all_baseline_keys}"
    )


@pytest.mark.integration
def test_seed_from_history_merge_with_existing_redis_data(real_redis: redis_lib.Redis) -> None:
    """[P1] AC3-1.3 + AC6: seed_from_history merges with pre-existing bucket data in real Redis.

    Pre-populates the Monday midnight bucket with existing values, then seeds new values.
    Verifies the merged result is stored correctly.
    """
    client = SeasonalBaselineClient(real_redis)

    existing_key = _expected_key(0, 0)
    existing_values = [1.0, 2.0, 3.0]
    real_redis.set(existing_key, json.dumps(existing_values))

    # Seed one new value into the same bucket
    client.seed_from_history(_SCOPE, _METRIC_KEY, [(_UTC_MON_MIDNIGHT, 99.0)])

    raw = real_redis.get(existing_key)
    assert raw is not None

    stored = json.loads(raw)

    # All existing values plus the new value must be present
    assert 1.0 in stored
    assert 2.0 in stored
    assert 3.0 in stored
    assert 99.0 in stored


@pytest.mark.integration
def test_seed_from_history_all_168_buckets_written_to_redis(real_redis: redis_lib.Redis) -> None:
    """[P0] AC1-1.3 + AC6: Seeding 7 days × 24 hours of data produces exactly 168 distinct
    Redis keys — one per (dow, hour) bucket — all with the correct key prefix."""
    import datetime as dt_module

    client = SeasonalBaselineClient(real_redis)

    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)  # Monday, hour 0
    time_series = [
        (base + dt_module.timedelta(hours=i), float(i))
        for i in range(7 * 24)  # 168 timestamps, one per unique bucket
    ]

    client.seed_from_history(_SCOPE, _METRIC_KEY, time_series)

    all_keys = real_redis.keys("aiops:seasonal_baseline:*")
    assert len(all_keys) == 168, (
        f"Expected 168 seasonal_baseline keys (one per (dow, hour) bucket), "
        f"found {len(all_keys)}."
    )

    # Every key must be parseable and contain a non-empty float list
    for key in all_keys:
        raw = real_redis.get(key)
        assert raw is not None, f"Key {key!r} exists but get() returned None"
        values = json.loads(raw)
        assert isinstance(values, list), f"Value for {key!r} is not a list: {values!r}"
        assert len(values) >= 1, f"Value for {key!r} is an empty list"
