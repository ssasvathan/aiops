"""Redis-backed distributed cycle lock with fail-open semantics."""

from aiops_triage_pipeline.coordination.protocol import (
    CycleLockOutcome,
    CycleLockStatus,
    RedisLockClientProtocol,
)

DEFAULT_CYCLE_LOCK_KEY = "aiops:lock:cycle"
DEFAULT_CYCLE_LOCK_MARGIN_SECONDS = 60


class RedisCycleLock:
    """Acquire scheduler interval ownership using Redis SET NX EX."""

    def __init__(
        self,
        *,
        redis_client: RedisLockClientProtocol,
        margin_seconds: int = DEFAULT_CYCLE_LOCK_MARGIN_SECONDS,
        key: str = DEFAULT_CYCLE_LOCK_KEY,
    ) -> None:
        if margin_seconds <= 0:
            raise ValueError("margin_seconds must be > 0")
        self._redis_client = redis_client
        self._margin_seconds = margin_seconds
        self._key = key

    def acquire(self, *, interval_seconds: int, owner_id: str) -> CycleLockOutcome:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        ttl_seconds = max(1, int(interval_seconds) + self._margin_seconds)
        try:
            acquired = bool(
                self._redis_client.set(
                    name=self._key,
                    value=owner_id,
                    nx=True,
                    ex=ttl_seconds,
                )
            )
        except Exception as exc:  # noqa: BLE001 - lock failure must fail open
            return CycleLockOutcome(
                status=CycleLockStatus.fail_open,
                key=self._key,
                owner_id=owner_id,
                ttl_seconds=ttl_seconds,
                reason=f"redis lock acquisition failed: {exc}",
            )

        if acquired:
            return CycleLockOutcome(
                status=CycleLockStatus.acquired,
                key=self._key,
                owner_id=owner_id,
                ttl_seconds=ttl_seconds,
            )

        holder_id: str | None = None
        try:
            raw_holder = self._redis_client.get(self._key)
            if isinstance(raw_holder, bytes):
                holder_id = raw_holder.decode("utf-8")
            elif raw_holder is not None:
                holder_id = str(raw_holder)
        except Exception:  # noqa: BLE001 - holder lookup is best-effort only
            holder_id = None

        return CycleLockOutcome(
            status=CycleLockStatus.yielded,
            key=self._key,
            owner_id=owner_id,
            ttl_seconds=ttl_seconds,
            holder_id=holder_id,
        )


# Backward-compatible class name accepted by ATDD fixtures.
DistributedCycleLock = RedisCycleLock
