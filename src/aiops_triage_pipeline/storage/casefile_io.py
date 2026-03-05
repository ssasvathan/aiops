"""CaseFile serialization and hashing helpers."""

from __future__ import annotations

import base64
import hashlib
from typing import Literal, TypeVar, cast

from pydantic import BaseModel

from aiops_triage_pipeline.errors.exceptions import (
    IntegrationError,
    InvariantViolation,
    ObjectNotFoundError,
)
from aiops_triage_pipeline.models.case_file import (
    DIAGNOSIS_HASH_PLACEHOLDER,
    LABELS_HASH_PLACEHOLDER,
    LINKAGE_HASH_PLACEHOLDER,
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileDiagnosisV1,
    CaseFileLabelsV1,
    CaseFileLinkageV1,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult

CaseFileStageName = Literal["triage", "diagnosis", "linkage", "labels"]
CaseFileStagePayload = CaseFileDiagnosisV1 | CaseFileLinkageV1 | CaseFileLabelsV1
CaseFileAnyPayload = CaseFileTriageV1 | CaseFileStagePayload
_CANONICAL_CASEFILE_STAGE_NAMES: tuple[CaseFileStageName, ...] = (
    "triage",
    "diagnosis",
    "linkage",
    "labels",
)
class CasefilePersistResult(BaseModel, frozen=True):
    """Confirmed persistence metadata used by outbox-ready handoff paths."""

    case_id: str
    object_path: str
    triage_hash: str
    write_result: Literal["created", "idempotent"]


class CasefileStagePersistResult(BaseModel, frozen=True):
    """Confirmed persistence metadata for append-only stage file writes."""

    case_id: str
    stage: Literal["diagnosis", "linkage", "labels"]
    object_path: str
    stage_hash: str
    write_result: Literal["created", "idempotent"]


TCaseFile = TypeVar("TCaseFile", bound=BaseModel)


def serialize_casefile_triage(casefile: CaseFileTriageV1) -> bytes:
    """Serialize CaseFile triage payload using the canonical Pydantic JSON path."""
    return casefile.model_dump_json().encode("utf-8")


def serialize_casefile_stage(casefile: CaseFileStagePayload) -> bytes:
    """Serialize append-only stage payload using canonical Pydantic JSON boundaries."""
    return casefile.model_dump_json().encode("utf-8")


def compute_sha256_hex(payload: bytes | str) -> str:
    """Compute deterministic SHA-256 lowercase hex digest for serialized payload bytes."""
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(payload_bytes).hexdigest()


def compute_casefile_triage_hash(casefile: CaseFileTriageV1) -> str:
    """Compute deterministic triage hash over canonical bytes with a placeholder hash field."""
    return _compute_casefile_hash(
        casefile,
        hash_field="triage_hash",
        placeholder_hash=TRIAGE_HASH_PLACEHOLDER,
        model_type=CaseFileTriageV1,
    )


def compute_casefile_diagnosis_hash(casefile: CaseFileDiagnosisV1) -> str:
    """Compute deterministic diagnosis hash over canonical bytes with placeholder hash field."""
    return _compute_casefile_hash(
        casefile,
        hash_field="diagnosis_hash",
        placeholder_hash=DIAGNOSIS_HASH_PLACEHOLDER,
        model_type=CaseFileDiagnosisV1,
    )


def compute_casefile_linkage_hash(casefile: CaseFileLinkageV1) -> str:
    """Compute deterministic linkage hash over canonical bytes with placeholder hash field."""
    return _compute_casefile_hash(
        casefile,
        hash_field="linkage_hash",
        placeholder_hash=LINKAGE_HASH_PLACEHOLDER,
        model_type=CaseFileLinkageV1,
    )


def compute_casefile_labels_hash(casefile: CaseFileLabelsV1) -> str:
    """Compute deterministic labels hash over canonical bytes with placeholder hash field."""
    return _compute_casefile_hash(
        casefile,
        hash_field="labels_hash",
        placeholder_hash=LABELS_HASH_PLACEHOLDER,
        model_type=CaseFileLabelsV1,
    )


def has_valid_casefile_triage_hash(casefile: CaseFileTriageV1) -> bool:
    """Return True when stored triage_hash matches canonical payload hash."""
    return casefile.triage_hash == compute_casefile_triage_hash(casefile)


def has_valid_casefile_diagnosis_hash(casefile: CaseFileDiagnosisV1) -> bool:
    """Return True when stored diagnosis_hash matches canonical payload hash."""
    return casefile.diagnosis_hash == compute_casefile_diagnosis_hash(casefile)


def has_valid_casefile_linkage_hash(casefile: CaseFileLinkageV1) -> bool:
    """Return True when stored linkage_hash matches canonical payload hash."""
    return casefile.linkage_hash == compute_casefile_linkage_hash(casefile)


def has_valid_casefile_labels_hash(casefile: CaseFileLabelsV1) -> bool:
    """Return True when stored labels_hash matches canonical payload hash."""
    return casefile.labels_hash == compute_casefile_labels_hash(casefile)


def validate_casefile_triage_json(payload: bytes | str) -> CaseFileTriageV1:
    """Re-validate serialized triage JSON at deserialize/read boundaries."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    casefile = CaseFileTriageV1.model_validate_json(payload)
    if not has_valid_casefile_triage_hash(casefile):
        raise ValueError("triage_hash does not match canonical serialized payload bytes")
    return casefile


def validate_casefile_diagnosis_json(payload: bytes | str) -> CaseFileDiagnosisV1:
    """Re-validate serialized diagnosis JSON at deserialize/read boundaries."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    casefile = CaseFileDiagnosisV1.model_validate_json(payload)
    if not has_valid_casefile_diagnosis_hash(casefile):
        raise ValueError("diagnosis_hash does not match canonical serialized payload bytes")
    return casefile


def validate_casefile_linkage_json(payload: bytes | str) -> CaseFileLinkageV1:
    """Re-validate serialized linkage JSON at deserialize/read boundaries."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    casefile = CaseFileLinkageV1.model_validate_json(payload)
    if not has_valid_casefile_linkage_hash(casefile):
        raise ValueError("linkage_hash does not match canonical serialized payload bytes")
    return casefile


def validate_casefile_labels_json(payload: bytes | str) -> CaseFileLabelsV1:
    """Re-validate serialized labels JSON at deserialize/read boundaries."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    casefile = CaseFileLabelsV1.model_validate_json(payload)
    if not has_valid_casefile_labels_hash(casefile):
        raise ValueError("labels_hash does not match canonical serialized payload bytes")
    return casefile


def validate_casefile_stage_json(payload: bytes | str, *, stage: str) -> CaseFileAnyPayload:
    """Validate stage JSON using stage-specific model and hash checks."""
    stage_name = _normalize_stage_name(stage)
    if stage_name == "triage":
        return validate_casefile_triage_json(payload)
    if stage_name == "diagnosis":
        return validate_casefile_diagnosis_json(payload)
    if stage_name == "linkage":
        return validate_casefile_linkage_json(payload)
    return validate_casefile_labels_json(payload)


def build_casefile_triage_object_key(case_id: str) -> str:
    """Build deterministic object path for CaseFile triage artifacts."""
    return build_casefile_stage_object_key(case_id=case_id, stage="triage")


def build_casefile_stage_object_key(case_id: str, *, stage: str) -> str:
    """Build deterministic object path for canonical CaseFile stage artifacts."""
    normalized_case_id = case_id.strip()
    if not normalized_case_id:
        raise ValueError("case_id must not be empty")

    stage_name = _normalize_stage_name(stage)
    return f"cases/{normalized_case_id}/{stage_name}.json"


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

    persisted = _persist_casefile_payload_write_once(
        object_store_client=object_store_client,
        case_id=casefile.case_id,
        stage="triage",
        payload=payload,
        stage_hash=casefile.triage_hash,
        metadata={
            "triage_hash": casefile.triage_hash,
            "payload_sha256": payload_sha256,
        },
    )
    return CasefilePersistResult(
        case_id=casefile.case_id,
        object_path=persisted.object_path,
        triage_hash=casefile.triage_hash,
        write_result=persisted.write_result,
    )


def persist_casefile_diagnosis_write_once(
    *,
    object_store_client: ObjectStoreClientProtocol,
    casefile: CaseFileDiagnosisV1,
) -> CasefileStagePersistResult:
    """Persist diagnosis.json using create-only semantics with idempotent retry handling."""
    payload = serialize_casefile_stage(casefile)
    payload_sha256 = compute_sha256_hex(payload)
    expected_hash = compute_casefile_diagnosis_hash(casefile)
    if casefile.diagnosis_hash != expected_hash:
        raise InvariantViolation(
            "diagnosis_hash does not match canonical serialized payload bytes before persistence"
        )

    persisted = _persist_casefile_payload_write_once(
        object_store_client=object_store_client,
        case_id=casefile.case_id,
        stage="diagnosis",
        payload=payload,
        stage_hash=casefile.diagnosis_hash,
        metadata={
            "triage_hash": casefile.triage_hash,
            "diagnosis_hash": casefile.diagnosis_hash,
            "payload_sha256": payload_sha256,
        },
    )
    return CasefileStagePersistResult(
        case_id=casefile.case_id,
        stage="diagnosis",
        object_path=persisted.object_path,
        stage_hash=casefile.diagnosis_hash,
        write_result=persisted.write_result,
    )


def persist_casefile_linkage_write_once(
    *,
    object_store_client: ObjectStoreClientProtocol,
    casefile: CaseFileLinkageV1,
) -> CasefileStagePersistResult:
    """Persist linkage.json using create-only semantics with idempotent retry handling."""
    payload = serialize_casefile_stage(casefile)
    payload_sha256 = compute_sha256_hex(payload)
    expected_hash = compute_casefile_linkage_hash(casefile)
    if casefile.linkage_hash != expected_hash:
        raise InvariantViolation(
            "linkage_hash does not match canonical serialized payload bytes before persistence"
        )

    metadata = {
        "triage_hash": casefile.triage_hash,
        "linkage_hash": casefile.linkage_hash,
        "payload_sha256": payload_sha256,
    }
    if casefile.diagnosis_hash is not None:
        metadata["diagnosis_hash"] = casefile.diagnosis_hash

    persisted = _persist_casefile_payload_write_once(
        object_store_client=object_store_client,
        case_id=casefile.case_id,
        stage="linkage",
        payload=payload,
        stage_hash=casefile.linkage_hash,
        metadata=metadata,
    )
    return CasefileStagePersistResult(
        case_id=casefile.case_id,
        stage="linkage",
        object_path=persisted.object_path,
        stage_hash=casefile.linkage_hash,
        write_result=persisted.write_result,
    )


def persist_casefile_labels_write_once(
    *,
    object_store_client: ObjectStoreClientProtocol,
    casefile: CaseFileLabelsV1,
) -> CasefileStagePersistResult:
    """Persist labels.json using create-only semantics with idempotent retry handling."""
    payload = serialize_casefile_stage(casefile)
    payload_sha256 = compute_sha256_hex(payload)
    expected_hash = compute_casefile_labels_hash(casefile)
    if casefile.labels_hash != expected_hash:
        raise InvariantViolation(
            "labels_hash does not match canonical serialized payload bytes before persistence"
        )

    metadata = {
        "triage_hash": casefile.triage_hash,
        "labels_hash": casefile.labels_hash,
        "payload_sha256": payload_sha256,
    }
    if casefile.diagnosis_hash is not None:
        metadata["diagnosis_hash"] = casefile.diagnosis_hash

    persisted = _persist_casefile_payload_write_once(
        object_store_client=object_store_client,
        case_id=casefile.case_id,
        stage="labels",
        payload=payload,
        stage_hash=casefile.labels_hash,
        metadata=metadata,
    )
    return CasefileStagePersistResult(
        case_id=casefile.case_id,
        stage="labels",
        object_path=persisted.object_path,
        stage_hash=casefile.labels_hash,
        write_result=persisted.write_result,
    )


def read_casefile_stage_json_or_none(
    *,
    object_store_client: ObjectStoreClientProtocol,
    case_id: str,
    stage: str,
) -> CaseFileAnyPayload | None:
    """Read a stage artifact and return explicit absence (None) when optional stage is missing."""
    stage_name = _normalize_stage_name(stage)
    object_path = build_casefile_stage_object_key(case_id=case_id, stage=stage_name)

    try:
        payload = object_store_client.get_object_bytes(key=object_path)
    except KeyError as exc:
        missing_key = exc.args[0] if exc.args else None
        if missing_key == object_path:
            return None
        raise
    except ObjectNotFoundError:
        return None
    except IntegrationError:
        raise

    return validate_casefile_stage_json(payload, stage=stage_name)


def list_present_casefile_stages(
    *,
    object_store_client: ObjectStoreClientProtocol,
    case_id: str,
) -> tuple[CaseFileStageName, ...]:
    """List stage names with persisted objects for a case via explicit stage probing."""
    present_stages: list[CaseFileStageName] = []
    for stage in _CANONICAL_CASEFILE_STAGE_NAMES:
        if read_casefile_stage_json_or_none(
            object_store_client=object_store_client,
            case_id=case_id,
            stage=stage,
        ) is not None:
            present_stages.append(stage)
    return tuple(present_stages)


class _PersistWriteResult(BaseModel, frozen=True):
    object_path: str
    write_result: Literal["created", "idempotent"]


def _compute_casefile_hash(
    casefile: TCaseFile,
    *,
    hash_field: str,
    placeholder_hash: str,
    model_type: type[TCaseFile],
) -> str:
    payload = casefile.model_dump(mode="json")
    payload[hash_field] = placeholder_hash
    canonical = model_type.model_validate(payload)
    return compute_sha256_hex(canonical.model_dump_json())


def _persist_casefile_payload_write_once(
    *,
    object_store_client: ObjectStoreClientProtocol,
    case_id: str,
    stage: CaseFileStageName,
    payload: bytes,
    stage_hash: str,
    metadata: dict[str, str],
) -> _PersistWriteResult:
    object_path = build_casefile_stage_object_key(case_id=case_id, stage=stage)
    checksum_sha256 = _to_s3_checksum_sha256(compute_sha256_hex(payload))
    put_result = object_store_client.put_if_absent(
        key=object_path,
        body=payload,
        content_type="application/json",
        checksum_sha256=checksum_sha256,
        metadata=metadata,
    )
    if put_result is PutIfAbsentResult.CREATED:
        return _PersistWriteResult(object_path=object_path, write_result="created")

    existing_payload = object_store_client.get_object_bytes(key=object_path)
    if existing_payload != payload:
        raise InvariantViolation(
            "write-once invariant violation: existing object payload differs from retry payload"
        )

    try:
        existing_casefile = validate_casefile_stage_json(existing_payload, stage=stage)
    except Exception as exc:  # noqa: BLE001
        raise InvariantViolation(
            "write-once invariant violation: existing object is not a valid "
            f"CaseFile {stage} payload"
        ) from exc

    existing_hash = _extract_stage_hash(existing_casefile, stage=stage)
    if existing_hash != stage_hash:
        raise InvariantViolation(
            "write-once invariant violation: existing object hash does not match retry hash"
        )

    return _PersistWriteResult(object_path=object_path, write_result="idempotent")


def _normalize_stage_name(stage: str) -> CaseFileStageName:
    normalized_stage = stage.strip().lower()
    if normalized_stage not in _CANONICAL_CASEFILE_STAGE_NAMES:
        raise ValueError(
            f"Unsupported casefile stage '{stage}'. Expected one of "
            f"{', '.join(_CANONICAL_CASEFILE_STAGE_NAMES)}"
        )
    return cast(CaseFileStageName, normalized_stage)


def _extract_stage_hash(casefile: CaseFileAnyPayload, *, stage: CaseFileStageName) -> str:
    if stage == "triage":
        return cast(CaseFileTriageV1, casefile).triage_hash
    if stage == "diagnosis":
        return cast(CaseFileDiagnosisV1, casefile).diagnosis_hash
    if stage == "linkage":
        return cast(CaseFileLinkageV1, casefile).linkage_hash
    return cast(CaseFileLabelsV1, casefile).labels_hash


def _to_s3_checksum_sha256(sha256_hex_digest: str) -> str:
    """Convert lowercase SHA-256 hex digest into base64 format expected by S3 ChecksumSHA256."""
    return base64.b64encode(bytes.fromhex(sha256_hex_digest)).decode("ascii")
