"""CaseFile serialization and hashing helpers."""

from __future__ import annotations

import hashlib

from aiops_triage_pipeline.models.case_file import TRIAGE_HASH_PLACEHOLDER, CaseFileTriageV1


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
