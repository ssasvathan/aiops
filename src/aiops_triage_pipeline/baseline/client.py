"""SeasonalBaselineClient — Redis I/O boundary for seasonal baseline data (D3)."""

import json
from collections.abc import Sequence
from typing import Protocol

from aiops_triage_pipeline.baseline.constants import MAX_BUCKET_VALUES

BaselineScope = tuple[str, ...]


class SeasonalBaselineClientProtocol(Protocol):
    """Structural protocol for Redis-like clients used by SeasonalBaselineClient."""

    def get(self, key: str) -> str | bytes | None:
        ...

    def mget(self, keys: Sequence[str]) -> Sequence[str | bytes | None]:
        ...

    def set(self, key: str, value: str) -> bool | None:
        ...


class SeasonalBaselineClient:
    """Encapsulates all Redis I/O for seasonal baseline storage.

    Key schema: aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}
    Value format: JSON float list, max MAX_BUCKET_VALUES items.
    """

    def __init__(self, redis_client: SeasonalBaselineClientProtocol) -> None:
        self._redis = redis_client

    def _build_key(
        self,
        scope: BaselineScope,
        metric_key: str,
        dow: int,
        hour: int,
    ) -> str:
        """Build the Redis key for a given scope, metric, and time bucket."""
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
        decoded = raw if isinstance(raw, str) else raw.decode()
        return json.loads(decoded)

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
                decoded = raw if isinstance(raw, str) else raw.decode()
                result[metric_key] = json.loads(decoded)
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
