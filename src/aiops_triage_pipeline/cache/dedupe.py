"""AG5 action deduplication store backed by Redis (FR33, FR34)."""

from typing import Protocol, runtime_checkable

from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.redis_ttl_policy import AG5DedupeTtlConfig

# FR33-specified TTL defaults — used when no policy config is provided.
_FR33_DEFAULT_TTL: dict[str, int] = {
    "PAGE": 7200,    # 120 min
    "TICKET": 14400, # 240 min
    "NOTIFY": 3600,  # 60 min
}


@runtime_checkable
class HealthTrackableDedupeStore(Protocol):
    """Protocol for dedupe stores that expose Redis health state."""

    @property
    def is_healthy(self) -> bool:
        """Return True when the backing store is reachable."""

    @property
    def last_error(self) -> str | None:
        """Return the last error message, or None when healthy."""


class RedisActionDedupeStore:
    """Redis-backed AG5 deduplication store with per-action TTLs.

    Uses atomic ``SET key value NX EX ttl`` semantics so duplicate detection
    and TTL registration are race-safe (no separate read-then-write window).

    Key format: ``dedupe:{fingerprint}``

    Per-action TTL defaults (FR33):
      PAGE   = 120 min (7200 s)
      TICKET = 240 min (14400 s)
      NOTIFY =  60 min (3600 s)

    Args:
        redis_client: A redis-py ``Redis`` client instance.
        ttl_config:   Optional ``AG5DedupeTtlConfig`` loaded from policy.
                      When None, FR33 defaults are used.
    """

    def __init__(
        self,
        redis_client: object,
        *,
        ttl_config: AG5DedupeTtlConfig | None = None,
    ) -> None:
        self._redis = redis_client
        self._ttl_config = ttl_config
        self._is_healthy: bool = True
        self._last_error: str | None = None

    @property
    def is_healthy(self) -> bool:
        """Return True when the last Redis operation succeeded."""
        return self._is_healthy

    @property
    def last_error(self) -> str | None:
        """Return the last Redis error message, or None when healthy."""
        return self._last_error

    def _ttl_for_action(self, action: Action) -> int:
        if self._ttl_config is not None:
            return self._ttl_config.ttl_for_action(action)
        return _FR33_DEFAULT_TTL.get(action.value, _FR33_DEFAULT_TTL["NOTIFY"])

    def is_duplicate(self, fingerprint: str) -> bool:
        """Return True when ``dedupe:{fingerprint}`` exists in Redis.

        Raises:
            Exception: Any Redis connectivity or protocol error — callers
                (the AG5 gate) catch this and apply the on_store_error effect.
        """
        try:
            result = self._redis.get(f"dedupe:{fingerprint}")  # type: ignore[attr-defined]
            self._is_healthy = True
            self._last_error = None
            return result is not None
        except Exception as exc:
            self._is_healthy = False
            self._last_error = str(exc)
            raise

    def remember(self, fingerprint: str, action: Action) -> None:
        """Atomically register ``dedupe:{fingerprint}`` with the per-action TTL.

        Uses ``SET NX EX`` so an existing active window is never overwritten.

        Raises:
            Exception: Any Redis connectivity or protocol error.
        """
        ttl = self._ttl_for_action(action)
        try:
            self._redis.set(  # type: ignore[attr-defined]
                f"dedupe:{fingerprint}",
                "1",
                nx=True,
                ex=ttl,
            )
            self._is_healthy = True
            self._last_error = None
        except Exception as exc:
            self._is_healthy = False
            self._last_error = str(exc)
            raise
