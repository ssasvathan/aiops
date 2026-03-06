"""Object-store client abstractions and S3-backed implementation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from pydantic import AwareDatetime, BaseModel

from aiops_triage_pipeline.config.settings import Settings, get_settings
from aiops_triage_pipeline.errors.exceptions import (
    CriticalDependencyError,
    IntegrationError,
    ObjectNotFoundError,
)

_RETRIABLE_CONDITION_STATUS_CODES = frozenset({409, 412})
_RETRIABLE_CONDITION_ERROR_CODES = frozenset({"PreconditionFailed", "ConditionalRequestConflict"})
_CONNECTIVITY_ERRORS = (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError)
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "NotFound"})
_S3_MAX_BATCH_KEYS = 1000


class PutIfAbsentResult(StrEnum):
    """Result status for write-once put operations."""

    CREATED = "created"
    EXISTS = "exists"


class ObjectSummary(BaseModel, frozen=True):
    """Metadata for an object discovered via listing APIs."""

    key: str
    last_modified: AwareDatetime


class ObjectStoreListPage(BaseModel, frozen=True):
    """Single page of object listing results."""

    objects: tuple[ObjectSummary, ...]
    next_continuation_token: str | None = None


class DeleteObjectsResult(BaseModel, frozen=True):
    """Batch delete result from object storage."""

    deleted_keys: tuple[str, ...]
    failed_keys: tuple[str, ...]


class ObjectStoreClientProtocol(Protocol):
    """Abstraction for casefile persistence against object storage."""

    def put_if_absent(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        checksum_sha256: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> PutIfAbsentResult: ...

    def get_object_bytes(self, *, key: str) -> bytes: ...

    def list_objects_page(
        self,
        *,
        prefix: str,
        continuation_token: str | None = None,
        max_keys: int = 1000,
    ) -> ObjectStoreListPage: ...

    def delete_objects_batch(self, *, keys: Sequence[str]) -> DeleteObjectsResult: ...


class S3ObjectStoreClient(ObjectStoreClientProtocol):
    """S3/MinIO object-store adapter with explicit create-only semantics."""

    def __init__(self, *, s3_client: BaseClient, bucket: str) -> None:
        normalized_bucket = bucket.strip()
        if not normalized_bucket:
            raise ValueError("bucket must not be empty")

        self._s3_client = s3_client
        self._bucket = normalized_bucket

    def put_if_absent(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        checksum_sha256: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> PutIfAbsentResult:
        request: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": body,
            "ContentType": content_type,
            "IfNoneMatch": "*",
            "Metadata": dict(metadata or {}),
        }
        if checksum_sha256:
            request["ChecksumSHA256"] = checksum_sha256

        try:
            self._s3_client.put_object(**request)
            return PutIfAbsentResult.CREATED
        except ClientError as exc:
            code = _extract_error_code(exc)
            status_code = _extract_http_status_code(exc)
            if (
                code in _RETRIABLE_CONDITION_ERROR_CODES
                or status_code in _RETRIABLE_CONDITION_STATUS_CODES
            ):
                return PutIfAbsentResult.EXISTS
            if status_code is not None and status_code >= 500:
                raise CriticalDependencyError(
                    "object storage unavailable during put_if_absent "
                    f"key={key}: {code or status_code}"
                ) from exc
            raise IntegrationError(
                f"object storage put_if_absent failed key={key}: {code or 'unknown_client_error'}"
            ) from exc
        except _CONNECTIVITY_ERRORS as exc:
            raise CriticalDependencyError(
                f"object storage unavailable during put_if_absent key={key}: {exc}"
            ) from exc
        except BotoCoreError as exc:
            raise CriticalDependencyError(
                f"object storage runtime error during put_if_absent key={key}: {exc}"
            ) from exc

    def get_object_bytes(self, *, key: str) -> bytes:
        try:
            response = self._s3_client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read()
            if not isinstance(body, bytes):
                raise IntegrationError(
                    f"object storage returned non-bytes payload for key={key}"
                )
            return body
        except ClientError as exc:
            code = _extract_error_code(exc)
            status_code = _extract_http_status_code(exc)
            if code in _NOT_FOUND_CODES:
                raise ObjectNotFoundError(f"object not found key={key}") from exc
            if status_code is not None and status_code >= 500:
                raise CriticalDependencyError(
                    f"object storage unavailable during get_object key={key}: {code or status_code}"
                ) from exc
            raise IntegrationError(
                f"object storage get_object failed key={key}: {code or 'unknown_client_error'}"
            ) from exc
        except _CONNECTIVITY_ERRORS as exc:
            raise CriticalDependencyError(
                f"object storage unavailable during get_object key={key}: {exc}"
            ) from exc
        except BotoCoreError as exc:
            raise CriticalDependencyError(
                f"object storage runtime error during get_object key={key}: {exc}"
            ) from exc

    def list_objects_page(
        self,
        *,
        prefix: str,
        continuation_token: str | None = None,
        max_keys: int = 1000,
    ) -> ObjectStoreListPage:
        if max_keys <= 0 or max_keys > _S3_MAX_BATCH_KEYS:
            raise ValueError(f"max_keys must be between 1 and {_S3_MAX_BATCH_KEYS}")
        request: dict[str, Any] = {
            "Bucket": self._bucket,
            "Prefix": prefix,
            "MaxKeys": max_keys,
        }
        if continuation_token:
            request["ContinuationToken"] = continuation_token

        try:
            response = self._s3_client.list_objects_v2(**request)
            contents = response.get("Contents", [])
            objects: list[ObjectSummary] = []
            for item in contents:
                key = item.get("Key")
                last_modified = item.get("LastModified")
                if not isinstance(key, str):
                    raise IntegrationError("object storage list returned invalid object key")
                if not isinstance(last_modified, datetime) or last_modified.tzinfo is None:
                    raise IntegrationError(
                        "object storage list returned non-aware LastModified timestamp"
                    )
                objects.append(
                    ObjectSummary(
                        key=key,
                        last_modified=last_modified.astimezone(UTC),
                    )
                )
            next_token = response.get("NextContinuationToken")
            return ObjectStoreListPage(
                objects=tuple(objects),
                next_continuation_token=str(next_token) if next_token is not None else None,
            )
        except ClientError as exc:
            code = _extract_error_code(exc)
            status_code = _extract_http_status_code(exc)
            if status_code is not None and status_code >= 500:
                raise CriticalDependencyError(
                    "object storage unavailable during list_objects "
                    f"key={prefix}: {code or status_code}"
                ) from exc
            raise IntegrationError(
                "object storage list_objects failed "
                f"prefix={prefix}: {code or 'unknown_client_error'}"
            ) from exc
        except _CONNECTIVITY_ERRORS as exc:
            raise CriticalDependencyError(
                f"object storage unavailable during list_objects prefix={prefix}: {exc}"
            ) from exc
        except BotoCoreError as exc:
            raise CriticalDependencyError(
                f"object storage runtime error during list_objects prefix={prefix}: {exc}"
            ) from exc

    def delete_objects_batch(self, *, keys: Sequence[str]) -> DeleteObjectsResult:
        normalized_keys = tuple(
            key.strip() for key in keys if isinstance(key, str) and key.strip()
        )
        if not normalized_keys:
            return DeleteObjectsResult(deleted_keys=tuple(), failed_keys=tuple())
        if len(normalized_keys) > _S3_MAX_BATCH_KEYS:
            raise ValueError(
                f"delete_objects_batch supports at most {_S3_MAX_BATCH_KEYS} keys per request"
            )

        try:
            response = self._s3_client.delete_objects(
                Bucket=self._bucket,
                Delete={
                    "Objects": [{"Key": key} for key in normalized_keys],
                    # Keep non-quiet mode so deleted keys are returned for audit counts.
                    "Quiet": False,
                },
            )
            deleted_keys = tuple(
                str(entry.get("Key"))
                for entry in response.get("Deleted", [])
                if entry.get("Key")
            )
            failed_keys = tuple(
                str(entry.get("Key"))
                for entry in response.get("Errors", [])
                if entry.get("Key")
            )
            return DeleteObjectsResult(
                deleted_keys=deleted_keys,
                failed_keys=failed_keys,
            )
        except ClientError as exc:
            code = _extract_error_code(exc)
            status_code = _extract_http_status_code(exc)
            if status_code is not None and status_code >= 500:
                raise CriticalDependencyError(
                    "object storage unavailable during delete_objects_batch "
                    f"keys={len(normalized_keys)}: {code or status_code}"
                ) from exc
            raise IntegrationError(
                "object storage delete_objects_batch failed "
                f"keys={len(normalized_keys)}: {code or 'unknown_client_error'}"
            ) from exc
        except _CONNECTIVITY_ERRORS as exc:
            raise CriticalDependencyError(
                "object storage unavailable during delete_objects_batch "
                f"keys={len(normalized_keys)}: {exc}"
            ) from exc
        except BotoCoreError as exc:
            raise CriticalDependencyError(
                "object storage runtime error during delete_objects_batch "
                f"keys={len(normalized_keys)}: {exc}"
            ) from exc


def build_s3_object_store_client_from_settings(
    settings: Settings | None = None,
) -> S3ObjectStoreClient:
    """Create an S3/MinIO client from application settings."""
    resolved_settings = settings or get_settings()
    s3_client = boto3.client(
        "s3",
        endpoint_url=resolved_settings.S3_ENDPOINT_URL,
        aws_access_key_id=resolved_settings.S3_ACCESS_KEY,
        aws_secret_access_key=resolved_settings.S3_SECRET_KEY,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )
    return S3ObjectStoreClient(
        s3_client=s3_client,
        bucket=resolved_settings.S3_BUCKET,
    )


def _extract_error_code(exc: ClientError) -> str | None:
    error = exc.response.get("Error", {})
    code = error.get("Code")
    return str(code) if code is not None else None


def _extract_http_status_code(exc: ClientError) -> int | None:
    metadata = exc.response.get("ResponseMetadata", {})
    code = metadata.get("HTTPStatusCode")
    return int(code) if code is not None else None
