"""ATDD fixture builders for Story 4.1 distributed cycle lock fail-open behavior."""

from __future__ import annotations

from collections.abc import Callable


class RecordingRedisLockClient:
    """In-memory Redis lock probe for Story 4.1 acceptance tests."""

    def __init__(
        self,
        *,
        set_result: bool = True,
        holder_value: str | None = None,
        raise_on_set: Exception | None = None,
    ) -> None:
        self._set_result = set_result
        self._holder_value = holder_value
        self._raise_on_set = raise_on_set
        self.set_calls: list[dict[str, object]] = []

    def set(self, name: str, value: str, *, nx: bool, ex: int) -> bool:
        if self._raise_on_set is not None:
            raise self._raise_on_set

        self.set_calls.append(
            {
                "name": name,
                "value": value,
                "nx": nx,
                "ex": ex,
            }
        )
        if self._set_result:
            self._holder_value = value
        return self._set_result

    def get(self, name: str) -> str | None:  # noqa: ARG002 - Redis compatibility surface
        return self._holder_value


def build_settings_kwargs(**overrides: object) -> dict[str, object]:
    """Return minimal kwargs for constructing a valid Settings instance in tests."""
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


def to_status_value(outcome: object) -> str | None:
    """Normalize lock outcome.status across enum/string implementations."""
    status = getattr(outcome, "status", None)
    if status is None:
        return None
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def extract_holder(outcome: object) -> str | None:
    """Read holder context from outcome across holder/holder_id naming variants."""
    holder = getattr(outcome, "holder", None)
    if holder is None:
        holder = getattr(outcome, "holder_id", None)
    if holder is None:
        return None
    if isinstance(holder, bytes):
        return holder.decode("utf-8")
    return str(holder)


def load_module_or_fail(module_name: str, fail_fn: Callable[[str], object]) -> object:
    """Import helper shared by ATDD tests so missing modules fail with actionable text."""
    import importlib

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - RED phase failure path
        fail_fn(
            f"Story 4.1 requires module {module_name!r}, but import failed: {exc}. "
            "Implement distributed cycle lock package surface first."
        )
