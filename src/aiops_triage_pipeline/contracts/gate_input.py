"""GateInputV1 — deterministic input to Rulebook AG0–AG6 evaluation (Stage 6)."""

import re
from types import MappingProxyType
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)

# NFR-S1: Bearer token pattern used to strip sensitive credential values from decision_basis
# at model construction time, ensuring they never appear in the canonical hash payload baseline.
_BEARER_TOKEN_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)bearer\s+[A-Za-z0-9._+/=\-]{10,}"
)

_ALLOWED_AG2_NON_PRESENT_STATUSES: frozenset[EvidenceStatus] = frozenset(
    {
        EvidenceStatus.UNKNOWN,
        EvidenceStatus.ABSENT,
        EvidenceStatus.STALE,
    }
)


class Finding(BaseModel, frozen=True):
    finding_id: str
    name: str
    is_anomalous: bool
    evidence_required: tuple[str, ...]  # Evidence primitives required; drives AG2
    # Optional per-evidence explicit allowances for non-PRESENT statuses in AG2.
    allowed_non_present_statuses_by_evidence: Mapping[str, tuple[EvidenceStatus, ...]] = Field(
        default_factory=dict
    )
    is_primary: bool | None = None  # If True, AG2 uses this finding's requirements preferentially
    severity: str | None = None
    reason_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_and_freeze_allowed_non_present_statuses(self) -> "Finding":
        evidence_required_set = set(self.evidence_required)
        normalized_allowances: dict[str, tuple[EvidenceStatus, ...]] = {}
        for evidence_key, statuses in self.allowed_non_present_statuses_by_evidence.items():
            if evidence_key not in evidence_required_set:
                raise ValueError(
                    "allowed_non_present_statuses_by_evidence keys must be present in "
                    f"evidence_required; got {evidence_key!r}"
                )
            if not statuses:
                raise ValueError(
                    "allowed_non_present_statuses_by_evidence values must include at least "
                    f"one status for {evidence_key!r}"
                )
            invalid_statuses = tuple(
                status
                for status in statuses
                if status not in _ALLOWED_AG2_NON_PRESENT_STATUSES
            )
            if invalid_statuses:
                invalid_values = tuple(status.value for status in invalid_statuses)
                raise ValueError(
                    "allowed_non_present_statuses_by_evidence values must be subset of "
                    f"UNKNOWN/ABSENT/STALE; got {invalid_values!r} for {evidence_key!r}"
                )
            normalized_allowances[evidence_key] = tuple(dict.fromkeys(statuses))

        object.__setattr__(
            self,
            "allowed_non_present_statuses_by_evidence",
            MappingProxyType(normalized_allowances),
        )
        return self

    @field_serializer("allowed_non_present_statuses_by_evidence")
    def _serialize_allowed_non_present_statuses(
        self,
        value: Mapping[str, tuple[EvidenceStatus, ...]],
    ) -> dict[str, tuple[EvidenceStatus, ...]]:
        return {evidence_key: tuple(statuses) for evidence_key, statuses in value.items()}


class GateInputV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    # Identity
    env: Environment
    cluster_id: str  # cluster_id := cluster_name (exact string)
    stream_id: str  # Logical end-to-end pipeline grouping key
    topic: str  # Topic that triggered the anomaly key
    topic_role: Literal["SOURCE_TOPIC", "SHARED_TOPIC", "SINK_TOPIC"]
    anomaly_family: Literal[
        "CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"
    ]
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

    @field_validator("decision_basis", mode="before")
    @classmethod
    def _sanitize_decision_basis(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Strip bearer token values from decision_basis at model construction time.

        NFR-S1: Ensures raw credential values never appear in the canonical hash payload
        baseline, regardless of how the casefile was constructed. This is a defence-in-depth
        guard complementing the denylist-based sanitization in assemble_casefile_triage_stage.
        """
        if value is None:
            return None
        return _sanitize_decision_basis_recursive(value)


def _sanitize_decision_basis_recursive(mapping: dict[str, Any]) -> dict[str, Any]:
    """Recursively remove mapping entries whose string values match the bearer token pattern."""
    result: dict[str, Any] = {}
    for key, val in mapping.items():
        if isinstance(val, str) and _BEARER_TOKEN_PATTERN.search(val):
            continue
        if isinstance(val, dict):
            result[key] = _sanitize_decision_basis_recursive(val)
        elif isinstance(val, list):
            result[key] = [
                item
                for item in val
                if not (isinstance(item, str) and _BEARER_TOKEN_PATTERN.search(item))
            ]
        else:
            result[key] = val
    return result
