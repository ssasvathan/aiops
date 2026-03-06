from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from aiops_triage_pipeline.contracts.casefile_retention_policy import (
    CasefileRetentionPolicy,
    CasefileRetentionPolicyV1,
)
from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.storage.client import (
    DeleteObjectsResult,
    ObjectStoreClientProtocol,
    ObjectStoreListPage,
    ObjectSummary,
    PutIfAbsentResult,
)
from aiops_triage_pipeline.storage.lifecycle import (
    CasefileLifecycleRunner,
    resolve_retention_cutoff,
)


def _policy() -> CasefileRetentionPolicyV1:
    return CasefileRetentionPolicyV1(
        retention_by_env={
            "local": CasefileRetentionPolicy(retention_months=1),
            "dev": CasefileRetentionPolicy(retention_months=6),
            "uat": CasefileRetentionPolicy(retention_months=18),
            "prod": CasefileRetentionPolicy(retention_months=25),
        }
    )


class _InMemoryLifecycleObjectStore(ObjectStoreClientProtocol):
    def __init__(self, *, inventory: dict[str, datetime], fail_delete_keys: set[str] | None = None):
        self._inventory = dict(inventory)
        self._fail_delete_keys = set(fail_delete_keys or set())
        self.delete_calls: list[tuple[str, ...]] = []
        self.governance_approval_refs: list[str | None] = []

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
        self.delete_calls.append(tuple(keys))
        self.governance_approval_refs.append(governance_approval_ref)
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


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append((event, kwargs))


def test_resolve_retention_cutoff_uses_env_months() -> None:
    cutoff = resolve_retention_cutoff(
        policy=_policy(),
        app_env="prod",
        now=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
    )
    assert cutoff == datetime(2024, 2, 6, 12, 0, tzinfo=UTC)


def test_resolve_retention_cutoff_rejects_naive_now() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_retention_cutoff(
            policy=_policy(),
            app_env="prod",
            now=datetime(2026, 3, 6, 12, 0),
        )


def test_runner_paginates_and_deletes_in_bounded_batches() -> None:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    inventory = {
        "cases/case-old-1/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC),
        "cases/case-old-1/diagnosis.json": datetime(2023, 1, 2, 1, 0, tzinfo=UTC),
        "cases/case-old-2/triage.json": datetime(2023, 1, 3, 1, 0, tzinfo=UTC),
        "cases/case-fresh-1/triage.json": datetime(2025, 8, 1, 1, 0, tzinfo=UTC),
        "cases/not-a-case-layout": datetime(2023, 1, 4, 1, 0, tzinfo=UTC),
    }
    client = _InMemoryLifecycleObjectStore(inventory=inventory)
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-12345",
        delete_batch_size=2,
        list_page_size=2,
    )

    result = runner.run_once(now=now)

    assert result.scanned_count == 5
    assert result.eligible_count == 3
    assert result.purged_count == 3
    assert result.failed_count == 0
    assert result.case_ids == ("case-old-1", "case-old-2")
    assert client.delete_calls == [
        ("cases/case-old-1/diagnosis.json", "cases/case-old-1/triage.json"),
        ("cases/case-old-2/triage.json",),
    ]
    assert client.governance_approval_refs == ["CHG-12345", "CHG-12345"]


def test_runner_purges_full_case_scope_by_case_creation_timestamp() -> None:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    inventory = {
        "cases/case-mixed-age/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC),
        "cases/case-mixed-age/diagnosis.json": datetime(2025, 8, 1, 1, 0, tzinfo=UTC),
        "cases/case-fresh/triage.json": datetime(2025, 8, 2, 1, 0, tzinfo=UTC),
    }
    client = _InMemoryLifecycleObjectStore(inventory=inventory)
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-12346",
        delete_batch_size=100,
        list_page_size=100,
    )

    result = runner.run_once(now=now)

    assert result.eligible_count == 2
    assert result.purged_count == 2
    assert result.failed_count == 0
    assert result.case_ids == ("case-mixed-age",)
    assert "cases/case-fresh/triage.json" in client._inventory  # noqa: SLF001


def test_runner_is_idempotent_across_repeated_runs() -> None:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    client = _InMemoryLifecycleObjectStore(
        inventory={"cases/case-old-1/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC)}
    )
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-12345",
        delete_batch_size=100,
        list_page_size=100,
    )

    first = runner.run_once(now=now)
    second = runner.run_once(now=now)

    assert first.purged_count == 1
    assert second.purged_count == 0
    assert second.eligible_count == 0


def test_runner_tracks_partial_delete_failures() -> None:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    failing_key = "cases/case-old-2/triage.json"
    inventory = {
        "cases/case-old-1/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC),
        failing_key: datetime(2023, 1, 2, 1, 0, tzinfo=UTC),
    }
    client = _InMemoryLifecycleObjectStore(inventory=inventory, fail_delete_keys={failing_key})
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-12345",
        delete_batch_size=100,
        list_page_size=100,
    )

    result = runner.run_once(now=now)

    assert result.purged_count == 1
    assert result.failed_count == 1
    assert result.case_ids == ("case-old-1", "case-old-2")


def test_runner_requires_governance_approval_for_destructive_purge() -> None:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    client = _InMemoryLifecycleObjectStore(
        inventory={"cases/case-old-1/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC)}
    )
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref=None,
        delete_batch_size=100,
        list_page_size=100,
    )

    with pytest.raises(InvariantViolation, match="governance approval"):
        runner.run_once(now=now)


def test_runner_emits_audit_log_with_required_fields() -> None:
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    client = _InMemoryLifecycleObjectStore(
        inventory={"cases/case-old-1/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC)}
    )
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-12345",
        delete_batch_size=100,
        list_page_size=100,
    )
    logger = _RecordingLogger()
    runner._logger = logger  # noqa: SLF001

    runner.run_once(now=now)

    assert logger.events
    event_name, fields = logger.events[0]
    assert event_name == "casefile_lifecycle_audit"
    assert fields["event_type"] == "casefile.lifecycle_purge"
    assert fields["component"] == "storage.lifecycle"
    assert fields["policy_ref"] == "casefile-retention-policy-v1"
    assert fields["app_env"] == "prod"
    assert fields["executed_at"] == now.isoformat()
    assert fields["case_ids"] == ("case-old-1",)
    assert fields["purged_count"] == 1
    assert fields["failed_count"] == 0
