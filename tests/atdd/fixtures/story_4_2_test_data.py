"""ATDD fixture builders for Story 4.2 shard coordination and lease recovery."""

from __future__ import annotations

import time
from collections.abc import Callable


class RecordingRedisShardClient:
    """In-memory Redis probe with TTL support for shard-lease style tests."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._expires_at: dict[str, float] = {}
        self.set_calls: list[dict[str, object]] = []

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, expiry in self._expires_at.items() if expiry <= now]
        for key in expired:
            self._values.pop(key, None)
            self._expires_at.pop(key, None)

    def set(self, name: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        self._purge_expired()
        if nx and name in self._values:
            return False
        self._values[name] = value
        if ex is not None:
            self._expires_at[name] = time.monotonic() + float(ex)
        self.set_calls.append({"name": name, "value": value, "nx": nx, "ex": ex})
        return True

    def get(self, name: str) -> str | None:
        self._purge_expired()
        return self._values.get(name)


def build_settings_kwargs(**overrides: object) -> dict[str, object]:
    """Return minimal kwargs for constructing valid Settings instances in ATDD tests."""
    base: dict[str, object] = {
        "_env_file": None,
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "S3_ENDPOINT_URL": "http://localhost:9000",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "bucket",
    }
    base.update(overrides)
    return base


def load_module_or_fail(module_name: str, fail_fn: Callable[[str], object]) -> object:
    """Import helper for ATDD red-phase tests with actionable error messages."""
    import importlib

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - RED phase failure path
        fail_fn(
            f"Story 4.2 requires module {module_name!r}, but import failed: {exc}. "
            "Implement shard coordination module surface before green phase."
        )
