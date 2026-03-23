"""Distributed cycle-lock protocol models and interfaces."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class CycleLockStatus(str, Enum):
    """Canonical outcomes for distributed cycle lock acquisition attempts."""

    acquired = "acquired"
    yielded = "yielded"
    fail_open = "fail_open"


@dataclass(frozen=True, slots=True)
class CycleLockOutcome:
    """Structured lock acquisition result for scheduler decisions and observability."""

    status: CycleLockStatus
    key: str
    owner_id: str
    ttl_seconds: int
    holder_id: str | None = None
    reason: str | None = None


class RedisLockClientProtocol(Protocol):
    """Minimal Redis surface used by the cycle lock implementation."""

    def set(self, name: str, value: str, *, nx: bool, ex: int) -> bool:
        ...

    def get(self, name: str) -> str | bytes | None:
        ...


class CycleLockProtocol(Protocol):
    """Interface consumed by the hot-path scheduler loop."""

    def acquire(self, *, interval_seconds: int, owner_id: str) -> CycleLockOutcome:
        ...
