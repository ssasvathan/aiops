"""CaseFile retention lifecycle execution for object storage."""

from __future__ import annotations

import re
from calendar import monthrange
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import BaseModel

from aiops_triage_pipeline.contracts.casefile_retention_policy import CasefileRetentionPolicyV1
from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol

_CASEFILE_PREFIX = "cases/"
_MAX_BATCH_KEYS = 1000
_CASEFILE_OBJECT_KEY_RE = re.compile(r"^cases/(?P<case_id>[^/]+)/(?P<stage>[A-Za-z0-9_-]+)\.json$")


class CasefileLifecycleRunResult(BaseModel, frozen=True):
    """Structured lifecycle-run result for deterministic scheduled execution."""

    scanned_count: int
    eligible_count: int
    purged_count: int
    failed_count: int
    case_ids: tuple[str, ...]


class CasefileLifecycleRunner:
    """Run policy-driven lifecycle purges for CaseFile objects in object storage."""

    def __init__(
        self,
        *,
        object_store_client: ObjectStoreClientProtocol,
        policy: CasefileRetentionPolicyV1,
        app_env: str,
        policy_ref: str,
        governance_approval_ref: str | None,
        delete_batch_size: int = 500,
        list_page_size: int = 500,
    ) -> None:
        if delete_batch_size <= 0 or delete_batch_size > _MAX_BATCH_KEYS:
            raise ValueError(f"delete_batch_size must be between 1 and {_MAX_BATCH_KEYS}")
        if list_page_size <= 0 or list_page_size > _MAX_BATCH_KEYS:
            raise ValueError(f"list_page_size must be between 1 and {_MAX_BATCH_KEYS}")
        self._object_store_client = object_store_client
        self._policy = policy
        self._app_env = app_env
        self._policy_ref = policy_ref
        self._governance_approval_ref = (
            governance_approval_ref.strip() if governance_approval_ref else None
        )
        self._delete_batch_size = delete_batch_size
        self._list_page_size = list_page_size
        self._logger = get_logger("storage.lifecycle")

    def run_once(self, *, now: datetime | None = None) -> CasefileLifecycleRunResult:
        resolved_now = _resolve_now(now)
        cutoff = resolve_retention_cutoff(
            policy=self._policy,
            app_env=self._app_env,
            now=resolved_now,
        )

        scanned_count = 0
        case_objects: dict[str, list[tuple[str, datetime]]] = {}
        continuation_token: str | None = None

        while True:
            page = self._object_store_client.list_objects_page(
                prefix=_CASEFILE_PREFIX,
                continuation_token=continuation_token,
                max_keys=self._list_page_size,
            )
            scanned_count += len(page.objects)

            for item in page.objects:
                case_id = _extract_case_id(item.key)
                if case_id is None:
                    continue
                last_modified = _as_aware_utc(item.last_modified, field_name="last_modified")
                case_objects.setdefault(case_id, []).append((item.key, last_modified))

            continuation_token = page.next_continuation_token
            if continuation_token is None:
                break

        eligible_case_ids = {
            case_id
            for case_id, objects in case_objects.items()
            if _resolve_case_created_at(objects) <= cutoff
        }
        # Keep ordering deterministic so repeated scheduled runs are reproducible.
        ordered_keys = tuple(
            sorted(
                {
                    key
                    for case_id, objects in case_objects.items()
                    if case_id in eligible_case_ids
                    for key, _ in objects
                }
            )
        )
        if ordered_keys and self._governance_approval_ref is None:
            raise InvariantViolation(
                "governance approval metadata is required for destructive lifecycle purge"
            )

        purged_keys: list[str] = []
        failed_keys: list[str] = []
        for key_batch in _chunked(ordered_keys, self._delete_batch_size):
            delete_result = self._object_store_client.delete_objects_batch(
                keys=key_batch,
                governance_approval_ref=self._governance_approval_ref,
            )
            purged_keys.extend(delete_result.deleted_keys)
            failed_keys.extend(delete_result.failed_keys)

        case_ids = tuple(
            sorted(
                {
                    case_id
                    for case_id in (
                        *(_extract_case_id(key) for key in purged_keys),
                        *(_extract_case_id(key) for key in failed_keys),
                    )
                    if case_id is not None
                }
            )
        )
        result = CasefileLifecycleRunResult(
            scanned_count=scanned_count,
            eligible_count=len(ordered_keys),
            purged_count=len(purged_keys),
            failed_count=len(failed_keys),
            case_ids=case_ids,
        )
        self._logger.info(
            "casefile_lifecycle_audit",
            event_type="casefile.lifecycle_purge",
            component="storage.lifecycle",
            policy_ref=self._policy_ref,
            app_env=self._app_env,
            executed_at=resolved_now.isoformat(),
            cutoff_utc=cutoff.isoformat(),
            case_ids=result.case_ids,
            scanned_count=result.scanned_count,
            eligible_count=result.eligible_count,
            purged_count=result.purged_count,
            failed_count=result.failed_count,
            governance_approval_ref=self._governance_approval_ref,
        )
        return result


def resolve_retention_cutoff(
    *,
    policy: CasefileRetentionPolicyV1,
    app_env: str,
    now: datetime | None = None,
) -> datetime:
    retention = policy.retention_by_env.get(app_env)
    if retention is None:
        raise ValueError(f"unsupported app_env for casefile retention policy: {app_env}")
    resolved_now = _resolve_now(now)
    return _subtract_months(resolved_now, retention.retention_months)


def _resolve_now(now: datetime | None) -> datetime:
    resolved_now = now or datetime.now(tz=UTC)
    return _as_aware_utc(resolved_now, field_name="now")


def _as_aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _subtract_months(dt: datetime, months: int) -> datetime:
    total_month_index = dt.year * 12 + (dt.month - 1) - months
    year = total_month_index // 12
    month = (total_month_index % 12) + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _extract_case_id(key: str) -> str | None:
    matched = _CASEFILE_OBJECT_KEY_RE.match(key)
    if matched is None:
        return None
    return matched.group("case_id")


def _resolve_case_created_at(objects: Iterable[tuple[str, datetime]]) -> datetime:
    # Prefer triage stage timestamp as canonical case creation; fall back to earliest stage.
    values = tuple(objects)
    triage_times = tuple(
        last_modified for key, last_modified in values if key.endswith("/triage.json")
    )
    if triage_times:
        return min(triage_times)
    return min(last_modified for _, last_modified in values)


def _chunked(values: Iterable[str], chunk_size: int) -> tuple[tuple[str, ...], ...]:
    chunk: list[str] = []
    chunks: list[tuple[str, ...]] = []
    for value in values:
        chunk.append(value)
        if len(chunk) >= chunk_size:
            chunks.append(tuple(chunk))
            chunk = []
    if chunk:
        chunks.append(tuple(chunk))
    return tuple(chunks)
