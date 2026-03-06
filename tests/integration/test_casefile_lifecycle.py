from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import urlopen

import boto3
import pytest
from botocore.client import BaseClient
from testcontainers.core.container import DockerContainer

from aiops_triage_pipeline.contracts.casefile_retention_policy import (
    CasefileRetentionPolicy,
    CasefileRetentionPolicyV1,
)
from aiops_triage_pipeline.storage.client import (
    DeleteObjectsResult,
    ObjectStoreClientProtocol,
    ObjectStoreListPage,
    PutIfAbsentResult,
    S3ObjectStoreClient,
)
from aiops_triage_pipeline.storage.lifecycle import CasefileLifecycleRunner

_MINIO_IMAGE = "minio/minio:RELEASE.2025-01-20T14-49-07Z"
_MINIO_ACCESS_KEY = "minioadmin"
_MINIO_SECRET_KEY = "minioadmin"
_MINIO_BUCKET = "aiops-casefile-lifecycle-integration"


def _wait_for_minio(endpoint_url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{endpoint_url}/minio/health/live", timeout=1.0) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for MinIO health endpoint at {endpoint_url}")


@pytest.fixture
def minio_object_store() -> tuple[BaseClient, S3ObjectStoreClient]:
    try:
        with (
            DockerContainer(_MINIO_IMAGE)
            .with_env("MINIO_ROOT_USER", _MINIO_ACCESS_KEY)
            .with_env("MINIO_ROOT_PASSWORD", _MINIO_SECRET_KEY)
            .with_command("server /data --address :9000")
            .with_exposed_ports(9000) as container
        ):
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(9000))
            endpoint_url = f"http://{host}:{port}"
            _wait_for_minio(endpoint_url)

            s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=_MINIO_ACCESS_KEY,
                aws_secret_access_key=_MINIO_SECRET_KEY,
                region_name="us-east-1",
            )
            s3_client.create_bucket(Bucket=_MINIO_BUCKET)

            yield s3_client, S3ObjectStoreClient(
                s3_client=s3_client,
                bucket=_MINIO_BUCKET,
            )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Docker/MinIO unavailable for integration test: {exc}")


def _policy() -> CasefileRetentionPolicyV1:
    return CasefileRetentionPolicyV1(
        retention_by_env={
            "local": CasefileRetentionPolicy(retention_months=1),
            "dev": CasefileRetentionPolicy(retention_months=6),
            "uat": CasefileRetentionPolicy(retention_months=18),
            "prod": CasefileRetentionPolicy(retention_months=25),
        }
    )


def _put_object(s3_client: BaseClient, key: str) -> None:
    s3_client.put_object(
        Bucket=_MINIO_BUCKET,
        Key=key,
        Body=b'{"ok":true}',
        ContentType="application/json",
    )


def _list_keys(s3_client: BaseClient) -> set[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    keys: set[str] = set()
    for page in paginator.paginate(Bucket=_MINIO_BUCKET):
        for item in page.get("Contents", []):
            keys.add(str(item["Key"]))
    return keys


class _PartiallyFailingDeleteClient(ObjectStoreClientProtocol):
    def __init__(self, *, delegate: ObjectStoreClientProtocol, failing_key: str) -> None:
        self._delegate = delegate
        self._failing_key = failing_key

    def put_if_absent(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        checksum_sha256: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PutIfAbsentResult:
        return self._delegate.put_if_absent(
            key=key,
            body=body,
            content_type=content_type,
            checksum_sha256=checksum_sha256,
            metadata=metadata,
        )

    def get_object_bytes(self, *, key: str) -> bytes:
        return self._delegate.get_object_bytes(key=key)

    def list_objects_page(
        self,
        *,
        prefix: str,
        continuation_token: str | None = None,
        max_keys: int = 1000,
    ) -> ObjectStoreListPage:
        return self._delegate.list_objects_page(
            prefix=prefix,
            continuation_token=continuation_token,
            max_keys=max_keys,
        )

    def delete_objects_batch(self, *, keys: Sequence[str]) -> DeleteObjectsResult:
        passthrough_keys = tuple(key for key in keys if key != self._failing_key)
        result = self._delegate.delete_objects_batch(keys=passthrough_keys)
        if self._failing_key in keys:
            return DeleteObjectsResult(
                deleted_keys=result.deleted_keys,
                failed_keys=(*result.failed_keys, self._failing_key),
            )
        return result


@pytest.mark.integration
def test_casefile_lifecycle_purges_expired_scope_and_is_idempotent(
    minio_object_store: tuple[BaseClient, S3ObjectStoreClient],
) -> None:
    s3_client, object_store_client = minio_object_store
    _put_object(s3_client, "cases/case-old-a/triage.json")
    _put_object(s3_client, "cases/case-old-a/diagnosis.json")
    _put_object(s3_client, "cases/case-old-b/triage.json")
    _put_object(s3_client, "cases/case-old-c/labels.json")
    _put_object(s3_client, "other/unmanaged.json")

    runner = CasefileLifecycleRunner(
        object_store_client=object_store_client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-9000",
        delete_batch_size=2,
        list_page_size=2,
    )

    first = runner.run_once(now=datetime(2029, 1, 1, 0, 0, tzinfo=UTC))
    second = runner.run_once(now=datetime(2029, 1, 1, 0, 0, tzinfo=UTC))
    remaining_keys = _list_keys(s3_client)

    assert first.eligible_count == 4
    assert first.purged_count == 4
    assert first.failed_count == 0
    assert first.case_ids == ("case-old-a", "case-old-b", "case-old-c")
    assert second.eligible_count == 0
    assert second.purged_count == 0
    assert remaining_keys == {"other/unmanaged.json"}


@pytest.mark.integration
def test_casefile_lifecycle_keeps_non_expired_casefiles(
    minio_object_store: tuple[BaseClient, S3ObjectStoreClient],
) -> None:
    s3_client, object_store_client = minio_object_store
    _put_object(s3_client, "cases/case-fresh-a/triage.json")
    _put_object(s3_client, "cases/case-fresh-b/diagnosis.json")

    runner = CasefileLifecycleRunner(
        object_store_client=object_store_client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-9001",
        delete_batch_size=100,
        list_page_size=100,
    )

    result = runner.run_once(now=datetime(2026, 3, 6, 12, 0, tzinfo=UTC))
    remaining_keys = _list_keys(s3_client)

    assert result.eligible_count == 0
    assert result.purged_count == 0
    assert result.failed_count == 0
    assert "cases/case-fresh-a/triage.json" in remaining_keys
    assert "cases/case-fresh-b/diagnosis.json" in remaining_keys


@pytest.mark.integration
def test_casefile_lifecycle_tracks_partial_delete_failures(
    minio_object_store: tuple[BaseClient, S3ObjectStoreClient],
) -> None:
    s3_client, object_store_client = minio_object_store
    _put_object(s3_client, "cases/case-old-a/triage.json")
    _put_object(s3_client, "cases/case-old-b/triage.json")
    failing_key = "cases/case-old-b/triage.json"
    partially_failing_client = _PartiallyFailingDeleteClient(
        delegate=object_store_client,
        failing_key=failing_key,
    )

    runner = CasefileLifecycleRunner(
        object_store_client=partially_failing_client,
        policy=_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-9002",
        delete_batch_size=100,
        list_page_size=100,
    )

    result = runner.run_once(now=datetime(2029, 1, 1, 0, 0, tzinfo=UTC))
    remaining_keys = _list_keys(s3_client)

    assert result.eligible_count == 2
    assert result.purged_count == 1
    assert result.failed_count == 1
    assert result.case_ids == ("case-old-a", "case-old-b")
    assert failing_key in remaining_keys
