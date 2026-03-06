"""Anomaly detection models for Stage 1 evidence analysis."""

from collections import defaultdict
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, Field, field_serializer, model_validator

from aiops_triage_pipeline.contracts.enums import EvidenceStatus

AnomalyFamily = Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]
AnomalySeverity = Literal["LOW", "MEDIUM", "HIGH"]
_ALLOWED_AG2_NON_PRESENT_STATUSES: frozenset[EvidenceStatus] = frozenset(
    {
        EvidenceStatus.UNKNOWN,
        EvidenceStatus.ABSENT,
        EvidenceStatus.STALE,
    }
)


class AnomalyFinding(BaseModel, frozen=True):
    """Structured anomaly finding used for downstream gate input assembly."""

    finding_id: str
    anomaly_family: AnomalyFamily
    scope: tuple[str, ...]
    severity: AnomalySeverity
    reason_codes: tuple[str, ...]
    evidence_required: tuple[str, ...]
    allowed_non_present_statuses_by_evidence: Mapping[str, tuple[EvidenceStatus, ...]] = Field(
        default_factory=dict
    )
    is_primary: bool | None = None

    @model_validator(mode="after")
    def _validate_and_freeze_allowed_non_present_statuses(self) -> "AnomalyFinding":
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


def group_findings_by_scope(
    findings: tuple[AnomalyFinding, ...],
) -> dict[tuple[str, ...], tuple[AnomalyFinding, ...]]:
    """Group findings by normalized scope key preserving insertion order."""
    grouped: dict[tuple[str, ...], list[AnomalyFinding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.scope].append(finding)
    return {scope: tuple(scope_findings) for scope, scope_findings in grouped.items()}


class AnomalyDetectionResult(BaseModel, frozen=True):
    """Anomaly detection result keyed by normalized identity scope."""

    findings: tuple[AnomalyFinding, ...]
    # Always derived from `findings` by the model validator; any caller-supplied value is
    # overwritten. Declared with a default so callers only need to pass `findings`.
    findings_by_scope: Mapping[tuple[str, ...], tuple[AnomalyFinding, ...]] = {}

    @model_validator(mode="after")
    def _derive_and_freeze_findings_by_scope(
        self,
    ) -> "AnomalyDetectionResult":
        # Always derive from `findings` to guarantee consistency; never trust caller-supplied map.
        derived = group_findings_by_scope(self.findings)
        object.__setattr__(self, "findings_by_scope", MappingProxyType(derived))
        return self
