"""Unit tests for RedisActionDedupeStore (Story 5.5 — AG5 dedupe, FR33)."""

import pytest

from aiops_triage_pipeline.cache.dedupe import (
    HealthTrackableDedupeStore,
    RedisActionDedupeStore,
)
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.redis_ttl_policy import AG5DedupeTtlConfig


class _StubRedis:
    """In-memory Redis stub with SET NX EX and GET semantics."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self.set_calls: list[dict] = []

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        self.set_calls.append({"key": key, "value": value, "nx": nx, "ex": ex})
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


class _ErrorRedis:
    """Stub that always raises on any operation."""

    def get(self, key: str) -> None:  # noqa: ARG002
        raise ConnectionError("Redis unavailable")

    def set(self, key: str, value: str, **kwargs: object) -> None:  # noqa: ARG002
        raise ConnectionError("Redis unavailable")


# ── Key format ────────────────────────────────────────────────────────────────


def test_is_duplicate_uses_dedupe_key_prefix() -> None:
    redis = _StubRedis()
    redis._store["dedupe:fp-abc"] = "1"
    store = RedisActionDedupeStore(redis)

    assert store.is_duplicate("fp-abc") is True
    assert store.is_duplicate("fp-other") is False


def test_remember_writes_dedupe_key_prefix() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp-xyz", Action.PAGE)

    assert len(redis.set_calls) == 1
    assert redis.set_calls[0]["key"] == "dedupe:fp-xyz"
    assert redis.set_calls[0]["value"] == "1"


# ── Per-action TTL (FR33) — default values ────────────────────────────────────


def test_remember_page_uses_fr33_default_ttl() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp", Action.PAGE)

    assert redis.set_calls[0]["ex"] == 7200  # 120 min


def test_remember_ticket_uses_fr33_default_ttl() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp", Action.TICKET)

    assert redis.set_calls[0]["ex"] == 14400  # 240 min


def test_remember_notify_uses_fr33_default_ttl() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp", Action.NOTIFY)

    assert redis.set_calls[0]["ex"] == 3600  # 60 min


def test_remember_observe_falls_back_to_notify_ttl() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp", Action.OBSERVE)

    assert redis.set_calls[0]["ex"] == 3600


# ── Per-action TTL — policy override ─────────────────────────────────────────


def test_remember_uses_policy_ttl_when_provided() -> None:
    redis = _StubRedis()
    ttl_config = AG5DedupeTtlConfig(page_seconds=600, ticket_seconds=1200, notify_seconds=300)
    store = RedisActionDedupeStore(redis, ttl_config=ttl_config)
    store.remember("fp", Action.PAGE)

    assert redis.set_calls[0]["ex"] == 600


def test_remember_policy_ticket_ttl() -> None:
    redis = _StubRedis()
    ttl_config = AG5DedupeTtlConfig(page_seconds=600, ticket_seconds=1200, notify_seconds=300)
    store = RedisActionDedupeStore(redis, ttl_config=ttl_config)
    store.remember("fp", Action.TICKET)

    assert redis.set_calls[0]["ex"] == 1200


def test_remember_policy_notify_ttl() -> None:
    redis = _StubRedis()
    ttl_config = AG5DedupeTtlConfig(page_seconds=600, ticket_seconds=1200, notify_seconds=300)
    store = RedisActionDedupeStore(redis, ttl_config=ttl_config)
    store.remember("fp", Action.NOTIFY)

    assert redis.set_calls[0]["ex"] == 300


# ── Atomic NX semantics ───────────────────────────────────────────────────────


def test_remember_passes_nx_true_for_atomic_claim() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp", Action.PAGE)

    assert redis.set_calls[0]["nx"] is True


def test_remember_does_not_overwrite_active_window() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp", Action.PAGE)
    store.remember("fp", Action.PAGE)  # second call should be NX-rejected

    assert len(redis._store) == 1
    # Both calls were made, but the second was rejected by NX
    assert len(redis.set_calls) == 2


def test_remember_returns_true_when_key_is_newly_registered() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    assert store.remember("fp", Action.PAGE) is True


def test_remember_returns_false_when_nx_claim_is_rejected() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp", Action.PAGE)  # first call wins the claim
    assert store.remember("fp", Action.PAGE) is False  # NX rejects duplicate


# ── Deduplication behavior ────────────────────────────────────────────────────


def test_is_duplicate_returns_false_when_key_absent() -> None:
    store = RedisActionDedupeStore(_StubRedis())
    assert store.is_duplicate("fp-new") is False


def test_is_duplicate_returns_true_after_remember() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp-1", Action.TICKET)
    assert store.is_duplicate("fp-1") is True


def test_is_duplicate_returns_false_for_different_fingerprint() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(redis)
    store.remember("fp-a", Action.PAGE)
    assert store.is_duplicate("fp-b") is False


# ── Health tracking ───────────────────────────────────────────────────────────


def test_store_is_healthy_by_default() -> None:
    store = RedisActionDedupeStore(_StubRedis())
    assert store.is_healthy is True
    assert store.last_error is None


def test_is_duplicate_raises_and_marks_unhealthy_on_error() -> None:
    store = RedisActionDedupeStore(_ErrorRedis())

    with pytest.raises(ConnectionError):
        store.is_duplicate("fp")

    assert store.is_healthy is False
    assert store.last_error is not None
    assert "Redis unavailable" in store.last_error


def test_remember_raises_and_marks_unhealthy_on_error() -> None:
    store = RedisActionDedupeStore(_ErrorRedis())

    with pytest.raises(ConnectionError):
        store.remember("fp", Action.PAGE)

    assert store.is_healthy is False
    assert "Redis unavailable" in (store.last_error or "")


def test_store_recovers_healthy_after_success_following_error() -> None:
    redis = _StubRedis()
    store = RedisActionDedupeStore(_ErrorRedis())

    with pytest.raises(ConnectionError):
        store.is_duplicate("fp")

    assert store.is_healthy is False

    # Replace the redis client with a working one
    store._redis = redis  # type: ignore[attr-defined]
    store.is_duplicate("fp")

    assert store.is_healthy is True
    assert store.last_error is None


# ── HealthTrackableDedupeStore protocol ──────────────────────────────────────


def test_redis_action_dedupe_store_satisfies_health_trackable_protocol() -> None:
    store = RedisActionDedupeStore(_StubRedis())
    assert isinstance(store, HealthTrackableDedupeStore)


# ── AG5DedupeTtlConfig validation ────────────────────────────────────────────


def test_ag5_dedupe_ttl_config_defaults_match_fr33() -> None:
    config = AG5DedupeTtlConfig()
    assert config.page_seconds == 7200
    assert config.ticket_seconds == 14400
    assert config.notify_seconds == 3600


def test_ag5_dedupe_ttl_config_rejects_zero_ttl() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="must be positive"):
        AG5DedupeTtlConfig(page_seconds=0)


def test_ag5_dedupe_ttl_config_ttl_for_action_page() -> None:
    config = AG5DedupeTtlConfig(page_seconds=100, ticket_seconds=200, notify_seconds=50)
    assert config.ttl_for_action(Action.PAGE) == 100


def test_ag5_dedupe_ttl_config_ttl_for_action_ticket() -> None:
    config = AG5DedupeTtlConfig(page_seconds=100, ticket_seconds=200, notify_seconds=50)
    assert config.ttl_for_action(Action.TICKET) == 200


def test_ag5_dedupe_ttl_config_ttl_for_action_notify() -> None:
    config = AG5DedupeTtlConfig(page_seconds=100, ticket_seconds=200, notify_seconds=50)
    assert config.ttl_for_action(Action.NOTIFY) == 50


def test_ag5_dedupe_ttl_config_ttl_for_action_observe_returns_notify() -> None:
    config = AG5DedupeTtlConfig(page_seconds=100, ticket_seconds=200, notify_seconds=50)
    assert config.ttl_for_action(Action.OBSERVE) == 50
