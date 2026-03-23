"""Unit tests for distributed coordination flag-combination behavior.

The central invariant for Story 4.3: DISTRIBUTED_CYCLE_LOCK_ENABLED=False and
SHARD_REGISTRY_ENABLED=False must produce zero Redis coordination side effects.

Tests use call-recording fake Redis (per-file, no shared fixture) to assert
that no SET or GET commands are issued when the relevant feature flag is off.
"""

from __future__ import annotations

from aiops_triage_pipeline.config.settings import Settings
from aiops_triage_pipeline.coordination.cycle_lock import RedisCycleLock
from aiops_triage_pipeline.coordination.shard_registry import RedisShardCoordinator

# ── Base settings kwargs ──────────────────────────────────────────────────────

_SETTINGS_BASE: dict = dict(
    _env_file=None,
    KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
    DATABASE_URL="postgresql+psycopg://u:p@h/db",
    REDIS_URL="redis://localhost:6379/0",
    S3_ENDPOINT_URL="http://localhost:9000",
    S3_ACCESS_KEY="key",
    S3_SECRET_KEY="secret",
    S3_BUCKET="bucket",
)

# ── Call-recording fake Redis ─────────────────────────────────────────────────


class _CallRecordingRedis:
    """In-memory Redis stub that records every SET and GET call.

    Tracks calls to ``set`` and ``get`` so tests can assert that no Redis
    coordination commands are issued when a feature flag is disabled.
    """

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self.set_calls: list[dict] = []
        self.get_calls: list[str] = []

    def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        self.set_calls.append({"name": name, "value": value, "nx": nx, "ex": ex})
        if nx and name in self._values:
            return False
        self._values[name] = value
        return True

    def get(self, name: str) -> str | None:
        self.get_calls.append(name)
        return self._values.get(name)

    @property
    def total_calls(self) -> int:
        """Total number of SET + GET calls issued to this fake Redis."""
        return len(self.set_calls) + len(self.get_calls)

    def lock_set_calls(self) -> list[dict]:
        """SET calls targeting the aiops:lock:* namespace."""
        return [c for c in self.set_calls if c["name"].startswith("aiops:lock:")]

    def shard_set_calls(self) -> list[dict]:
        """SET calls targeting the aiops:shard:* namespace."""
        return [c for c in self.set_calls if c["name"].startswith("aiops:shard:")]


# ── Helper: simulate flag-gated coordination calls ───────────────────────────


def _simulate_coordinated_cycle(
    *,
    settings: Settings,
    cycle_lock: RedisCycleLock,
    shard_coordinator: RedisShardCoordinator,
    interval_seconds: int = 300,
    owner_id: str = "test-pod",
) -> None:
    """Simulate one scheduler cycle's flag-gated coordination calls.

    Mirrors the conditional logic in the hot-path scheduler loop
    (``__main__._run_hot_path_scheduler_loop``) so unit tests can assert
    Redis side effects without spinning up the full async scheduler.
    """
    if settings.DISTRIBUTED_CYCLE_LOCK_ENABLED:
        cycle_lock.acquire(interval_seconds=interval_seconds, owner_id=owner_id)

    if settings.SHARD_REGISTRY_ENABLED:
        shard_coordinator.acquire_lease(
            shard_id=0,
            owner_id=owner_id,
            lease_ttl_seconds=settings.SHARD_LEASE_TTL_SECONDS,
        )


# ── Flag-combination tests ────────────────────────────────────────────────────


def test_both_flags_false_produces_zero_redis_coordination_calls() -> None:
    """Both flags off → zero Redis SET/GET calls (the central invariant, AC 1)."""
    settings = Settings(**{
        **_SETTINGS_BASE,
        "DISTRIBUTED_CYCLE_LOCK_ENABLED": False,
        "SHARD_REGISTRY_ENABLED": False,
    })
    fake_redis = _CallRecordingRedis()
    cycle_lock = RedisCycleLock(redis_client=fake_redis, margin_seconds=60)
    shard_coordinator = RedisShardCoordinator(redis_client=fake_redis, pod_id="test-pod")

    _simulate_coordinated_cycle(
        settings=settings,
        cycle_lock=cycle_lock,
        shard_coordinator=shard_coordinator,
    )

    assert fake_redis.total_calls == 0, (
        f"Expected zero Redis calls with both flags disabled, "
        f"got {fake_redis.total_calls}: set={fake_redis.set_calls}, get={fake_redis.get_calls}"
    )


def test_lock_enabled_shard_disabled_emits_lock_calls_only() -> None:
    """Lock flag=True, shard flag=False → only lock Redis calls, zero shard calls (AC 2)."""
    settings = Settings(**{
        **_SETTINGS_BASE,
        "DISTRIBUTED_CYCLE_LOCK_ENABLED": True,
        "SHARD_REGISTRY_ENABLED": False,
    })
    fake_redis = _CallRecordingRedis()
    cycle_lock = RedisCycleLock(redis_client=fake_redis, margin_seconds=60)
    shard_coordinator = RedisShardCoordinator(redis_client=fake_redis, pod_id="test-pod")

    _simulate_coordinated_cycle(
        settings=settings,
        cycle_lock=cycle_lock,
        shard_coordinator=shard_coordinator,
    )

    lock_calls = fake_redis.lock_set_calls()
    shard_calls = fake_redis.shard_set_calls()

    assert len(lock_calls) >= 1, (
        f"Expected at least one Redis SET on aiops:lock:* when DISTRIBUTED_CYCLE_LOCK_ENABLED=True,"
        f" got: {lock_calls}"
    )
    assert shard_calls == [], (
        f"Expected zero Redis calls on aiops:shard:* when SHARD_REGISTRY_ENABLED=False,"
        f" got: {shard_calls}"
    )


def test_both_flags_true_activates_lock_and_shard_coordination() -> None:
    """Both flags enabled → lock and shard coordination both issue Redis calls (AC 1, 2)."""
    settings = Settings(**{
        **_SETTINGS_BASE,
        "DISTRIBUTED_CYCLE_LOCK_ENABLED": True,
        "SHARD_REGISTRY_ENABLED": True,
    })
    fake_redis = _CallRecordingRedis()
    cycle_lock = RedisCycleLock(redis_client=fake_redis, margin_seconds=60)
    shard_coordinator = RedisShardCoordinator(redis_client=fake_redis, pod_id="test-pod")

    _simulate_coordinated_cycle(
        settings=settings,
        cycle_lock=cycle_lock,
        shard_coordinator=shard_coordinator,
    )

    assert fake_redis.lock_set_calls(), (
        "Expected at least one lock Redis call when DISTRIBUTED_CYCLE_LOCK_ENABLED=True"
    )
    assert fake_redis.shard_set_calls(), (
        "Expected at least one shard Redis call when SHARD_REGISTRY_ENABLED=True"
    )


def test_flag_disabled_after_enabled_produces_valid_settings_with_default_false() -> None:
    """Rollback: disabling both flags after they were enabled produces valid Settings (AC 2)."""
    # Phase: flags enabled (simulates an operator enabling distributed coordination)
    settings_enabled = Settings(**{
        **_SETTINGS_BASE,
        "DISTRIBUTED_CYCLE_LOCK_ENABLED": True,
        "SHARD_REGISTRY_ENABLED": True,
    })
    assert settings_enabled.DISTRIBUTED_CYCLE_LOCK_ENABLED is True
    assert settings_enabled.SHARD_REGISTRY_ENABLED is True

    # Rollback: both flags return to default False (no env var override)
    settings_disabled = Settings(**_SETTINGS_BASE)
    assert settings_disabled.DISTRIBUTED_CYCLE_LOCK_ENABLED is False
    assert settings_disabled.SHARD_REGISTRY_ENABLED is False
    # No ValidationError raised — rollback requires no schema migration
