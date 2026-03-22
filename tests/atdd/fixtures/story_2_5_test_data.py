"""ATDD fixture builders for Story 2.5 casefile lifecycle retention purge."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from aiops_triage_pipeline.contracts.casefile_retention_policy import (
    CasefileRetentionPolicy,
    CasefileRetentionPolicyV1,
)
from aiops_triage_pipeline.storage.client import (
    DeleteObjectsResult,
    ObjectStoreClientProtocol,
    ObjectStoreListPage,
    ObjectSummary,
    PutIfAbsentResult,
)


class InMemoryLifecycleObjectStore(ObjectStoreClientProtocol):
    """Deterministic in-memory object store for lifecycle ATDD tests."""

    def __init__(self, *, inventory: dict[str, datetime], fail_delete_keys: set[str] | None = None):
        self._inventory = dict(inventory)
        self._fail_delete_keys = set(fail_delete_keys or set())

    def put_if_absent(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        checksum_sha256: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PutIfAbsentResult:
        del key, body, content_type, checksum_sha256, metadata
        return PutIfAbsentResult.CREATED

    def get_object_bytes(self, *, key: str) -> bytes:
        return key.encode("utf-8")

    def list_objects_page(
        self,
        *,
        prefix: str,
        continuation_token: str | None = None,
        max_keys: int = 1000,
    ) -> ObjectStoreListPage:
        keys = tuple(sorted(k for k in self._inventory if k.startswith(prefix)))
        start = int(continuation_token or "0")
        end = start + max_keys
        page_keys = keys[start:end]
        next_token = str(end) if end < len(keys) else None
        return ObjectStoreListPage(
            objects=tuple(
                ObjectSummary(key=key, last_modified=self._inventory[key]) for key in page_keys
            ),
            next_continuation_token=next_token,
        )

    def delete_objects_batch(
        self,
        *,
        keys: Sequence[str],
        governance_approval_ref: str | None = None,
    ) -> DeleteObjectsResult:
        del governance_approval_ref
        deleted: list[str] = []
        failed: list[str] = []
        for key in keys:
            if key in self._fail_delete_keys:
                failed.append(key)
                continue
            if key in self._inventory:
                deleted.append(key)
                del self._inventory[key]
        return DeleteObjectsResult(deleted_keys=tuple(deleted), failed_keys=tuple(failed))


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append((event, kwargs))


def build_retention_policy() -> CasefileRetentionPolicyV1:
    return CasefileRetentionPolicyV1(
        retention_by_env={
            "local": CasefileRetentionPolicy(retention_months=1),
            "dev": CasefileRetentionPolicy(retention_months=6),
            "uat": CasefileRetentionPolicy(retention_months=18),
            "prod": CasefileRetentionPolicy(retention_months=25),
        }
    )
