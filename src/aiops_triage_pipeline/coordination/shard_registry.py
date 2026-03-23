"""Redis-backed shard coordination: assignment, lease, and checkpoint primitives."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

# ── Key builders (D1 namespace: aiops:shard:...) ─────────────────────────────


def build_shard_lease_key(shard_id: int) -> str:
    """Build Redis key for shard lease ownership."""
    return f"aiops:shard:lease:{shard_id}"


def build_shard_checkpoint_key(shard_id: int, interval_bucket: int) -> str:
    """Build Redis key for per-shard per-interval checkpoint."""
    return f"aiops:shard:checkpoint:{shard_id}:{interval_bucket}"


# ── Deterministic scope assignment ────────────────────────────────────────────


def scope_to_shard_id(scope: tuple[str, str, str], shard_count: int) -> int:
    """Map a scope tuple to its shard index via SHA-256 consistent hash."""
    key = "|".join(scope)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest, 16) % shard_count


def assign_scopes_to_pod(
    *,
    scopes: list[tuple[str, str, str]],
    active_pod_ids: list[str],
    shard_count: int,
    pod_id: str,
) -> list[tuple[str, str, str]]:
    """Deterministically assign scopes to a pod via consistent hash.

    Each scope is hashed (SHA-256) to a shard in [0, shard_count) and each
    shard is mapped to a pod via the sorted membership list.  Results are
    stable for identical inputs across processes (no PYTHONHASHSEED reliance).
    """
    if not active_pod_ids or shard_count <= 0:
        return list(scopes)

    sorted_pods = sorted(active_pod_ids)

    def _shard_owner(shard_id: int) -> str:
        return sorted_pods[shard_id % len(sorted_pods)]

    return [
        scope for scope in scopes
        if _shard_owner(scope_to_shard_id(scope, shard_count)) == pod_id
    ]


def filter_scopes_by_shard_ids(
    *,
    scopes: list[tuple[str, str, str]],
    acquired_shard_ids: set[int],
    shard_count: int,
) -> list[tuple[str, str, str]]:
    """Return scopes whose consistent-hash shard falls in acquired_shard_ids.

    Used by the scheduler loop to restrict processing to scopes owned by this
    pod's acquired leases (D11-D12).  Returns all scopes when acquired_shard_ids
    is empty or shard_count is not positive (fail-open, D3).
    """
    if not acquired_shard_ids or shard_count <= 0:
        return list(scopes)
    return [
        scope for scope in scopes
        if scope_to_shard_id(scope, shard_count) in acquired_shard_ids
    ]


# ── Lease outcome models ──────────────────────────────────────────────────────


class ShardLeaseStatus(str, Enum):
    """Canonical outcomes for shard lease acquisition attempts."""

    acquired = "acquired"
    yielded = "yielded"
    fail_open = "fail_open"


@dataclass(frozen=True, slots=True)
class ShardLeaseOutcome:
    """Structured lease acquisition result for shard coordination observability."""

    status: ShardLeaseStatus
    shard_id: int
    owner_id: str
    ttl_seconds: int
    holder_id: str | None = None
    reason: str | None = None


# ── Redis client protocol ─────────────────────────────────────────────────────


class RedisShardClientProtocol(Protocol):
    """Minimal Redis surface used by the shard coordinator."""

    def set(self, name: str, value: str, *, nx: bool, ex: int) -> bool:
        ...

    def get(self, name: str) -> str | bytes | None:
        ...


# ── Shard coordinator ─────────────────────────────────────────────────────────


class RedisShardCoordinator:
    """Acquire shard leases using Redis SET NX EX semantics.

    Follows the same fail-open pattern as RedisCycleLock: Redis failures are
    surfaced via ``ShardLeaseStatus.fail_open`` so the caller can fall back to
    full-scope processing rather than halting the scheduler cycle.
    """

    def __init__(
        self,
        *,
        redis_client: RedisShardClientProtocol,
        pod_id: str,
    ) -> None:
        self._redis_client = redis_client
        self._pod_id = pod_id

    def acquire_lease(
        self,
        *,
        shard_id: int,
        owner_id: str,
        lease_ttl_seconds: int,
    ) -> ShardLeaseOutcome:
        """Attempt to acquire a shard lease; yields if another holder exists.

        Uses ``SET NX EX`` — no explicit unlock; lease expires automatically so
        a new pod can recover ownership after the TTL elapses.
        """
        key = build_shard_lease_key(shard_id)
        try:
            acquired = bool(
                self._redis_client.set(
                    name=key,
                    value=owner_id,
                    nx=True,
                    ex=lease_ttl_seconds,
                )
            )
        except Exception as exc:  # noqa: BLE001 - coordination failure must fail open
            return ShardLeaseOutcome(
                status=ShardLeaseStatus.fail_open,
                shard_id=shard_id,
                owner_id=owner_id,
                ttl_seconds=lease_ttl_seconds,
                reason=f"redis shard lease failed: {exc}",
            )

        if acquired:
            return ShardLeaseOutcome(
                status=ShardLeaseStatus.acquired,
                shard_id=shard_id,
                owner_id=owner_id,
                ttl_seconds=lease_ttl_seconds,
            )

        holder_id: str | None = None
        try:
            raw = self._redis_client.get(key)
            if isinstance(raw, bytes):
                holder_id = raw.decode("utf-8")
            elif raw is not None:
                holder_id = str(raw)
        except Exception:  # noqa: BLE001 - holder lookup is best-effort
            holder_id = None

        return ShardLeaseOutcome(
            status=ShardLeaseStatus.yielded,
            shard_id=shard_id,
            owner_id=owner_id,
            ttl_seconds=lease_ttl_seconds,
            holder_id=holder_id,
        )
