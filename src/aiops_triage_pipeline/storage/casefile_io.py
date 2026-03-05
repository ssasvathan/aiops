"""CaseFile serialization and hashing helpers."""

from __future__ import annotations

import base64
import hashlib
from typing import Literal

from pydantic import BaseModel

from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.models.case_file import TRIAGE_HASH_PLACEHOLDER, CaseFileTriageV1
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult


class CasefilePersistResult(BaseModel, frozen=True):
    """Confirmed persistence metadata used by outbox-ready handoff paths."""

    case_id: str
    object_path: str
    triage_hash: str
    write_result: Literal["created", "idempotent"]


def serialize_casefile_triage(casefile: CaseFileTriageV1) -> bytes:
    """Serialize CaseFile triage payload using the canonical Pydantic JSON path."""
    return casefile.model_dump_json().encode("utf-8")


def compute_sha256_hex(payload: bytes | str) -> str:
    """Compute deterministic SHA-256 lowercase hex digest for serialized payload bytes."""
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(payload_bytes).hexdigest()


def compute_casefile_triage_hash(casefile: CaseFileTriageV1) -> str:
    """Compute deterministic triage hash over canonical bytes with a placeholder hash field."""
    payload = casefile.model_dump(mode="json")
    payload["triage_hash"] = TRIAGE_HASH_PLACEHOLDER
    canonical = CaseFileTriageV1.model_validate(payload)
    return compute_sha256_hex(serialize_casefile_triage(canonical))


def has_valid_casefile_triage_hash(casefile: CaseFileTriageV1) -> bool:
    """Return True when stored triage_hash matches canonical payload hash."""
    return casefile.triage_hash == compute_casefile_triage_hash(casefile)


def validate_casefile_triage_json(payload: bytes | str) -> CaseFileTriageV1:
    """Re-validate serialized CaseFile JSON at deserialize/read boundaries."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    casefile = CaseFileTriageV1.model_validate_json(payload)
    if not has_valid_casefile_triage_hash(casefile):
        raise ValueError("triage_hash does not match canonical serialized payload bytes")
    return casefile


def build_casefile_triage_object_key(case_id: str) -> str:
    """Build deterministic object path for CaseFile triage artifacts."""
    normalized_case_id = case_id.strip()
    if not normalized_case_id:
        raise ValueError("case_id must not be empty")
    return f"cases/{normalized_case_id}/triage.json"


def persist_casefile_triage_write_once(
    *,
    object_store_client: ObjectStoreClientProtocol,
    casefile: CaseFileTriageV1,
) -> CasefilePersistResult:
    """Persist triage.json using create-only semantics with idempotent retry handling."""
    payload = serialize_casefile_triage(casefile)
    payload_sha256 = compute_sha256_hex(payload)
    expected_hash = compute_casefile_triage_hash(casefile)
    if casefile.triage_hash != expected_hash:
        raise InvariantViolation(
            "triage_hash does not match canonical serialized payload bytes before persistence"
        )

    object_path = build_casefile_triage_object_key(casefile.case_id)
    checksum_sha256 = _to_s3_checksum_sha256(payload_sha256)
    put_result = object_store_client.put_if_absent(
        key=object_path,
        body=payload,
        content_type="application/json",
        checksum_sha256=checksum_sha256,
        metadata={
            "triage_hash": casefile.triage_hash,
            "payload_sha256": payload_sha256,
        },
    )
    if put_result is PutIfAbsentResult.CREATED:
        return CasefilePersistResult(
            case_id=casefile.case_id,
            object_path=object_path,
            triage_hash=casefile.triage_hash,
            write_result="created",
        )

    existing_payload = object_store_client.get_object_bytes(key=object_path)
    if existing_payload != payload:
        raise InvariantViolation(
            "write-once invariant violation: existing object payload differs from retry payload"
        )

    try:
        existing_casefile = validate_casefile_triage_json(existing_payload)
    except Exception as exc:  # noqa: BLE001
        raise InvariantViolation(
            "write-once invariant violation: existing object is not a valid CaseFile triage payload"
        ) from exc

    if existing_casefile.triage_hash != casefile.triage_hash:
        raise InvariantViolation(
            "write-once invariant violation: existing object hash does not match retry hash"
        )

    return CasefilePersistResult(
        case_id=casefile.case_id,
        object_path=object_path,
        triage_hash=casefile.triage_hash,
        write_result="idempotent",
    )


def _to_s3_checksum_sha256(sha256_hex_digest: str) -> str:
    """Convert lowercase SHA-256 hex digest into base64 format expected by S3 ChecksumSHA256."""
    return base64.b64encode(bytes.fromhex(sha256_hex_digest)).decode("ascii")
