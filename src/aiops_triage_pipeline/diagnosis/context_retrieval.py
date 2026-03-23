"""Cold-path context retrieval: read triage.json from S3 and reconstruct TriageExcerptV1.

Implements FR37: S3 context retrieval + TriageExcerptV1 reconstruction.
Invariant A: triage.json is guaranteed to exist by the hot-path before any
CaseHeaderEventV1 is published. If missing, that is a system invariant violation
— this module raises loudly rather than silently continuing.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.errors.exceptions import InvariantViolation, ObjectNotFoundError
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.case_file import CaseFileTriageV1
from aiops_triage_pipeline.storage.casefile_io import (
    build_casefile_triage_object_key,
    has_valid_casefile_triage_hash,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol

_logger = get_logger("diagnosis.context_retrieval")


class CaseTriageNotFoundError(InvariantViolation):
    """Raised when triage.json is absent in object storage.

    This is an invariant violation: triage.json must always be present before
    a CaseHeaderEventV1 is published (Invariant A, D6 cold-path design).
    """


@dataclass(frozen=True)
class RetrievedCaseContext:
    """Validated cold-path context payload from persisted triage.json."""

    excerpt: TriageExcerptV1
    triage_hash: str


def retrieve_case_context_with_hash(
    *,
    case_id: str,
    object_store_client: ObjectStoreClientProtocol,
) -> RetrievedCaseContext:
    """Read triage.json and return both TriageExcerptV1 and validated triage_hash."""
    casefile, object_path = _load_casefile_triage(
        case_id=case_id,
        object_store_client=object_store_client,
    )
    excerpt = _build_triage_excerpt(casefile)

    _logger.info(
        "case_context_retrieved",
        case_id=case_id,
        triage_hash=casefile.triage_hash,
        object_path=object_path,
    )
    return RetrievedCaseContext(excerpt=excerpt, triage_hash=casefile.triage_hash)


def _load_casefile_triage(
    *,
    case_id: str,
    object_store_client: ObjectStoreClientProtocol,
) -> tuple[CaseFileTriageV1, str]:
    """Load and validate triage.json from object storage."""
    object_path = build_casefile_triage_object_key(case_id)

    # Read raw bytes from object storage; ObjectNotFoundError → domain error
    try:
        payload_bytes = object_store_client.get_object_bytes(key=object_path)
    except ObjectNotFoundError as exc:
        raise CaseTriageNotFoundError(
            f"Invariant A violated: triage.json missing for case {case_id!r} "
            f"at path {object_path!r}. The hot-path must persist triage.json "
            "before publishing CaseHeaderEventV1."
        ) from exc

    # Deserialize and validate schema
    casefile = CaseFileTriageV1.model_validate_json(payload_bytes)

    # Validate hash chain integrity before using any data
    if not has_valid_casefile_triage_hash(casefile):
        raise InvariantViolation(
            f"Hash chain integrity check failed for case {case_id!r}: "
            f"stored triage_hash={casefile.triage_hash!r} does not match "
            "the computed hash over the canonical payload bytes. "
            "The casefile may have been tampered with or corrupted."
        )
    return casefile, object_path


def _build_triage_excerpt(casefile: CaseFileTriageV1) -> TriageExcerptV1:
    """Map validated CaseFileTriageV1 fields to TriageExcerptV1."""
    # Map peak flag from evidence_snapshot.peak_context
    peak: bool | None = None
    if casefile.evidence_snapshot.peak_context is not None:
        peak = casefile.evidence_snapshot.peak_context.is_peak_window

    return TriageExcerptV1(
        case_id=casefile.case_id,
        env=casefile.gate_input.env,
        cluster_id=casefile.gate_input.cluster_id,
        stream_id=casefile.gate_input.stream_id,
        topic=casefile.gate_input.topic,
        anomaly_family=casefile.gate_input.anomaly_family,
        topic_role=casefile.topology_context.topic_role,
        criticality_tier=casefile.topology_context.criticality_tier,
        routing_key=casefile.topology_context.routing.routing_key,
        sustained=casefile.gate_input.sustained,
        peak=peak,
        evidence_status_map=dict(casefile.gate_input.evidence_status_map),
        findings=casefile.gate_input.findings,
        triage_timestamp=casefile.triage_timestamp,
    )


def retrieve_case_context(
    *,
    case_id: str,
    object_store_client: ObjectStoreClientProtocol,
) -> TriageExcerptV1:
    """Read triage.json from object storage and reconstruct TriageExcerptV1.

    Reads ``cases/{case_id}/triage.json`` via the object store client,
    validates the triage_hash integrity, and maps CaseFileTriageV1 fields
    to a TriageExcerptV1 for use by the cold-path diagnosis pipeline.

    Args:
        case_id: The case identifier used to locate the triage artifact.
        object_store_client: Synchronous object store client (S3/MinIO).

    Returns:
        Reconstructed TriageExcerptV1 with all fields populated from the
        persisted casefile triage artifact.

    Raises:
        CaseTriageNotFoundError: If triage.json is absent (Invariant A violation).
        InvariantViolation: If the stored triage_hash does not match the
            computed hash over the canonical payload bytes.
    """
    return retrieve_case_context_with_hash(
        case_id=case_id,
        object_store_client=object_store_client,
    ).excerpt
