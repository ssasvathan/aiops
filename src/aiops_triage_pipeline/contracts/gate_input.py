"""GateInputV1 — deterministic input to Rulebook AG0–AG6 evaluation (Stage 6)."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)


class Finding(BaseModel, frozen=True):
    finding_id: str
    name: str
    is_anomalous: bool
    evidence_required: tuple[str, ...]  # Evidence primitives required; drives AG2
    is_primary: bool | None = None  # If True, AG2 uses this finding's requirements preferentially
    severity: str | None = None
    reason_codes: tuple[str, ...] = ()


class GateInputV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    # Identity
    env: Environment
    cluster_id: str  # cluster_id := cluster_name (exact string)
    stream_id: str  # Logical end-to-end pipeline grouping key
    topic: str  # Topic that triggered the anomaly key
    topic_role: Literal["SOURCE_TOPIC", "SHARED_TOPIC", "SINK_TOPIC"]
    anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]
    criticality_tier: CriticalityTier
    # Diagnosis inputs
    proposed_action: Action  # Diagnosis result before gates apply
    diagnosis_confidence: Annotated[float, Field(ge=0.0, le=1.0)]  # Deterministic scalar
    sustained: bool  # True if anomaly sustained for sustained_intervals_required windows
    findings: tuple[Finding, ...]  # Justify diagnosis; declare evidence requirements
    # Evidence primitive -> PRESENT/UNKNOWN/ABSENT/STALE
    evidence_status_map: dict[str, EvidenceStatus]
    action_fingerprint: str  # Identity fingerprint (excludes timestamps/metric values)
    # Optional
    consumer_group: str | None = None  # Required for lag-based anomalies; omit otherwise
    partition_count_observed: int | None = None  # For confidence downgrade on partition coverage
    peak: bool | None = None  # If computed; used for postmortem selector (AG6)
    case_id: str | None = None  # Stable case identifier (for audit)
    decision_basis: dict[str, Any] | None = None  # Optional deterministic linkage
